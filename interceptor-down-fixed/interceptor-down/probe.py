
import socket

HOST = "172.20.0.1"
PORT = 7878

probes = [
    b"\x00",
    b"\x00\x00",
    b"\x01\x00",
    b"\x00\x00\x00\x00",
    b"HELP",
]

for payload in probes:
    print(f"\nSending: {payload.hex(' ')}")

    try:
        with socket.create_connection((HOST, PORT), timeout=3) as s:
            s.settimeout(1)
            s.sendall(payload)

            try:
                response = s.recv(4096)
                if response:
                    print("Received:", response.hex(" "))
                    print("ASCII:", repr(response))
                else:
                    print("Server closed the connection.")
            except socket.timeout:
                print("No response before timeout.")

    except OSError as e:
        print("Connection error:", e)
