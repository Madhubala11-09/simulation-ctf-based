#!/usr/bin/env python3
"""
Operation ColdStart — Zone 1: Power Restoration & Conveyor Revival
Simulated Motor Control Center (MCC) PLC exposed over unauthenticated Modbus TCP.

This is the CHALLENGE TARGET. Ship only this file (or its container image) to players.
Do not ship internal/ alongside it.
"""

import os
import time
import threading
from pyModbusTCP.server import ModbusServer

# --------------------------------------------------------------------------
# Address map (all zero-based, matches raw Modbus PDU addressing)
# --------------------------------------------------------------------------
# Coils (FC1 read / FC5,FC15 write)
COIL_MCC_MASTER_ENABLE = 0     # 0=de-energized, 1=energized
COIL_ESTOP_TRIPPED     = 1     # 1=tripped (safe default), 0=cleared
COIL_CONV1_RUN         = 2
COIL_CONV2_RUN         = 3
COIL_DIAG_LAMP         = 4     # cosmetic only

# Holding registers (FC3 read / FC6,FC16 write)
HREG_VFD1_SPEED_SP  = 0        # rpm setpoint, 0-1500
HREG_VFD2_SPEED_SP  = 1
HREG_SAFETY_KEY     = 2        # legacy field, unused by current firmware
HREG_DIAG_CODE      = 3        # read-only-by-convention status code

# Input registers (FC4, read only)
IREG_VFD1_ACTUAL = 0
IREG_VFD2_ACTUAL = 1
IREG_UPTIME      = 2           # seconds since boot, wraps at 65535
IREG_FLAG_BASE   = 10          # 16 registers reserved (32 bytes) for flag ASCII

FLAG_REG_COUNT = 16

# Diagnostic codes surfaced on HREG_DIAG_CODE — standard plant telemetry,
# not a solution hint (any real MCC exposes fault/run state like this).
DIAG_MCC_DISABLED       = 0
DIAG_ESTOP_TRIPPED      = 1
DIAG_IDLE               = 2
DIAG_RAMPING            = 3
DIAG_RUNNING_NOMINAL    = 4
DIAG_RUNNING_OUT_OF_BAND = 5

# Physics / gating parameters
TICK_SECONDS   = 0.5
RAMP_RATE      = 60           # rpm change per tick toward setpoint
BAND_LOW       = 850
BAND_HIGH      = 950
SUSTAIN_TICKS  = 10            # 10 * 0.5s = 5s continuous nominal running
MAX_SETPOINT   = 1500

FLAG = os.environ.get("CHAL_FLAG", "flag{c0nv3y0r_r3v1v4l_pl4c3h0ld3r}")


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _pack_flag_into_registers(flag: str, count: int):
    data = flag.encode("utf-8")
    data = data[: count * 2]
    data = data + b"\x00" * (count * 2 - len(data))
    regs = []
    for i in range(0, len(data), 2):
        regs.append((data[i] << 8) | data[i + 1])
    return regs


