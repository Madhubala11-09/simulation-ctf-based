"""
uas-telemetry/publisher.py
Optional Stage 5 branch: a supporting drone/UAS asset broadcasting
telemetry over MQTT with NO authentication (the mosquitto broker in this
compose stack is configured with allow_anonymous true). This is a common,
realistic IoT/UAS weak-auth pattern -- not a bug in this script, the
"vulnerability" is the broker configuration itself.
"""
import json
import os
import random
import time

import paho.mqtt.client as mqtt

BROKER = os.environ.get("BROKER_HOST", "mosquitto")
PORT = int(os.environ.get("BROKER_PORT", "1883"))

HINT = (
    "Battery arm interlock window is short -- watch the debug timing "
    "registers closely."
)

client = mqtt.Client()
client.connect(BROKER, PORT, 60)
client.loop_start()

while True:
    telemetry = {
        "lat": round(34.05 + random.uniform(-0.01, 0.01), 5),
        "lon": round(-118.25 + random.uniform(-0.01, 0.01), 5),
        "alt_m": round(1200 + random.uniform(-50, 50), 1),
        "ts": time.time(),
    }
    client.publish("uas/telemetry", json.dumps(telemetry))
    client.publish("uas/hint", HINT, retain=True)
    time.sleep(1)
