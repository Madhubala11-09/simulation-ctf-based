"""
hmi/app.py
Battery control HMI -- Stage 6. Polls both PLCs in a background thread and
serves a live dashboard plus a command console. The final command is
re-validated fresh against the PLCs server-side (never trusts the cached
poll alone, and never trusts the client), so the flag can only be produced
after a genuine TOCTOU violation has actually been recorded by plc-battery.
"""
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, jsonify, render_template_string, request

from modbus_client_mini import ModbusMiniClient

RADAR_HOST = os.environ.get("RADAR_HOST", "plc-radar")
RADAR_PORT = int(os.environ.get("RADAR_PORT", "502"))
BATTERY_HOST = os.environ.get("BATTERY_HOST", "plc-battery")
BATTERY_PORT = int(os.environ.get("BATTERY_PORT", "502"))

radar = ModbusMiniClient(RADAR_HOST, RADAR_PORT)
battery = ModbusMiniClient(BATTERY_HOST, BATTERY_PORT)

app = Flask(__name__)
_state_lock = threading.Lock()
_state = {}


def poll_loop():
    while True:
        try:
            confidence = radar.read_registers(0, 1)[0]
            lock = radar.read_coils(0, 1)[0]
            lock_ms = radar.read_registers(9, 1)[0]
        except Exception:
            confidence, lock, lock_ms = 0, False, 0
        try:
            armed = battery.read_coils(1, 1)[0]
            fired = battery.read_coils(2, 1)[0]
            elevation = battery.read_registers(1, 1)[0]
            race_flag = battery.read_registers(11, 1)[0]
        except Exception:
            armed, fired, elevation, race_flag = False, False, 0, 0

        with _state_lock:
            _state.update(
                {
                    "tracking_confidence": confidence,
                    "radar_lock": lock,
                    "radar_lock_ms_remaining": lock_ms,
                    "battery_armed": armed,
                    "battery_fired": fired,
                    "launcher_elevation": elevation,
                    "race_flag": race_flag,
                    "ts": time.time(),
                }
            )
        time.sleep(1)


@app.route("/api/state")
def api_state():
    with _state_lock:
        return jsonify(dict(_state))


@app.route("/api/command", methods=["POST"])
def api_command():
    payload = request.get_json(silent=True) or {}
    cmd = payload.get("command", "") or request.form.get("command", "")
    if cmd.strip().upper() != "INTERCEPT":
        return jsonify({"ok": False, "message": "Unknown command."}), 400

    # Re-validate fresh server-side state -- never trust the cached poll
    try:
        armed = battery.read_coils(1, 1)[0]
        race_flag = battery.read_registers(11, 1)[0]
    except Exception:
        return jsonify({"ok": False, "message": "PLC unreachable."}), 500

    if armed and race_flag == 1:
        try:
            battery.write_coil(2, True)  # fire
        except Exception:
            pass
        try:
            regs = battery.read_registers(20, 60)  # generous: flags up to ~59 chars
            flag = "".join(chr(r) for r in regs if r != 0)
        except Exception:
            flag = "(error reading flag registers)"
        return jsonify({"ok": True, "message": "INTERCEPT confirmed.", "flag": flag})

    return (
        jsonify(
            {
                "ok": False,
                "message": "Command rejected: battery not armed under a confirmed "
                "interlock bypass.",
            }
        ),
        403,
    )


PAGE = """
<!doctype html>
<html>
<head>
<title>Core Watch -- Interceptor Down HMI</title>
<style>
  body { font-family: monospace; background:#0b0f14; color:#d7e3e8; padding:20px; }
  .panel { border:1px solid #2a3a44; padding:12px; margin-bottom:12px; }
  .ok { color:#5fdc8c; } .bad { color:#e85c5c; }
  input, button { font-family: monospace; padding:6px; }
  h2 { color:#9fd6ff; }
</style>
</head>
<body>
<h2>INTERCEPTOR DOWN -- Battery Control HMI</h2>

<div class="panel">
  <div>Radar tracking confidence: <span id="conf">--</span>%</div>
  <div>Radar lock: <span id="lock">--</span> (ms remaining: <span id="lockms">--</span>)</div>
</div>

<div class="panel">
  <div>Battery armed: <span id="armed">--</span></div>
  <div>Launcher elevation: <span id="elev">--</span></div>
  <div>Interlock integrity: <span id="race">--</span></div>
</div>

<div class="panel">
  <div>Command console:</div>
  <input id="cmdInput" placeholder="type command, e.g. INTERCEPT" size="30">
  <button onclick="sendCmd()">Submit</button>
  <pre id="cmdOut"></pre>
</div>

<script>
async function poll() {
  const r = await fetch('/api/state');
  const s = await r.json();
  document.getElementById('conf').textContent = s.tracking_confidence ?? '--';
  document.getElementById('lock').textContent = s.radar_lock ? 'ACTIVE' : 'inactive';
  document.getElementById('lockms').textContent = s.radar_lock_ms_remaining ?? '--';
  document.getElementById('armed').textContent = s.battery_armed ? 'ARMED' : 'safe';
  document.getElementById('elev').textContent = s.launcher_elevation ?? '--';
  document.getElementById('race').textContent = s.race_flag ? 'VIOLATION DETECTED' : 'nominal';
}
setInterval(poll, 1000);
poll();

async function sendCmd() {
  const cmd = document.getElementById('cmdInput').value;
  const r = await fetch('/api/command', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({command: cmd})
  });
  const j = await r.json();
  document.getElementById('cmdOut').textContent = JSON.stringify(j, null, 2);
}
</script>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(PAGE)


if __name__ == "__main__":
    threading.Thread(target=poll_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=8082)
