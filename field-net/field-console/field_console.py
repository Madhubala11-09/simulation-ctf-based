#!/usr/bin/env python3
"""
field-console - Stage 3.5a
Legacy "Field Diagnostics Console" - raw TCP, telnet-style, username/password.

Creds are intentionally weak/default and are meant to be discoverable from
earlier stages (e.g. referenced in historian's interlock notes or
engineering-ws's config leak). Set via env so the CTF build can inject them
consistently with whatever breadcrumb you leave in Stage 2/3.

Vulnerability: `debug-dump` is a real but undocumented command (absent from
`help`) left in by an engineer. It has no access control beyond the initial
login and leaks the HART gateway's address + device tag needed for 3.5b.
"""
import asyncio
import os

HOST = "0.0.0.0"
PORT = int(os.environ.get("FIELD_CONSOLE_PORT", "2323"))

# Weak/default creds -- wire this up to match whatever breadcrumb Stage 2/3 leaves.
USERNAME = os.environ.get("FIELD_CONSOLE_USER", "fieldtech")
PASSWORD = os.environ.get("FIELD_CONSOLE_PASS", "fieldtech123")

HART_GATEWAY_HOST = os.environ.get("HART_GATEWAY_HOST", "hart-gateway")
HART_GATEWAY_PORT = os.environ.get("HART_GATEWAY_PORT", "5094")
HART_DEVICE_TAG = os.environ.get("HART_DEVICE_TAG", "RDR-CAL-07")

BANNER = (
    "=================================================\n"
    " Field Diagnostics Console v2.3  (c) Meridian Instruments\n"
    " UNAUTHORIZED ACCESS PROHIBITED\n"
    "=================================================\n"
)

HELP_TEXT = (
    "Available commands:\n"
    "  help          - show this text\n"
    "  status        - show console status\n"
    "  list-devices  - list devices on the field bus\n"
    "  quit          - disconnect\n"
)

DEVICES = [
    "RDR-CAL-07   HART transducer     (radar calibration sensor)",
    "BAT-TMP-03   HART transducer     (battery pack thermal sensor)",
    "SAFE-BUS-01  field-safety-bus    (interlock broadcast node)",
]


async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    peer = writer.get_extra_info("peername")
    writer.write(BANNER.encode())
    await writer.drain()

    # --- auth ---
    writer.write(b"login: ")
    await writer.drain()
    user_line = await reader.readline()
    user = user_line.decode(errors="replace").strip()

    writer.write(b"password: ")
    await writer.drain()
    pass_line = await reader.readline()
    pw = pass_line.decode(errors="replace").strip()

    if user != USERNAME or pw != PASSWORD:
        writer.write(b"Login incorrect\n")
        await writer.drain()
        writer.close()
        return

    writer.write(f"\nWelcome, {user}. Type 'help' for commands.\n> ".encode())
    await writer.drain()

    while True:
        line = await reader.readline()
        if not line:
            break
        cmd = line.decode(errors="replace").strip()

        if cmd == "help":
            writer.write(HELP_TEXT.encode())

        elif cmd == "status":
            writer.write(b"console: OK  uptime: 128d  bus-errors: 0\n")

        elif cmd == "list-devices":
            writer.write(("\n".join(DEVICES) + "\n").encode())

        elif cmd == "debug-dump":
            # Undocumented. Not in help output. The vuln.
            dump = (
                "-- DEBUG DUMP (eng build, remove before ship) --\n"
                f"hart_gateway_addr = {HART_GATEWAY_HOST}:{HART_GATEWAY_PORT}\n"
                f"hart_device_tag   = {HART_DEVICE_TAG}\n"
                "hart_session_auth = none (handshake only)\n"
                "-------------------------------------------------\n"
            )
            writer.write(dump.encode())

        elif cmd in ("quit", "exit"):
            writer.write(b"bye\n")
            await writer.drain()
            break

        elif cmd == "":
            pass

        else:
            writer.write(f"unknown command: {cmd}\n".encode())

        writer.write(b"> ")
        await writer.drain()

    writer.close()


async def main():
    server = await asyncio.start_server(handle_client, HOST, PORT)
    print(f"[field-console] listening on {HOST}:{PORT}")
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
