"""
it-foothold/app.py
Thin, intentionally weak IT-perimeter gate -- Stage 1.

This is deliberately NOT where the challenge's difficulty lives (per the
design: don't over-invest in the IT stage). Default/weak credentials grant
a session that reveals the OT host list -- just enough to point players at
Stages 2/3. Restyled as a missile-defense installation's employee portal
for narrative presentation; the actual login logic (admin/admin123) is
unchanged.
"""
from flask import Flask, render_template_string, request, send_from_directory

app = Flask(__name__, static_folder="static")

USERS = {"admin": "admin123"}

BASE_NAME = "Site 14 -- Longreach Air Defense Station"
BASE_MOTTO = "Vigilance Aloft"

PAGE_STYLE = """
<style>
  * { box-sizing: border-box; }
  body {
    margin: 0; font-family: 'Courier New', monospace;
    background: radial-gradient(circle at top, #10171c 0%, #06090c 70%);
    color: #c9d6dc; min-height: 100vh;
  }
  .topbar {
    background:#0a1014; border-bottom: 2px solid #3a5a66;
    padding: 14px 28px; display:flex; justify-content:space-between; align-items:center;
  }
  .topbar .crest { color:#6fb7cf; font-weight:bold; letter-spacing:2px; }
  .topbar .tag { color:#5a6b72; font-size: 12px; }
  .wrap { max-width: 920px; margin: 0 auto; padding: 40px 20px; }
  .columns { display:flex; gap: 32px; flex-wrap: wrap; }
  .card {
    background: #0d1418; border: 1px solid #253942; border-radius: 4px;
    padding: 24px; flex: 1; min-width: 280px;
  }
  h1 { color:#8fd4f2; font-size: 20px; letter-spacing: 1px; margin-top:0; }
  h2 { color:#8fd4f2; font-size: 16px; border-bottom: 1px solid #253942; padding-bottom:8px; }
  .legacy { color:#8a9aa1; font-size: 13px; line-height: 1.6; }
  label { display:block; margin: 14px 0 4px; font-size: 13px; color:#9fb0b6; }
  input[type=text], input[type=password] {
    width: 100%; padding: 8px; background:#060a0c; border:1px solid #2d434d;
    color:#d7e3e8; font-family: inherit;
  }
  button {
    margin-top: 18px; width: 100%; padding: 10px; background:#1c3540;
    border: 1px solid #3a5a66; color:#bfe3f2; cursor:pointer; letter-spacing: 1px;
  }
  button:hover { background:#274654; }
  .footer { text-align:center; color:#45535a; font-size: 11px; margin-top: 40px; }
  .err { color:#e88; margin-top: 10px; font-size: 13px; }
  .stamp {
    display:inline-block; border: 1px solid #4a6; color:#7c9; padding: 2px 8px;
    font-size: 10px; letter-spacing: 1px; margin-bottom: 8px;
  }
</style>
"""

LOGIN_PAGE = """
<html><head><title>{{base_name}} -- Employee Portal</title>""" + PAGE_STYLE + """</head>
<body>
<div class="topbar">
  <div class="crest">{{base_name}}</div>
  <div class="tag">AUTHORIZED PERSONNEL ONLY -- Network Access Log Monitored</div>
</div>
<div class="wrap">
  <div class="columns">
    <div class="card">
      <span class="stamp">UNCLASSIFIED</span>
      <h2>Station History</h2>
      <p class="legacy">
        Commissioned in 1978 as a coastal early-warning relay, Site 14 was
        reclassified as an integrated air-defense installation in 2003
        following the Longreach Modernization Program. The station now
        operates a networked tracking-and-intercept battery alongside
        legacy radar infrastructure retained for redundancy.
      </p>
      <p class="legacy">
        Station motto, adopted 1981: <em>&ldquo;{{base_motto}}&rdquo;</em>.
        The extranet portal was introduced in 2019 to support remote
        contractor access for scheduled maintenance windows.
      </p>
    </div>
    <div class="card">
      <h1>Employee &amp; Contractor Login</h1>
      <form method="POST">
        <label>Username</label>
        <input type="text" name="username" autocomplete="username">
        <label>Password</label>
        <input type="password" name="password" autocomplete="current-password">
        <button type="submit">AUTHENTICATE</button>
      </form>
      {% if error %}<div class="err">{{error}}</div>{% endif %}
    </div>
  </div>
  <div class="footer">
    {{base_name}} Extranet &middot; Form submissions are logged for security review &middot; v2.3.1
  </div>
</div>
</body></html>
"""

