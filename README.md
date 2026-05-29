# Modbus Virtual Sensor

A Home Assistant custom integration that **aggregates several HA temperature/humidity
sensors into one value and serves it to a polling Modbus master** over an
RS485↔TCP serial bridge (such as an [Elfin EW11](https://www.hi-flying.com/elfin-ew10-elfin-ew11)).

In other words, it makes Home Assistant act as a **Modbus slave / server** — the
piece the built-in [`modbus`](https://www.home-assistant.io/integrations/modbus/)
integration is missing, since that one is master-only (it *reads* slaves, it can't
*be* one).

> Keywords: Home Assistant Modbus slave, Modbus server, RS485, Elfin EW11,
> expose sensor over Modbus, sensor aggregation/averaging, virtual sensor.

## Why

Some equipment (HVAC, dehumidifiers, PLCs) reads an **external temperature/humidity
sensor over Modbus RTU**: the equipment is the *master* and polls a *slave* sensor.
Instead of buying that sensor, you can feed the equipment readings you already have
in Home Assistant — and, when the equipment conditions several rooms (e.g. a ducted
dehumidifier), feed it the **aggregate** of the sensors in those rooms.

## How it works

```
HA sensors ──► [aggregate: mean/median/min/max] ──► Modbus Virtual Sensor (slave)
                                                          │  TCP
                                                          ▼
                                            RS485↔TCP bridge (EW11, etc.)
                                                          │  RS485 (Modbus RTU)
                                                          ▼
                                              master device (polls the slave)
```

The master polls with function `0x03` (Read Holding Registers); the integration
answers with the current aggregated values. Frames are Modbus **RTU** (address +
CRC16) tunnelled over the bridge's transparent TCP socket.

## Features

- Select **multiple** temperature and humidity source entities; unavailable ones are
  skipped automatically, and the last good value is held if they all drop out.
- Per-quantity **aggregation**: `mean`, `median`, `min`, or `max`
  (e.g. chase the *wettest* room with `max` humidity).
- Configurable **slave address, register map, scaling and sign** (defaults: humidity
  register `0`, temperature register `1`, ×10 for 0.1 resolution, temperature signed).
- Temperature sources in °F are converted to °C before aggregating.
- **Resilient connection**: TCP keepalive to detect dead links, capped exponential
  reconnect backoff, survives bridge reboots and Wi-Fi drops.
- Diagnostic entities: connection status, reported temperature/humidity, poll count,
  last poll time. Fully UI-configured (config + options flow).

## Installation

### HACS (custom repository)
1. HACS → ⋮ → **Custom repositories**.
2. Add this repo's URL, category **Integration**.
3. Install **Modbus Virtual Sensor**, then restart Home Assistant.
4. **Settings → Devices & Services → Add Integration → Modbus Virtual Sensor**.

### Manual
Copy `custom_components/modbus_virtual_sensor/` into your HA `config/custom_components/`
directory and restart.

## Configuration

Set up entirely in the UI:

| Field | Meaning |
|---|---|
| Name | Friendly name / device name |
| Bridge IP / Port | The RS485↔TCP bridge's TCP-server socket (EW11 `netp`, default `8899`) |
| Modbus slave address | The address the master polls (e.g. `13`) |
| Temperature / Humidity sources | The HA sensors to aggregate |

Aggregation methods and the register mapping/scaling live under the integration's
**Configure** (options) dialog and can be changed anytime.

## Example: ducted dehumidifier external sensor

A dehumidifier with *"External temp & humidity sensor, MODBUS RTU RS485, Address 13,
9600 8N1, Humidity 0x0000, Temperature 0x0001, 0.1 resolution"* — set slave address
`13`, humidity register `0`, temperature register `1`, scale `10`. Pick the room
sensors in the ducted zones; use `mean` temperature and (optionally) `max` humidity.

**Bridge (EW11) settings:** UART `9600 8N1`, Flow Control `Half Duplex`, UART Protocol
`Modbus`; a transparent `netp` socket set to **TCP Server** on `8899`, Route `Uart`.

## Standalone tester

`dehumidifier_mock.py` (repo root) is a dependency-free CLI that runs the same Modbus
slave logic outside Home Assistant — handy for verifying wiring and framing before
installing the integration. `python3 dehumidifier_mock.py --selftest`.

## Disclaimer

Community project, not affiliated with Hi-Flying/Elfin or any equipment vendor. Use at
your own risk; verify your device's register map against its manual.
