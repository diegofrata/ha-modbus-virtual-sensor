#!/usr/bin/env python3
"""
Mock external temp/humidity sensor for a dehumidifier, bridged through an
Elfin EW11 (RS485 <-> Wi-Fi gateway).

How the real hardware talks (from the dehumidifier manual, sec 4.1.9)
--------------------------------------------------------------------
    "External temp. & humidity sensor ... MODBUS RTU RS485
     Address: 13; Baud rate: 9600; Parity: 8N1"

        Name         Add     Code  Bytes  Access      Precision
        Humidity     0000H    03     2    Read Only   0.1%
        Temperature  0001H    03     2    Read Only   0.1

The dehumidifier is the Modbus **master**: it periodically sends function 0x03
(Read Holding Registers) requests addressed to slave **13** and expects the
sensor to answer. The registers are Read Only, so we do NOT write them -- we
impersonate the sensor and *respond* to the controller's polls.

Data path
---------
    dehumidifier (master) --RS485--> EW11 --TCP--> this script (slave #13)
                                          <--TCP-- (our response)
                          <--RS485--

The EW11 transparent socket is a dumb pipe: the master's request bytes arrive
on our TCP socket, and whatever we send back is pushed onto RS485. This is
Modbus **RTU** (address + CRC16), tunnelled over raw TCP -- NOT Modbus/TCP
(there is no MBAP header).

Register values
---------------
    reg 0 (humidity)    = round(humidity * 10)   unsigned   e.g. 55.0% -> 550
    reg 1 (temperature) = round(temp * 10)        signed     e.g. -4.0  -> 0xFFD8

EW11 settings to verify in its web UI
-------------------------------------
  * UART page : Baud 9600, Data 8, Parity None, Stop 1  (must match: 9600 8N1)
  * Socket    : a transparent socket (the 'netp' tab), default TCP Server :8899.
                - netp = TCP Server  -> run this script normally (we connect to it)
                - netp = TCP Client  -> run with --listen (the EW11 connects to us)

No third-party dependencies -- pure standard library.

Examples
--------
  # Verify framing locally with no hardware (simulates a master poll):
  python3 dehumidifier_mock.py --selftest

  # Serve fixed readings to the dehumidifier (EW11 netp = TCP Server):
  python3 dehumidifier_mock.py --temp 23.5 --humidity 55

  # Drift the readings slightly over time, like a live sensor:
  python3 dehumidifier_mock.py --temp 23.5 --humidity 55 --jitter

  # If the EW11 netp socket is a TCP *Client*, listen for it instead:
  python3 dehumidifier_mock.py --listen --temp 23.5 --humidity 55
"""

import argparse
import random
import socket
import sys
import time


# --------------------------------------------------------------------------
# Modbus RTU helpers
# --------------------------------------------------------------------------
def crc16_modbus(data: bytes) -> bytes:
    """Modbus RTU CRC-16, returned low byte first (on-wire order)."""
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


def hexstr(data: bytes) -> str:
    return " ".join(f"{b:02X}" for b in data)


