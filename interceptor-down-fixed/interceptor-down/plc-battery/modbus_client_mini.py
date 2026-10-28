"""
modbus_client_mini.py
Minimal Modbus TCP client (subset) -- used server-to-server here (plc-battery
querying plc-radar's lock state) and also handy for the HMI poller and
reference solve scripts. Stdlib only, no external dependency.
"""
import socket
import struct


class ModbusMiniClient:
    def __init__(self, host, port, timeout=5):
        self.host = host
        self.port = port
        self.timeout = timeout
        self._tid = 0

    def _txn(self, func_body):
        self._tid = (self._tid + 1) % 0xFFFF
        header = struct.pack(">HHHB", self._tid, 0, len(func_body) + 1, 1)
        frame = header + func_body
        with socket.create_connection((self.host, self.port), timeout=self.timeout) as s:
            s.sendall(frame)
            resp = s.recv(4096)
        return resp[7:]  # strip MBAP header

    def read_coils(self, start, qty):
        body = struct.pack(">BHH", 0x01, start, qty)
        resp = self._txn(body)
        if resp[0] & 0x80:
            raise RuntimeError(f"Modbus exception {resp[1]}")
        byte_count = resp[1]
        data = resp[2:2 + byte_count]
        bits = []
        for i in range(qty):
            bits.append(bool(data[i // 8] & (1 << (i % 8))))
        return bits

    def read_registers(self, start, qty):
        body = struct.pack(">BHH", 0x03, start, qty)
        resp = self._txn(body)
        if resp[0] & 0x80:
            raise RuntimeError(f"Modbus exception {resp[1]}")
        byte_count = resp[1]
        regs = []
        for i in range(byte_count // 2):
            regs.append(struct.unpack(">H", resp[2 + i * 2:4 + i * 2])[0])
        return regs

    def write_coil(self, addr, value):
        val = 0xFF00 if value else 0x0000
        body = struct.pack(">BHH", 0x05, addr, val)
        self._txn(body)

    def write_register(self, addr, value):
        body = struct.pack(">BHH", 0x06, addr, value & 0xFFFF)
        self._txn(body)
