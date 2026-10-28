"""
plc-radar/server.py
Simulated radar/tracking PLC for the "Interceptor Down" CTF.

Modbus TCP map (0-based protocol addresses; add 40001/00001 for the
human-facing tag names used in challenge documentation):

  Holding Register 0  (40001)  tracking_confidence   0-100, read-only
  Coil             0  (00001)  lock_state            read-only, set internally
  Holding Register 9  (40010)  lock_ms_remaining      UNDOCUMENTED debug register --
                                                       not in the leaked tag table,
                                                       discoverable via register
                                                       scanning. Leaks precise
                                                       timing used to win the
                                                       plc-battery TOCTOU race.

Behavior: tracking_confidence climbs on its own. Once it reaches
LOCK_THRESHOLD, lock_state flips True and holds for LOCK_HOLD_SECONDS,
then automatically drops (simulating signal loss / re-acquisition cycle)
and confidence resets partway down, so the lock window recurs periodically
-- players get repeated attempts rather than one single shot.
"""
import os
import random
import threading
import time

from modbus_mini import DataStore, ModbusMiniServer

PORT = int(os.environ.get("PORT", "502"))
LOCK_THRESHOLD = 90
LOCK_HOLD_SECONDS = float(os.environ.get("LOCK_HOLD_SECONDS", "4.0"))
CONFIDENCE_RESET = 65

store = DataStore()
store.set_register_raw(0, 20)   # 40001 tracking_confidence
store.set_coil_raw(0, False)    # 00001 lock_state
store.set_register_raw(9, 0)    # 40010 debug: lock ms remaining

_lock_expiry = 0.0


def sim_loop():
    global _lock_expiry
    while True:
        time.sleep(0.25)
        conf = store.read_registers(0, 1)[0]
        locked = store.read_coils(0, 1)[0]
        now = time.time()
        if locked:
            remaining_ms = max(0, int((_lock_expiry - now) * 1000))
            store.set_register_raw(9, min(remaining_ms, 65535))
            if now >= _lock_expiry:
                store.set_coil_raw(0, False)
                store.set_register_raw(0, CONFIDENCE_RESET)
                store.set_register_raw(9, 0)
        else:
            conf = min(100, conf + random.randint(2, 6))
            store.set_register_raw(0, conf)
            if conf >= LOCK_THRESHOLD:
                store.set_coil_raw(0, True)
                _lock_expiry = now + LOCK_HOLD_SECONDS
                store.set_register_raw(9, int(LOCK_HOLD_SECONDS * 1000))


if __name__ == "__main__":
    threading.Thread(target=sim_loop, daemon=True).start()
    srv = ModbusMiniServer("0.0.0.0", PORT, store)
    print(f"plc-radar Modbus TCP listening on :{PORT} "
          f"(lock threshold={LOCK_THRESHOLD}%, hold={LOCK_HOLD_SECONDS}s)")
    srv.serve_forever()
