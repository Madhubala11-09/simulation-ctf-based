# Add to plc-radar's existing simulation module.
# This is the ENTIRE surface area of the hart-gateway coupling: one read,
# one clamp, one place it's consumed. The TOCTOU race logic itself is
# untouched -- only the lock-hold *duration* value changes.

import json
import os
import time

SHARED_STATE_PATH = os.environ.get("SHARED_STATE_PATH", "/shared/calibration_offset.json")
BASE_LOCK_HOLD_MS = 800
_cache = {"value": BASE_LOCK_HOLD_MS, "mtime": 0}
_POLL_INTERVAL_S = 1.0  # don't stat() the file every tick


def get_lock_hold_ms() -> int:
    """
    Call this wherever plc-radar's existing TOCTOU logic currently uses a
    constant/hardcoded lock-hold duration. Everything else about that
    logic -- when the check happens, when the use happens, the window
    between them -- stays exactly as it was.
    """
    now = time.monotonic()
    if now - _cache["mtime"] < _POLL_INTERVAL_S:
        return _cache["value"]

    try:
        with open(SHARED_STATE_PATH) as f:
            data = json.load(f)
        offset = float(data.get("calibration_offset", 0.0))
        offset = max(-300.0, min(300.0, offset))  # clamp: shifts the window, doesn't remove it
        _cache["value"] = int(BASE_LOCK_HOLD_MS + offset)
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        _cache["value"] = BASE_LOCK_HOLD_MS

    _cache["mtime"] = now
    return _cache["value"]
