#!/usr/bin/env python3
"""
hart-gateway - Stage 3.5b
Minimal real subset of HART-IP (TCP/5094, the IANA-registered port) feeding
plc-radar's calibration sensor.

Implements:
  - Session Initiate request/response (HART-IP message type 0x00)
  - Token-Passing frames (message type 0x00... see TPO below) carrying real
    HART command bytes:
      Command 0   - Read Unique Identifier
      Command 1   - Read Primary Variable
      Command 148 - Write Calibration Offset (device-specific, 128-253 range)

VULNERABILITY (intentional): the session handshake does no authentication
at all. Any client that completes Session Initiate gets full read/write on
device variables. This mirrors a real, documented HART-IP weakness.

If HART_MECH_COUPLING=1, a successful Command 148 write updates a shared
value that plc-radar polls each tick to shift its lock-hold duration -
small, one-directional coupling, no RPC back into this process.
"""
import asyncio
import json
import os
import struct
import time

HOST = "0.0.0.0"
PORT = int(os.environ.get("HART_GATEWAY_PORT", "5094"))

DEVICE_TAG = os.environ.get("HART_DEVICE_TAG", "RDR-CAL-07")
DEVICE_ID = bytes.fromhex("534e5230370000")[:7].ljust(7, b"\x00")  # fake unique ID
PRIMARY_VARIABLE_UNIT = 0xB2  # arbitrary HART unit code (e.g. "mm")

MECH_COUPLING = os.environ.get("HART_MECH_COUPLING", "1") == "1"
SHARED_STATE_PATH = os.environ.get("SHARED_STATE_PATH", "/shared/calibration_offset.json")

# -------------------- HART-IP framing constants --------------------
HARTIP_VERSION = 1

MSG_TYPE_REQUEST = 0x00
MSG_TYPE_RESPONSE = 0x01

MSG_ID_SESSION_INIT = 0x00
MSG_ID_TOKEN_PASSING = 0x02
MSG_ID_SESSION_CLOSE = 0x03

# HART-IP header: version(1) msgType(1) msgID(1) status(1) seq(2) byteCount(2)
HEADER_FMT = ">BBBBHH"
HEADER_LEN = struct.calcsize(HEADER_FMT)


def build_header(msg_type, msg_id, status, seq, payload_len):
    return struct.pack(HEADER_FMT, HARTIP_VERSION, msg_type, msg_id, status, seq, HEADER_LEN + payload_len)


def write_shared_offset(offset_raw_bytes):
    if not MECH_COUPLING:
        return
    try:
        offset = struct.unpack(">f", offset_raw_bytes)[0]
        data = {"calibration_offset": offset, "ts": time.time(), "device_tag": DEVICE_TAG}
        os.makedirs(os.path.dirname(SHARED_STATE_PATH), exist_ok=True)
        tmp = SHARED_STATE_PATH + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f)
        os.replace(tmp, SHARED_STATE_PATH)
        print(f"[hart-gateway] calibration_offset -> {offset}")
    except Exception as e:
        print(f"[hart-gateway] failed to write shared offset: {e}")


async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    peer = writer.get_extra_info("peername")
    print(f"[hart-gateway] connection from {peer}")
    session_open = False

    try:
        while True:
            header = await reader.readexactly(HEADER_LEN)
            version, msg_type, msg_id, status, seq, byte_count = struct.unpack(HEADER_FMT, header)
            payload_len = byte_count - HEADER_LEN
            payload = await reader.readexactly(payload_len) if payload_len > 0 else b""

            if msg_id == MSG_ID_SESSION_INIT and msg_type == MSG_TYPE_REQUEST:
                # NO AUTH CHECK -- this is the vuln. Any requester is granted a session.
                session_open = True
                # Response payload: inactivity timeout (2B) + max frame size type fields (trimmed, minimal)
                resp_payload = struct.pack(">H", 5000)  # inactivity timeout ms
                hdr = build_header(MSG_TYPE_RESPONSE, MSG_ID_SESSION_INIT, 0, seq, len(resp_payload))
                writer.write(hdr + resp_payload)
                await writer.drain()
                print(f"[hart-gateway] session opened for {peer} (no auth performed)")
                continue

            if msg_id == MSG_ID_SESSION_CLOSE:
                break

            if msg_id == MSG_ID_TOKEN_PASSING and msg_type == MSG_TYPE_REQUEST:
                if not session_open:
                    # still respond -- real gateways are often lenient here too
                    pass
                resp = handle_hart_command(payload)
                hdr = build_header(MSG_TYPE_RESPONSE, MSG_ID_TOKEN_PASSING, 0, seq, len(resp))
                writer.write(hdr + resp)
                await writer.drain()
                continue

            # Unknown message id -- just ack with empty response to keep things moving
            hdr = build_header(MSG_TYPE_RESPONSE, msg_id, 0, seq, 0)
            writer.write(hdr)
            await writer.drain()

    except (asyncio.IncompleteReadError, ConnectionResetError):
        pass
    finally:
        print(f"[hart-gateway] connection closed {peer}")
        writer.close()


def handle_hart_command(payload: bytes) -> bytes:
    """
    payload is a HART command frame (simplified, long-address style):
      command(1) byteCount(1) data(byteCount)
    Returns a response frame: command(1) responseCode(1) deviceStatus(1) data(...)
    """
    if len(payload) < 2:
        return bytes([0, 2, 0])  # command error

    command = payload[0]
    data_len = payload[1]
    data = payload[2:2 + data_len]

    if command == 0:
        # Read Unique Identifier
        resp_data = DEVICE_ID + DEVICE_TAG.encode().ljust(8, b"\x00")[:8]
        return bytes([0, 0, 0]) + resp_data

    elif command == 1:
        # Read Primary Variable
        pv = 42.5  # fake live reading
        resp_data = bytes([PRIMARY_VARIABLE_UNIT]) + struct.pack(">f", pv)
        return bytes([1, 0, 0]) + resp_data

    elif command == 148:
        # Write Calibration Offset (device-specific command, 128-253 range)
        if len(data) >= 4:
            write_shared_offset(data[:4])
            return bytes([148, 0, 0]) + data[:4]
        return bytes([148, 2, 0])  # invalid data

    else:
        return bytes([command, 64, 0])  # "command not implemented"


async def main():
    server = await asyncio.start_server(handle_client, HOST, PORT)
    print(f"[hart-gateway] listening on {HOST}:{PORT} (HART-IP, unauthenticated by design)")
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