DASHBOARD_PAGE = """
<html><head><title>{{base_name}} -- Dashboard</title>""" + PAGE_STYLE + """</head>
<body>
<div class="topbar">
  <div class="crest">{{base_name}}</div>
  <div class="tag">SESSION: {{user}}</div>
</div>
<div class="wrap">
  <div class="card">
    <span class="stamp">UNCLASSIFIED</span>
    <h2>Network Operations Summary</h2>
    <p class="legacy">OT network range: 172.20.0.0/24</p>
    <p class="legacy">Known OT hosts on record: historian service, engineering
    workstation. Exact addresses rotate per DHCP lease -- consult the
    historian's network-map query for current values.</p>
    <p class="legacy">For maintenance history and open engineering items,
    see the internal notes archive (link intentionally omitted from this
    page -- check site policy documents).</p>
  </div>
</div>
</body></html>
"""

INTERNAL_NOTES_STYLE = PAGE_STYLE
INTERNAL_NOTES_PAGE = """
<html><head><title>Engineering Notes -- Internal</title>""" + INTERNAL_NOTES_STYLE + """</head>
<body>
<div class="topbar">
  <div class="crest">{{base_name}}</div>
  <div class="tag">INTERNAL DISTRIBUTION ONLY</div>
</div>
<div class="wrap">
  <div class="card">
    <h1>ENGINEERING NOTES</h1>
    <p class="legacy">
      <strong>System:</strong> Interceptor Control System<br>
      <strong>Department:</strong> Controls &amp; Instrumentation<br>
      <strong>Document Type:</strong> Internal Maintenance Log<br>
      <strong>Status:</strong> Open Items Pending Review
    </p>

    <h2>01 &mdash; Historian Maintenance</h2>
    <p class="legacy">
      Routine maintenance has been completed. Diagnostic queries continue
      to return additional context beyond the standard operator summary.
      The existing reporting profile remains unchanged pending the next
      review.
    </p>

    <h2>02 &mdash; Engineering Workstation</h2>
    <p class="legacy">
      The configuration-interface review remains open. Previous audit
      action items have been carried forward into the current maintenance
      cycle. No closure date has been confirmed.
    </p>

    <h2>03 &mdash; Arm Sequence Firmware</h2>
    <p class="legacy">
      The latest firmware passed functional testing. Event logs continue
      to show minor variations between command receipt and interlock
      confirmation. Further timing validation has been deferred to the
      next maintenance window.
    </p>

    <p class="legacy"><strong>Maintenance Reminder:</strong> Outstanding
    audit items should be reviewed before the next scheduled system
    validation.</p>

    <p class="legacy" style="color:#5a6b72; font-size: 11px;">
      Document maintained by Controls Engineering. Internal distribution
      only.
    </p>
  </div>
</div>
</body></html>
"""


@app.route("/robots.txt")
def robots():
    return send_from_directory(app.static_folder, "robots.txt")


@app.route("/internal-notes")
def internal_notes():
    # disclosed via robots.txt's Disallow entry -- no auth required to view
    # (the weakness here is pure "security through obscurity": the
    # disallowed path is a roadmap, not a lock). Content is deliberately
    # vague/corporate rather than explicit -- it hints at where to look
    # (historian, engineering workstation, arm-sequence timing) without
    # spelling out register addresses or exact vulnerabilities.
    return render_template_string(INTERNAL_NOTES_PAGE, base_name=BASE_NAME)


@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form.get("username", "")
        p = request.form.get("password", "")
        if USERS.get(u) == p:
            return render_template_string(
                DASHBOARD_PAGE, user=u, base_name=BASE_NAME
            )
        return render_template_string(
            LOGIN_PAGE,
            base_name=BASE_NAME,
            base_motto=BASE_MOTTO,
            error="Authentication failed. Attempt has been logged.",
        ), 401
    return render_template_string(
        LOGIN_PAGE, base_name=BASE_NAME, base_motto=BASE_MOTTO, error=None
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