# --------------------------------------------------------------------------
# Sensor state -> register map
# --------------------------------------------------------------------------
class Sensor:
    """Holds the current readings and renders them as Modbus registers."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.temp = cfg.temp
        self.humidity = cfg.humidity

    def registers(self) -> dict:
        return {
            self.cfg.hum_reg: to_register(self.humidity, self.cfg.hum_scale, signed=False),
            self.cfg.temp_reg: to_register(self.temp, self.cfg.temp_scale, signed=True),
        }

    def drift(self):
        self.temp = round(max(-40.0, min(80.0, self.temp + random.uniform(-0.3, 0.3))), 1)
        self.humidity = round(max(0.0, min(100.0, self.humidity + random.uniform(-0.4, 0.4))), 1)


# --------------------------------------------------------------------------
# Request handling
# --------------------------------------------------------------------------
def build_read_response(unit: int, start: int, qty: int, regs: dict) -> bytes:
    """Function 0x03/0x04 response: addr, func, bytecount, data..., CRC."""
    data = b""
    for i in range(qty):
        data += regs.get(start + i, 0).to_bytes(2, "big")
    body = bytes([unit, 0x03, qty * 2]) + data
    return body + crc16_modbus(body)


def build_exception(unit: int, func: int, code: int) -> bytes:
    body = bytes([unit, func | 0x80, code])
    return body + crc16_modbus(body)


def process_buffer(buf: bytearray, sensor: Sensor, send) -> None:
    """
    Pull complete request frames out of `buf`, answer the ones addressed to us,
    and call send(response_bytes) for each reply. Resyncs past noise.

    Only fixed-length read requests (0x03/0x04, 8 bytes) are handled, which is
    all this controller issues.
    """
    cfg = sensor.cfg
    while len(buf) >= 2:
        func = buf[1]
        if func in (0x03, 0x04):
            if len(buf) < 8:
                return  # wait for the rest of the frame
            frame = bytes(buf[:8])
            if crc16_modbus(frame[:6]) != frame[6:8]:
                del buf[0]  # bad CRC -> drop one byte and resync
                continue
            unit = frame[0]
            start = int.from_bytes(frame[2:4], "big")
            qty = int.from_bytes(frame[4:6], "big")
            del buf[:8]
            if unit != cfg.unit:
                continue  # not for us; on a real bus another slave would answer
            regs = sensor.registers()
            resp = build_read_response(cfg.unit, start, qty, regs)
            wanted = ", ".join(f"reg{start + i}={regs.get(start + i, 0)}" for i in range(qty))
            print(f"  RX poll  {hexstr(frame)}   (read {qty} reg @ {start})")
            print(f"  TX reply {hexstr(resp)}   ({wanted}"
                  f"  =>  H={sensor.humidity:.1f}% T={sensor.temp:.1f})")
            send(resp)
        else:
            del buf[0]  # unknown function/noise -> resync


# --------------------------------------------------------------------------
# Connection loops
# --------------------------------------------------------------------------
def enable_keepalive(sock: socket.socket) -> None:
    """
    Turn on TCP keepalive so a silently-dead link (Wi-Fi drop, EW11 power-cycle,
    cable yanked -- where no FIN/RST ever arrives) is detected by the OS and
    surfaces as a socket error, instead of the recv loop hanging forever.

    Probe after ~20s idle, then every 5s, give up after 3 misses (~35s total).
    Option names differ per platform, so each is applied only if present.
    """
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        if hasattr(socket, "TCP_KEEPIDLE"):        # Linux
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 20)
        elif hasattr(socket, "TCP_KEEPALIVE"):     # macOS
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPALIVE, 20)
        if hasattr(socket, "TCP_KEEPINTVL"):
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 5)
        if hasattr(socket, "TCP_KEEPCNT"):
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)
    except OSError:
        pass  # best-effort; reconnect logic still covers us


def serve_socket(sock: socket.socket, sensor: Sensor) -> bool:
    """
    Answer polls on an open socket until the peer closes or the link breaks.
    Returns True if any data was received (i.e. the connection actually worked),
    which the caller uses to decide how fast to reconnect.
    """
    cfg = sensor.cfg
    buf = bytearray()
    sock.settimeout(1.0)
    last_drift = last_rx = time.monotonic()
    received_any = False
    while True:
        try:
            data = sock.recv(256)
            if not data:
                print("  peer closed the connection")
                return received_any
            buf += data
            last_rx = time.monotonic()
            received_any = True
        except socket.timeout:
            pass
        except OSError as e:
            print(f"  link error: {e}")
            return received_any

        now = time.monotonic()
        if cfg.idle_timeout and now - last_rx >= cfg.idle_timeout:
            print(f"  no data for {cfg.idle_timeout:.0f}s; recycling the connection")
            return received_any
        if cfg.jitter and now - last_drift >= 5.0:
            sensor.drift()
            last_drift = now
        try:
            process_buffer(buf, sensor, sock.sendall)
        except OSError as e:
            print(f"  send failed: {e}")
            return received_any


def run_client(sensor: Sensor) -> None:
    """We connect out to the EW11 (its netp socket is a TCP Server)."""
    cfg = sensor.cfg
    delay = cfg.reconnect_delay
    while True:
        healthy = False
        try:
            print(f"connecting to EW11 at {cfg.host}:{cfg.port} ...")
            with socket.create_connection((cfg.host, cfg.port), timeout=cfg.timeout) as s:
                enable_keepalive(s)
                print("connected. waiting for the dehumidifier to poll (Ctrl-C to stop).")
                healthy = serve_socket(s, sensor)
        except KeyboardInterrupt:
            raise
        except Exception as e:  # never let the loop die on an unexpected error
            print(f"  connection problem: {e}")
        if healthy:
            delay = cfg.reconnect_delay  # link was working -> reconnect promptly
        print(f"  reconnecting in {delay:.0f}s ...")
        time.sleep(delay)
        if not healthy:  # device still down -> back off (capped)
            delay = min(cfg.max_reconnect_delay, max(delay, 1.0) * 2)


def run_server(sensor: Sensor) -> None:
    """The EW11 dials in to us (its netp socket is a TCP Client)."""
    cfg = sensor.cfg
    while True:
        try:
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind((cfg.bind, cfg.port))
            srv.listen(1)
            print(f"listening on {cfg.bind}:{cfg.port} for the EW11 (Ctrl-C to stop).")
            with srv:
                while True:
                    conn, addr = srv.accept()
                    print(f"EW11 connected from {addr[0]}:{addr[1]}")
                    enable_keepalive(conn)
                    try:
                        with conn:
                            serve_socket(conn, sensor)
                    except Exception as e:
                        print(f"  connection problem: {e}")
                    print("  waiting for the EW11 to reconnect ...")
        except KeyboardInterrupt:
            raise
        except Exception as e:
            print(f"  listener error: {e}; retrying in {cfg.reconnect_delay:.0f}s ...")
            time.sleep(cfg.reconnect_delay)


def run_selftest(sensor: Sensor) -> None:
    """No hardware: synthesize a master poll and show the response."""
    cfg = sensor.cfg
    # Build what the dehumidifier would send: read 2 regs from slave, start 0.
    req_body = bytes([cfg.unit, 0x03]) + (0).to_bytes(2, "big") + (2).to_bytes(2, "big")
    request = req_body + crc16_modbus(req_body)
    print(f"simulated master poll for slave {cfg.unit}, read 2 regs @ 0:")
    print(f"  (master TX) {hexstr(request)}")
    sent = []
    process_buffer(bytearray(request), sensor, sent.append)
    if not sent:
        print("  !! no response produced -- check --unit matches the request address")
    print("self-test OK" if sent else "self-test FAILED")


def main() -> None:
    p = argparse.ArgumentParser(
        description="Mock RS485 temp/humidity sensor (Modbus slave) behind an Elfin EW11.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--host", default="192.168.68.75", help="EW11 IP address (client mode)")
    p.add_argument("--port", type=int, default=8899, help="EW11 netp TCP port")
    p.add_argument("--listen", action="store_true",
                   help="act as TCP server (use if EW11 netp socket is a TCP Client)")
    p.add_argument("--bind", default="0.0.0.0", help="bind address in --listen mode")
    p.add_argument("--timeout", type=float, default=10.0, help="connect timeout (s)")
    p.add_argument("--reconnect-delay", type=float, default=3.0,
                   help="base retry delay (s); grows on repeated failures")
    p.add_argument("--max-reconnect-delay", type=float, default=30.0,
                   help="cap for the backoff retry delay (s)")
    p.add_argument("--idle-timeout", type=float, default=0.0,
                   help="if >0, drop & reconnect after this many seconds with no "
                        "data (catches a stuck link the EW11 keeps 'open'); set "
                        "above your poll interval, e.g. 120")

    p.add_argument("--unit", type=int, default=13, help="our Modbus slave address")
    p.add_argument("--hum-reg", type=int, default=0, help="humidity register (0x0000)")
    p.add_argument("--temp-reg", type=int, default=1, help="temperature register (0x0001)")
    p.add_argument("--hum-scale", type=int, default=10, help="humidity x scale (0.1%% => 10)")
    p.add_argument("--temp-scale", type=int, default=10, help="temperature x scale (0.1 => 10)")

    p.add_argument("--temp", type=float, default=22.5, help="temperature to report")
    p.add_argument("--humidity", type=float, default=55.0, help="humidity to report")
    p.add_argument("--jitter", action="store_true", help="drift readings slightly every 5s")
    p.add_argument("--selftest", action="store_true",
                   help="no hardware: simulate a poll and print the response")
    cfg = p.parse_args()

    sensor = Sensor(cfg)
    print("=" * 68)
    print(f"Mock sensor = Modbus slave #{cfg.unit}  |  humidity reg {cfg.hum_reg}, "
          f"temperature reg {cfg.temp_reg}")
    print(f"reporting  H={cfg.humidity:.1f}%  T={cfg.temp:.1f}"
          f"{'  (+jitter)' if cfg.jitter else ''}")
    print("=" * 68)

    try:
        if cfg.selftest:
            run_selftest(sensor)
        elif cfg.listen:
            run_server(sensor)
        else:
            run_client(sensor)
    except KeyboardInterrupt:
        print("\nstopped.")


if __name__ == "__main__":
    main()
