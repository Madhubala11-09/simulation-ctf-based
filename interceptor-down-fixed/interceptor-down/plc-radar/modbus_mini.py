"""
modbus_mini.py
Minimal Modbus TCP server implementation (subset) for the Interceptor Down CTF.

Supports function codes:
  0x01 Read Coils
  0x03 Read Holding Registers
  0x05 Write Single Coil
  0x06 Write Single Register

This is not a full spec implementation -- it is sufficient for standard
Modbus TCP clients (e.g. pymodbus, or the bundled modbus_client_mini.py)
to read/write coils and holding registers against it.
"""
import socket
import socketserver
import struct
import threading

EXC_ILLEGAL_FUNCTION = 0x01
EXC_ILLEGAL_DATA_ADDRESS = 0x02
EXC_ILLEGAL_DATA_VALUE = 0x03


class DataStore:
    def __init__(self):
        self.lock = threading.RLock()
        self.coils = {}
        self.registers = {}
        # optional hooks: fn(store, address, value) -- implement custom
        # (and deliberately vulnerable) write logic here
        self.coil_write_hook = None
        self.register_write_hook = None

    def read_coils(self, start, qty):
        with self.lock:
            return [bool(self.coils.get(start + i, False)) for i in range(qty)]

    def read_registers(self, start, qty):
        with self.lock:
            return [int(self.registers.get(start + i, 0)) & 0xFFFF for i in range(qty)]

    def write_coil(self, address, value):
        if self.coil_write_hook:
            self.coil_write_hook(self, address, value)
        else:
            with self.lock:
                self.coils[address] = bool(value)

    def write_register(self, address, value):
        if self.register_write_hook:
            self.register_write_hook(self, address, value)
        else:
            with self.lock:
                self.registers[address] = int(value) & 0xFFFF

    def set_coil_raw(self, address, value):
        with self.lock:
            self.coils[address] = bool(value)

    def set_register_raw(self, address, value):
        with self.lock:
            self.registers[address] = int(value) & 0xFFFF


class _Handler(socketserver.BaseRequestHandler):
    def handle(self):
        store = self.server.datastore
        sock = self.request
        sock.settimeout(30)
        buf = b""
        while True:
            try:
                chunk = sock.recv(4096)
            except (socket.timeout, ConnectionResetError, OSError):
                return
            if not chunk:
                return
            buf += chunk
            while len(buf) >= 7:
                length = struct.unpack(">H", buf[4:6])[0]
                total = 6 + length
                if len(buf) < total:
                    break
                frame = buf[:total]
                buf = buf[total:]
                resp = self._process(store, frame)
                if resp:
                    try:
                        sock.sendall(resp)
                    except OSError:
                        return

    def _process(self, store, frame):
        trans_id, proto_id, length, unit_id = struct.unpack(">HHHB", frame[:7])
        pdu = frame[7:]
        if not pdu:
            return None
        func = pdu[0]
        try:
            if func == 0x01:  # Read Coils
                start, qty = struct.unpack(">HH", pdu[1:5])
                bits = store.read_coils(start, qty)
                byte_count = (len(bits) + 7) // 8
                data = bytearray(byte_count)
                for i, b in enumerate(bits):
                    if b:
                        data[i // 8] |= (1 << (i % 8))
                body = struct.pack("B", func) + struct.pack("B", byte_count) + bytes(data)
            elif func == 0x03:  # Read Holding Registers
                start, qty = struct.unpack(">HH", pdu[1:5])
                regs = store.read_registers(start, qty)
                body = struct.pack("B", func) + struct.pack("B", len(regs) * 2)
                for r in regs:
                    body += struct.pack(">H", r)
            elif func == 0x05:  # Write Single Coil
                addr, val = struct.unpack(">HH", pdu[1:5])
                store.write_coil(addr, val == 0xFF00)
                body = pdu  # echo request back, per spec
            elif func == 0x06:  # Write Single Register
                addr, val = struct.unpack(">HH", pdu[1:5])
                store.write_register(addr, val)
                body = pdu  # echo request back, per spec
            else:
                body = struct.pack("B", func | 0x80) + struct.pack("B", EXC_ILLEGAL_FUNCTION)
        except Exception:
            body = struct.pack("B", func | 0x80) + struct.pack("B", EXC_ILLEGAL_DATA_VALUE)

        resp_len = len(body) + 1
        header = struct.pack(">HHHB", trans_id, proto_id, resp_len, unit_id)
        return header + body


class ModbusMiniServer:
    def __init__(self, host, port, datastore):
        self.datastore = datastore
        self._server = socketserver.ThreadingTCPServer((host, port), _Handler)
        self._server.daemon_threads = True
        self._server.datastore = datastore
        self._server.allow_reuse_address = True

    def serve_forever(self):
        self._server.serve_forever()
