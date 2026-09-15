# Zone 1 — Internal Solution Notes (do not distribute)

## Address map
- Coils: 0=MCC master enable, 1=E-STOP (1=tripped), 2=Conv1 run, 3=Conv2 run, 4=diag lamp (cosmetic)
- Holding regs: 0=VFD1 speed setpoint, 1=VFD2 speed setpoint, 2=unused legacy field (decoy), 3=diag code (read-only by convention)
- Input regs: 0=VFD1 actual speed, 1=VFD2 actual speed, 2=uptime, 10-25=flag ASCII (zero until unlocked)

## Diag codes
0 disabled · 1 estop tripped · 2 idle · 3 ramping · 4 running nominal · 5 running out of band

## Intended solve (active path)
1. Enumerate coils/holding/input registers — everything is unauthenticated.
2. Write coil 0 = 1 (master enable).
3. Write coil 1 = 0 (clear E-STOP).
4. Write holding reg 0 and 1 to a value in [850, 950] (e.g. 900).
5. Write coil 2 = 1 and coil 3 = 1 (start both conveyors).
6. Poll input registers 10-25 — flag appears once diag code holds at 4
   (running nominal) for 5 continuous seconds. Breaking any condition
   resets the sustain counter, so out-of-band setpoints or a re-tripped
   E-STOP will stall progress without corrupting state.

## Intended solve (replay path)
1. Extract Modbus write PDUs (function codes 5/6/15/16) from
   `maintenance_session.pcap`, in order.
2. Resend the same requests against the live target (scapy raw replay
   won't work due to TCP handshake/seq numbers — players need to open
   a fresh TCP session and reissue the same PDU payloads, which is the
   intended "protocol replay" skill test, not literal pcap replay).
3. Same gating as above applies once requests land.

## Deliberate misdirection
- Holding register 2 ("safety key") is legacy/unused. It reads back
  whatever was last written but has zero effect on any logic. Included
  to bait blind fuzzing/brute-force down a dead end.
- Coil 4 (diag lamp) is purely cosmetic, mirrors diag==4, easy to mistake
  for something that needs to be set manually.
- Diag codes are standard operational telemetry (any real MCC exposes
  fault/run state on an HMI) — not a hint, but they do help players
  distinguish "wrong values" from "right values, not held long enough."

## Difficulty tuning knobs
`BAND_LOW`/`BAND_HIGH` (currently 850-950) and `SUSTAIN_TICKS` (currently
10 = 5s) in `server/plc_server.py` control how forgiving the band and
hold-time are. Widen the band or shorten sustain time for an easier
zone; the reverse for a harder one.

## Verified
`internal/solve.py` reproduces the active-exploitation path end-to-end
against a live instance and confirms flag delivery.