class PlantSimulator:
    def __init__(self, server: ModbusServer):
        self.server = server
        self.bank = server.data_bank
        self._sustain_counter = 0
        self._uptime = 0
        self._flag_regs = _pack_flag_into_registers(FLAG, FLAG_REG_COUNT)
        self._zero_regs = [0] * FLAG_REG_COUNT
        self._init_state()

    def _init_state(self):
        self.bank.set_coils(COIL_MCC_MASTER_ENABLE, [False])
        self.bank.set_coils(COIL_ESTOP_TRIPPED, [True])
        self.bank.set_coils(COIL_CONV1_RUN, [False])
        self.bank.set_coils(COIL_CONV2_RUN, [False])
        self.bank.set_coils(COIL_DIAG_LAMP, [False])

        self.bank.set_holding_registers(HREG_VFD1_SPEED_SP, [0])
        self.bank.set_holding_registers(HREG_VFD2_SPEED_SP, [0])
        self.bank.set_holding_registers(HREG_SAFETY_KEY, [0])
        self.bank.set_holding_registers(HREG_DIAG_CODE, [DIAG_MCC_DISABLED])

        self.bank.set_input_registers(IREG_VFD1_ACTUAL, [0])
        self.bank.set_input_registers(IREG_VFD2_ACTUAL, [0])
        self.bank.set_input_registers(IREG_UPTIME, [0])
        self.bank.set_input_registers(IREG_FLAG_BASE, self._zero_regs)

    def _read_coil(self, addr):
        return bool(self.bank.get_coils(addr, 1)[0])

    def _read_hreg(self, addr):
        return self.bank.get_holding_registers(addr, 1)[0]

    def _read_ireg(self, addr):
        return self.bank.get_input_registers(addr, 1)[0]

    def tick(self):
        self._uptime = (self._uptime + 1) % 65536
        self.bank.set_input_registers(IREG_UPTIME, [self._uptime])

        master_on = self._read_coil(COIL_MCC_MASTER_ENABLE)
        estop_tripped = self._read_coil(COIL_ESTOP_TRIPPED)
        conv1_run = self._read_coil(COIL_CONV1_RUN)
        conv2_run = self._read_coil(COIL_CONV2_RUN)

        sp1 = _clamp(self._read_hreg(HREG_VFD1_SPEED_SP), 0, MAX_SETPOINT)
        sp2 = _clamp(self._read_hreg(HREG_VFD2_SPEED_SP), 0, MAX_SETPOINT)

        act1 = self._read_ireg(IREG_VFD1_ACTUAL)
        act2 = self._read_ireg(IREG_VFD2_ACTUAL)

        energized = master_on and (not estop_tripped)

        target1 = sp1 if (energized and conv1_run) else 0
        target2 = sp2 if (energized and conv2_run) else 0

        act1 = self._ramp(act1, target1)
        act2 = self._ramp(act2, target2)

        self.bank.set_input_registers(IREG_VFD1_ACTUAL, [act1])
        self.bank.set_input_registers(IREG_VFD2_ACTUAL, [act2])

        # Diagnostic code
        if not master_on:
            diag = DIAG_MCC_DISABLED
        elif estop_tripped:
            diag = DIAG_ESTOP_TRIPPED
        elif not (conv1_run and conv2_run):
            diag = DIAG_IDLE
        else:
            in_band = (BAND_LOW <= act1 <= BAND_HIGH) and (BAND_LOW <= act2 <= BAND_HIGH)
            settled = (act1 == target1) and (act2 == target2)
            if in_band and settled:
                diag = DIAG_RUNNING_NOMINAL
            elif settled:
                diag = DIAG_RUNNING_OUT_OF_BAND
            else:
                diag = DIAG_RAMPING

        self.bank.set_holding_registers(HREG_DIAG_CODE, [diag])
        self.bank.set_coils(COIL_DIAG_LAMP, [diag == DIAG_RUNNING_NOMINAL])

        # Flag gating: sustained nominal running for SUSTAIN_TICKS in a row
        if diag == DIAG_RUNNING_NOMINAL:
            self._sustain_counter += 1
        else:
            self._sustain_counter = 0

        if self._sustain_counter >= SUSTAIN_TICKS:
            self.bank.set_input_registers(IREG_FLAG_BASE, self._flag_regs)
        else:
            self.bank.set_input_registers(IREG_FLAG_BASE, self._zero_regs)

    def _ramp(self, current, target):
        if current < target:
            return min(current + RAMP_RATE, target)
        elif current > target:
            return max(current - RAMP_RATE, target)
        return current

    def run_forever(self):
        while True:
            self.tick()
            time.sleep(TICK_SECONDS)


def main():
    host = os.environ.get("CHAL_HOST", "0.0.0.0")
    port = int(os.environ.get("CHAL_PORT", "502"))

    server = ModbusServer(host=host, port=port, no_block=True)
    server.start()

    sim = PlantSimulator(server)
    thread = threading.Thread(target=sim.run_forever, daemon=True)
    thread.start()

    print(f"[zone1-modbus] MCC/conveyor PLC simulator listening on {host}:{port}")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        server.stop()


if __name__ == "__main__":
    main()
