#!/usr/bin/env python3
"""
field-safety-bus - Stage 3.5c
A proprietary device-to-device protocol broadcasting the live interlock
status the PLCs are built around. Deliberately distinct framing from
historian's custom protocol (CRC-8 here instead of XOR) so it's a genuinely
separate reverse-engineering exercise.

Frame format (all big-endian):
  0xAA 0x55        sync bytes
  ver (1)          protocol version, = 1
  type (1)         0x10 = QUERY (client->server), 0x11 = STATUS (server->client)
  len (1)          length of payload
  payload (len)
  crc8 (1)          CRC-8/ATM (poly 0x07) over [ver, type, len, payload...]

STATUS payload layout (what it leaks -- the point of this stage):
  interlock_armed      (1)   0/1
  arm_window_open_ms   (2)   ms remaining the arm window stays open
  arm_window_total_ms  (2)   total duration of the arm window
  lock_hold_ms         (2)   current lock-hold duration (reflects any
                              hart-gateway calibration write, if coupled)
  seq                  (2)   monotonically increasing status counter

Behavior: broadcasts STATUS to all connected clients every BROADCAST_MS,
and also answers unsolicited QUERY frames immediately. No auth at all --
this bus is "trusted by physical presence" in-world, which is exactly why
leaking it over the network is the bug.
"""
import asyncio
import json
import os
import struct
import time

HOST = "0.0.0.0"
PORT = int(os.environ.get("FIELD_SAFETY_BUS_PORT", "4747"))
BROADCAST_MS = int(os.environ.get("FSB_BROADCAST_MS", "500"))

SHARED_STATE_PATH = os.environ.get("SHARED_STATE_PATH", "/shared/calibration_offset.json")

SYNC = b"\xAA\x55"
VERSION = 1
TYPE_QUERY = 0x10
TYPE_STATUS = 0x11

BASE_LOCK_HOLD_MS = 800
ARM_WINDOW_TOTAL_MS = 2000

_clients = set()
_seq = 0


def crc8(data: bytes) -> int:
    crc = 0x00
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ 0x07) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc


def build_frame(msg_type: int, payload: bytes) -> bytes:
    header = bytes([VERSION, msg_type, len(payload)])
    body = header + payload
    return SYNC + body + bytes([crc8(body)])


def current_lock_hold_ms() -> int:
    """Reflects hart-gateway's calibration write, if present."""
    try:
        with open(SHARED_STATE_PATH) as f:
            data = json.load(f)
        offset = float(data.get("calibration_offset", 0.0))
        # clamp so a single write can shift timing but not trivially win the stage
        offset = max(-300.0, min(300.0, offset))
        return int(BASE_LOCK_HOLD_MS + offset)
    except FileNotFoundError:
        return BASE_LOCK_HOLD_MS
    except Exception:
        return BASE_LOCK_HOLD_MS


def status_payload() -> bytes:
    global _seq
    _seq = (_seq + 1) % 65536
    cycle_pos_ms = int((time.monotonic() * 1000) % (ARM_WINDOW_TOTAL_MS * 3))
    armed = 1 if cycle_pos_ms < ARM_WINDOW_TOTAL_MS else 0
    window_open_ms = max(0, ARM_WINDOW_TOTAL_MS - cycle_pos_ms) if armed else 0
    lock_hold = current_lock_hold_ms()
    return struct.pack(">BHHHH", armed, window_open_ms, ARM_WINDOW_TOTAL_MS, lock_hold, _seq)


async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    peer = writer.get_extra_info("peername")
    print(f"[field-safety-bus] connection from {peer}")
    _clients.add(writer)
    buf = b""
    try:
        while True:
            chunk = await reader.read(256)
            if not chunk:
                break
            buf += chunk
            buf = await process_buffer(buf, writer)
    except ConnectionResetError:
        pass
    finally:
        _clients.discard(writer)
        print(f"[field-safety-bus] connection closed {peer}")
        writer.close()


async def process_buffer(buf: bytes, writer: asyncio.StreamWriter) -> bytes:
    while True:
        idx = buf.find(SYNC)
        if idx == -1:
            return b""
        if idx > 0:
            buf = buf[idx:]
        if len(buf) < 5:
            return buf  # need more data for header
        ver, msg_type, length = buf[2], buf[3], buf[4]
        frame_len = 2 + 3 + length + 1
        if len(buf) < frame_len:
            return buf  # wait for more
        frame = buf[:frame_len]
        buf = buf[frame_len:]

        body = frame[2:2 + 3 + length]
        received_crc = frame[-1]
        if crc8(body) != received_crc:
            continue  # bad frame, drop

        if msg_type == TYPE_QUERY:
            resp = build_frame(TYPE_STATUS, status_payload())
            writer.write(resp)
            await writer.drain()


async def broadcaster():
    while True:
        await asyncio.sleep(BROADCAST_MS / 1000)
        if not _clients:
            continue
        frame = build_frame(TYPE_STATUS, status_payload())
        dead = []
        for w in _clients:
            try:
                w.write(frame)
                await w.drain()
            except Exception:
                dead.append(w)
        for w in dead:
            _clients.discard(w)


async def main():
    server = await asyncio.start_server(handle_client, HOST, PORT)
    print(f"[field-safety-bus] listening on {HOST}:{PORT}")
    asyncio.create_task(broadcaster())
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
