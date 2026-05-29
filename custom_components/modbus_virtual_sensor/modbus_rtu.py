"""Pure Modbus RTU helpers — no Home Assistant imports, so they're unit-testable.

This integration plays the Modbus *slave/server*: it answers Read-Holding/Input
register requests (function 0x03 / 0x04) from a polling master, serving values
sourced from Home Assistant. Frames are RTU (address + CRC16), tunnelled over a
raw TCP socket by an RS485<->TCP bridge such as the Elfin EW11.
"""
from __future__ import annotations

READ_FUNCS = (0x03, 0x04)


def crc16(data: bytes) -> bytes:
    """Modbus RTU CRC-16, returned low byte first (the on-wire order)."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return bytes([crc & 0xFF, (crc >> 8) & 0xFF])


def to_register(value: float, scale: int, signed: bool) -> int:
    """Convert a real-world value to a 16-bit register word."""
    raw = int(round(value * scale))
    if signed and raw < 0:
        raw += 0x10000  # two's complement
    if not 0 <= raw <= 0xFFFF:
        raise ValueError(f"value {value} * {scale} = {raw} doesn't fit in 16 bits")
    return raw


def build_read_response(unit: int, start: int, qty: int, regs: dict[int, int]) -> bytes:
    """Build a 0x03 read response: addr, func, byte-count, data..., CRC."""
    data = b""
    for i in range(qty):
        data += regs.get(start + i, 0).to_bytes(2, "big")
    body = bytes([unit, 0x03, qty * 2]) + data
    return body + crc16(body)


def build_exception(unit: int, func: int, code: int) -> bytes:
    """Build a Modbus exception response (func | 0x80, exception code)."""
    body = bytes([unit, func | 0x80, code])
    return body + crc16(body)


def take_request(buf: bytearray) -> dict | None:
    """Pull one complete, CRC-valid read request from the front of ``buf``.

    Mutates ``buf`` in place: consumes the frame's bytes on success, or drops a
    single leading byte to resync past noise. Returns a dict with unit/func/
    start/qty, or None when there isn't a full valid frame yet.

    Only fixed-length read requests (0x03/0x04, 8 bytes) are recognised, which
    is what a master issues when reading a sensor.
    """
    while len(buf) >= 2:
        func = buf[1]
        if func in READ_FUNCS:
            if len(buf) < 8:
                return None  # wait for the rest of the frame
            frame = bytes(buf[:8])
            if crc16(frame[:6]) != frame[6:8]:
                del buf[0]  # bad CRC -> resync
                continue
            req = {
                "unit": frame[0],
                "func": func,
                "start": int.from_bytes(frame[2:4], "big"),
                "qty": int.from_bytes(frame[4:6], "big"),
            }
            del buf[:8]
            return req
        del buf[0]  # unknown function / noise -> resync
    return None
