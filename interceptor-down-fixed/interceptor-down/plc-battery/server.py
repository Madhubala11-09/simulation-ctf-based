"""
plc-battery/server.py
Simulated interceptor-battery PLC for the "Interceptor Down" CTF.

Modbus TCP map (0-based protocol addresses; add 40001/00001 for the
human-facing tag names used in challenge documentation):

  Coil             1  (00002)  arm_state         write-gated, TOCTOU vuln lives here
  Holding Register 1  (40002)  launcher_elevation  R/W, cosmetic
  Coil             2  (00003)  fire_command       requires arm_state True
  Holding Register 9  (40010)  last_check_time    debug, truncated ms
  Holding Register 10 (40011)  last_commit_time   debug, truncated ms
  Holding Register 11 (40012)  race_flag          0/1, set server-side only
  Holding Registers 20-79 (40020-40079)  flag ASCII bytes (one char per
                                          register, null-terminated),
                                          populated only once race_flag == 1

--- THE VULNERABILITY (CWE-367, Time-of-Check to Time-of-Use) ---

Arming the battery (writing Coil 1 = True) requires plc-radar's lock_state
coil to be active. The handler:

  1. CHECKS plc-radar's lock coil and reads its remaining-ms debug register
     (this is the "check")
  2. sleeps for ARTIFICIAL_DELAY seconds, simulating "interlock verification
     processing"
  3. COMMITS the arm write (this is the "use")

Step 3 never re-verifies that the lock is still valid. If the commit lands
after the lock's actual expiry (because the delay pushed it past the
window), the arm write still succeeds -- an unauthorized arm. race_flag is
then set to 1 purely from server-side timestamps the client never supplies,
and the flag becomes readable.

A plain "unlock -> immediate write" sequence does NOT trigger this: the
check and commit both land comfortably inside the lock window, which is
intended, legitimate behavior. Only a write timed (or burst-raced) right at
the lock's expiry boundary can land its commit after expiry.
"""
import os
import time

from modbus_mini import DataStore, ModbusMiniServer
from modbus_client_mini import ModbusMiniClient

RADAR_HOST = os.environ.get("RADAR_HOST", "plc-radar")
RADAR_PORT = int(os.environ.get("RADAR_PORT", "502"))
PORT = int(os.environ.get("PORT", "502"))
ARTIFICIAL_DELAY = float(os.environ.get("ARTIFICIAL_DELAY", "0.25"))  # seconds

FLAG = os.environ.get("FLAG", "CTF{toctou_cross_plc_interlock_bypass_demo}")

store = DataStore()
store.set_coil_raw(1, False)     # 00002 arm_state
store.set_register_raw(1, 0)     # 40002 launcher elevation
store.set_coil_raw(2, False)     # 00003 fire_command
store.set_register_raw(9, 0)     # 40010 last check-time (truncated ms)
store.set_register_raw(10, 0)    # 40011 last commit-time (truncated ms)
store.set_register_raw(11, 0)    # 40012 race_flag

radar_client = ModbusMiniClient(RADAR_HOST, RADAR_PORT)


def _populate_flag(store):
    for i, ch in enumerate(FLAG):
        store.set_register_raw(20 + i, ord(ch))
    store.set_register_raw(20 + len(FLAG), 0)


def coil_write_hook(store, address, value):
    if address == 1 and value:
        # --- arming the battery: the vulnerable check-then-commit path ---
        check_time = time.time()
        try:
            locked = radar_client.read_coils(0, 1)[0]
        except Exception:
            locked = False

        if not locked:
            return  # rejected: no active radar lock at check time

        try:
            remaining_ms = radar_client.read_registers(9, 1)[0]
        except Exception:
            remaining_ms = 0
        expiry_estimate = check_time + remaining_ms / 1000.0

        time.sleep(ARTIFICIAL_DELAY)  # simulated interlock verification processing
        # <-- the gap: lock is never re-checked after this point

        commit_time = time.time()
        store.set_coil_raw(1, True)
        store.set_register_raw(9, int((check_time * 1000) % 65536))
        store.set_register_raw(10, int((commit_time * 1000) % 65536))

        if commit_time > expiry_estimate:
            store.set_register_raw(11, 1)
            _populate_flag(store)

    elif address == 2 and value:
        # fire command requires arm_state True (checked fresh, not raced --
        # this part is intentionally NOT vulnerable, the bug is isolated to
        # the arm path above)
        armed = store.read_coils(1, 1)[0]
        if armed:
            store.set_coil_raw(2, True)
        # else: silently rejected

    else:
        # disarm, un-fire, or any other coil: commits directly, no interlock
        store.set_coil_raw(address, bool(value))


def register_write_hook(store, address, value):
    # launcher elevation (address 1) is freely writable, cosmetic only
    store.set_register_raw(address, value)


store.coil_write_hook = coil_write_hook
store.register_write_hook = register_write_hook

if __name__ == "__main__":
    srv = ModbusMiniServer("0.0.0.0", PORT, store)
    print(f"plc-battery Modbus TCP listening on :{PORT} "
          f"(radar={RADAR_HOST}:{RADAR_PORT}, delay={ARTIFICIAL_DELAY}s)")
    srv.serve_forever()
