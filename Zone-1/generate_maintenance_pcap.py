#!/usr/bin/env python3
"""
INTERNAL — NOT FOR PLAYER DISTRIBUTION.

Produces the "legit engineer maintenance session" traffic that becomes the
bundled pcap for the replay-based solve path described in the brief:
  "...or replay control traffic to spin up the conveyors..."

Usage (on your own build box, as root, with tcpdump installed):

    # Terminal 1 — start the target
    CHAL_PORT=5020 CHAL_FLAG='flag{...}' python3 ../server/plc_server.py

    # Terminal 2 — capture
    tcpdump -i lo -w maintenance_session.pcap tcp port 5020

    # Terminal 3 — generate the legit sequence, then stop the capture
    python3 generate_maintenance_pcap.py 127.0.0.1 5020

The resulting maintenance_session.pcap goes into the player-facing challenge
bundle. Players extract the Modbus write requests (function codes 5/6/15/16)
in order and resend them (e.g. with scapy or a small pymodbus/pyModbusTCP
script) against the live target to reach the same running state and pull
the flag — without ever having to guess register semantics themselves.

Note: this deliberately does NOT hardcode the "safety key" register (unused
by current firmware) so the captured traffic doesn't accidentally suggest
it matters.
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

TARGET_SPEED = 900  # inside 850-950 nominal band


def main():
    c = ModbusClient(host=HOST, port=PORT, auto_open=True, auto_close=True)

    # A believable engineer sequence, with small pauses so the pcap doesn't
    # look like a scripted burst.
    c.write_single_coil(COIL_MCC_MASTER_ENABLE, True)
    time.sleep(1.2)
    c.write_single_coil(COIL_ESTOP_TRIPPED, False)
    time.sleep(0.8)
    c.write_single_register(HREG_VFD1_SPEED_SP, TARGET_SPEED)
    time.sleep(0.5)
    c.write_single_register(HREG_VFD2_SPEED_SP, TARGET_SPEED)
    time.sleep(1.0)
    c.write_single_coil(COIL_CONV1_RUN, True)
    time.sleep(0.3)
    c.write_single_coil(COIL_CONV2_RUN, True)

    # Idle a bit longer so the capture also shows the plant settling into
    # nominal run state, in case players want to confirm the target band
    # from behavior rather than register values alone.
    time.sleep(12)
    print("[*] Maintenance sequence complete — stop the capture now.")


if __name__ == "__main__":
    main()
