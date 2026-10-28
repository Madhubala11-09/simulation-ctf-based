# Interceptor Down

An OT/ICS CTF chain: breach a defense contractor's IT perimeter, pivot
through an undocumented historian protocol and a broken-access-control
engineering workstation, then win a cross-PLC TOCTOU race condition to
arm an interceptor battery without a valid radar lock, and finish the
chain at a live HMI.

Fully self-contained Docker Compose build. No GRFICS, no ESP32 --
every service here is custom Python, tested end-to-end (see
`solutions/solve.py` and `solutions/test_toctou.py`).

## Running it

```bash
docker compose up --build
```

Services and their default host ports (see the hardening note in
`docker-compose.yml` before running this for an actual multi-team event
-- as shipped, every port is published to the host for easy local
testing, which defeats the net=work-segmentation lesson):

| Service | Port | Role |
|---|---|---|
| it-foothold | 8080 | Stage 1 -- weak-auth web login |
| historian | 7878 | Stage 2 -- custom binary protocol, info leak |
| engineering-ws | 8081 | Stage 3 -- broken access control (blind-ish) |
| plc-radar | 5020 | Stage 4a -- Modbus TCP, tracking/lock simulation |
| plc-battery | 5021 | Stage 4b -- Modbus TCP, **TOCTOU vulnerability** |
| hmi | 8082 | Stage 6 -- dashboard + final command console |
| mosquitto / uas-publisher | 1883 | Stage 5 (optional) -- unauthenticated MQTT |

## Attack chain

```
[Stage 1: it-foothold]  admin/admin123 -> reveals OT host list
        |
        v
[Stage 2: historian]  custom binary protocol (see historian/server.py
        |              docstring for the frame format) -> leaks network
        |              map, register map, and a hint that both PLCs carry
        |              undocumented debug registers
        v
[Stage 3: engineering-ws]  /signup for a guest session, then /api/config
        |                  accepts ANY known session id (role is never
        |                  checked) -- confirms routing/interlock details
        v
[Stage 4a: plc-radar]  Modbus TCP. Tracking confidence climbs on its own;
        |               once it crosses 90% a lock window opens for a few
        |               seconds, then auto-expires and the cycle repeats.
        v
[Stage 4b: plc-battery]  Modbus TCP. Arming (Coil 1 / 00002) requires
        |                 plc-radar's lock to be active. The handler checks
        |                 the lock, sleeps briefly ("interlock verification"),
        |                 then commits -- without re-checking. A write timed
        |                 (or burst-raced) right at the lock's expiry
        |                 boundary lands its commit after expiry, which sets
        |                 race_flag server-side. THIS IS THE VULNERABILITY.
        v
[Stage 5: uas-telemetry]  optional -- unauthenticated MQTT feed, flavor/hint
        |
        v
[Stage 6: hmi]  submit "INTERCEPT" via the command console. The backend
                 re-checks the PLCs fresh (never trusts its own cache or
                 the client) and only returns the flag if armed == True
                 AND race_flag == 1.
```

## The vulnerability, precisely

`plc-battery/server.py`, `coil_write_hook()`, arming path:

1. **Check**: read plc-radar's lock coil + its remaining-ms debug register.
2. Sleep `ARTIFICIAL_DELAY` seconds (default 0.25s) -- simulates "interlock
   verification processing."
3. **Commit**: write the arm coil. The lock is never re-checked here.

If the commit timestamp falls after the lock's actual expiry (estimated
from the Step-1 reading), `race_flag` is set and the flag registers
populate. A plain `unlock -> immediate write` sequence does **not**
trigger this -- both check and commit land comfortably inside the lock
window, which is correct, intended behavior. Only a write timed at the
boundary (or a burst of writes straddling it) can win. This is tested
explicitly in `solutions/test_toctou.py` (asserts a legitimate immediate
write never sets the flag, then asserts a boundary-timed/burst write
does).

## Difficulty tuning

| Knob | Where | Easier | Harder |
|---|---|---|---|
| `ARTIFICIAL_DELAY` | plc-battery env | 0.4-0.5s | 0.05-0.1s |
| `LOCK_HOLD_SECONDS` | plc-radar env | 5-6s | 1.5-2s |
| Debug register visibility | historian Stage-2 text | mention it directly | remove the hint, force register-range scanning |
| Historian checksum | historian/server.py | document algorithm in challenge brief | players must RE it from a sample capture only |
| EWS session ids | engineering-ws/app.py | admin id obvious (1) | randomize/obscure admin id, require brute-forcing a narrow range |

## Testing

```bash
# unit-level: just the TOCTOU logic against plc-radar/plc-battery
python3 solutions/test_toctou.py

# full chain, against docker compose (or locally-run services on the
# same ports)
python3 solutions/solve.py
```

Both were run against this exact codebase before delivery; the full
chain (historian -> EWS -> TOCTOU race -> HMI flag) completed
successfully end to end.

## Flag

Set via the `FLAG` environment variable on `plc-battery` in
`docker-compose.yml` (default is a placeholder -- change it before
running a real event). Flag length isn't hard-capped in practice, but
the register range reserved for it (40020-40079, 60 registers) caps it
at 59 characters -- stay under that.
