"""
historian/server.py
Simulated SCADA historian for the "Interceptor Down" CTF -- Stage 2.

Speaks a small, custom, undocumented binary protocol over raw TCP (not a
real/public protocol, so no off-the-shelf client library applies; players
must reverse-engineer the frame format, e.g. from a sample capture you
provide out-of-band). No authentication at all -- the vulnerability here
is CWE-200 (information disclosure): anyone who can frame a valid request
gets the internal network map and register map back.

Frame format:
  MAGIC    2 bytes   0xCA 0xFE
  LENGTH   2 bytes   big-endian, length of (TAG + FUNC + PAYLOAD) in bytes
  TAG      2 bytes   big-endian tag id being requested
  FUNC     1 byte    0x01 = read request (client->server)
                     0x81 = read response (server->client, 0x01 | 0x80)
  PAYLOAD  variable  empty on request; response text on reply
  CHECKSUM 1 byte    XOR of every byte from MAGIC through PAYLOAD inclusive
                     (deliberately weak -- single-byte XOR, trivial to
                     recompute once the algorithm is known)

A bad checksum gets silently dropped (connection closes, no error text) --
this forces players to get the framing exactly right through trial and
error / packet analysis rather than iterating against helpful error
messages.
"""
import socket
import socketserver
import struct

HOST, PORT = "0.0.0.0", 7878
MAGIC = b"\xCA\xFE"

TAGS = {
    0x0001: (
        "NETWORK MAP\n"
        "ot-net: 172.20.0.0/24\n"
        "plc-radar: plc-radar:502 (Modbus TCP)\n"
        "plc-battery: plc-battery:502 (Modbus TCP)\n"
        "hmi: hmi:8082\n"
    ),
    0x0002: (
        "REGISTER MAP\n"
        "plc-radar:   HR40001=tracking_confidence  Coil00001=lock_state\n"
        "plc-battery: Coil00002=arm_state(interlocked)  HR40002=launcher_elevation\n"
        "             Coil00003=fire_command  HR40012=race_flag  HR40020+=flag(ascii)\n"
    ),
    0x0003: (
        "INTERLOCK NOTES\n"
        "Battery arm command requires plc-radar lock_state active at commit time.\n"
        "Legacy diagnostic registers on both PLCs were left enabled after the\n"
        "last firmware update -- not in the official tag documentation, but\n"
        "still readable. Worth checking nearby register addresses.\n"
    ),
}


def checksum(data: bytes) -> int:
    c = 0
    for b in data:
        c ^= b
    return c


def build_frame(tag: int, func: int, payload: bytes) -> bytes:
    body = struct.pack(">H", tag) + struct.pack(">B", func) + payload
    length = len(body)
    header = MAGIC + struct.pack(">H", length)
    full = header + body
    return full + bytes([checksum(full)])


class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(15)
        buf = b""
        while True:
            try:
                chunk = self.request.recv(4096)
            except (socket.timeout, OSError):
                return
            if not chunk:
                return
            buf += chunk
            while len(buf) >= 5:
                if buf[0:2] != MAGIC:
                    return  # bad magic -- drop silently
                length = struct.unpack(">H", buf[2:4])[0]
                total = 4 + length + 1  # header(4) + body(length) + checksum(1)
                if len(buf) < total:
                    break
                frame = buf[:total]
                buf = buf[total:]
                resp = self.process(frame)
                if resp:
                    try:
                        self.request.sendall(resp)
                    except OSError:
                        return
                else:
                    return  # bad checksum -- silently close, no hint

    def process(self, frame: bytes):
        body = frame[4:-1]
        received_cksum = frame[-1]
        if checksum(frame[:-1]) != received_cksum:
            return None
        tag = struct.unpack(">H", body[0:2])[0]
        func = body[2]
        if func != 0x01:
            return build_frame(tag, 0x81, b"ERR: unsupported function")
        text = TAGS.get(tag)
        if text is None:
            return build_frame(tag, 0x81, b"ERR: unknown tag")
        return build_frame(tag, 0x81, text.encode())


if __name__ == "__main__":
    srv = socketserver.ThreadingTCPServer((HOST, PORT), Handler)
    srv.daemon_threads = True
    srv.allow_reuse_address = True
    print(f"historian listening on {HOST}:{PORT}")
    srv.serve_forever()
