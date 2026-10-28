"""
engineering-ws/app.py
Simulated engineering workstation config tool -- Stage 3.

Vulnerability: OWASP A01:2021 Broken Access Control, specifically "missing
function-level access control". /signup gives anyone a low-privilege
"guest" session. /api/config is supposed to be admin-only, but the handler
never actually checks session role -- it only checks that the session id
exists at all. The admin session (id 1) is also simply the lowest-numbered
id, so once a player understands the pattern, no credential guessing is
even required.

Deliberately blind-ish: every response is HTTP 200 with the same generic
HTML wrapper, so there's no status-code or error-text signal distinguishing
"you got admin data" from "you didn't" -- the only difference is the
content hidden in an HTML comment, which players must diff/inspect for.
"""
import itertools
import threading

from flask import Flask, make_response, render_template_string, request

app = Flask(__name__)

_lock = threading.Lock()
_next_guest_id = itertools.count(10001)

ADMIN_SESSION_ID = 1
SESSIONS = {ADMIN_SESSION_ID: {"role": "admin"}}

ADMIN_CONFIG_TEXT = (
    "ENGINEERING CONFIG (ADMIN) | "
    "ot-net subnet: 172.20.0.0/24 | "
    "firewall rule: historian(7878) and plc ports reachable only from hmi/ews hosts | "
    "maintenance note: plc-battery interlock verification delay is tunable via "
    "ARTIFICIAL_DELAY env var, currently left at default"
)

GENERIC_PAGE = (
    "<html><body><h3>Engineering Workstation</h3>"
    "<p>Request processed.</p></body></html>"
)

# Previously this app had no GET / route at all, so opening it in a
# browser returned a bare Flask 404 -- easy to mistake for "the service
# doesn't really speak HTTP." It does; it was just missing a landing page.
# This page is cosmetic (legacy internal-tool look) and changes nothing
# about the vulnerability: /signup and /api/config behave exactly as
# before.
LANDING_PAGE = """
<html><head><title>Engineering Workstation -- Config Tool</title>
<style>
  body { font-family: Tahoma, Geneva, sans-serif; background:#d6d3ce; color:#222; margin:0; }
  .titlebar { background:#003366; color:#fff; padding:6px 12px; font-size:13px; }
  .wrap { max-width: 640px; margin: 24px auto; background:#ece9e4; border:1px solid #888;
          box-shadow: 2px 2px 0 #999; padding: 16px; }
  h1 { font-size: 15px; border-bottom: 1px solid #aaa; padding-bottom:4px; }
  button { padding: 5px 14px; font-size: 12px; }
  .note { font-size: 11px; color:#555; margin-top: 14px; }
  #out { margin-top: 12px; font-family: monospace; font-size: 12px; white-space: pre-wrap;
         background:#fff; border:1px inset #999; padding:8px; min-height: 20px; }
</style>
</head>
<body>
<div class="titlebar">Engineering Workstation v1.4 -- Configuration Utility</div>
<div class="wrap">
  <h1>Session</h1>
  <p>No active session. Use Guest Sign-In to obtain a session for this
  tool, then load configuration.</p>
  <button onclick="signup()">Guest Sign-In</button>
  <button onclick="loadConfig()">Load Configuration</button>
  <div id="out"></div>
  <p class="note">Internal tool. Access is logged. Contact Controls
  Engineering for elevated access requests.</p>
</div>
<script>
function signup() {
  fetch('/signup', {method:'POST'}).then(() => {
    document.getElementById('out').textContent = 'Session established.';
  });
}
function loadConfig() {
  fetch('/api/config').then(r => r.text()).then(t => {
    document.getElementById('out').textContent = t;
  });
}
</script>
</body></html>
"""


@app.route("/")
def index():
    return render_template_string(LANDING_PAGE)


@app.route("/signup", methods=["POST"])
def signup():
    with _lock:
        sid = next(_next_guest_id)
        SESSIONS[sid] = {"role": "guest"}
    resp = make_response(GENERIC_PAGE)
    resp.set_cookie("session", str(sid))
    return resp


@app.route("/api/config")
def config():
    sid_raw = request.args.get("session", request.cookies.get("session", ""))
    try:
        sid = int(sid_raw)
    except ValueError:
        sid = -1

    session = SESSIONS.get(sid)
    # BUG: any known session id is accepted here -- role is never checked.
    if session is not None:
        body = GENERIC_PAGE.replace(
            "Request processed.",
            f"Request processed. <!-- {ADMIN_CONFIG_TEXT} -->",
        )
    else:
        body = GENERIC_PAGE.replace(
            "Request processed.",
            "Request processed. <!-- no additional data available for this session        -->",
        )
    return body


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8081)
