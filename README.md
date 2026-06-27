# Push2FLStudio

Use an **Ableton Push 2** as a controller surface for **FL Studio** — including
the color display.

## Why two processes?

The Push 2 has two independent interfaces:

| Part | Transport | Driven by |
|------|-----------|-----------|
| Pads, encoders, buttons, LEDs | MIDI (Note / CC / SysEx) | the **FL Studio script** |
| 960×160 color display | USB **bulk** endpoint, 60 fps, libusb | the **display daemon** |

FL Studio's MIDI scripting runs in a locked-down Python 3.9 sandbox with **no
USB / file / socket access** — only MIDI out. So the display *cannot* be driven
from inside FL Studio. Instead, a small external daemon owns the display over
USB, and the FL script mirrors its state to the daemon over a virtual MIDI bus.

```
Push 2 ──MIDI──▶ FL script ──dispatch──▶ Display-Out script ──▶ virtual MIDI bus
  ▲                  │ (LEDs)                                          │
  └──────────────────┘                                                ▼
  ▲                                                          display daemon
  └──────────────── USB bulk frames (60fps) ────────────────────┘
```

See [docs/architecture.md](docs/architecture.md) for the full picture and
[fl_script/README.md](fl_script/README.md) for the FL Studio wiring.

## Layout

- [fl_script/](fl_script/) — runs **inside FL Studio** (sandboxed, no deps):
  - `device_Push2FLStudio.py` — main controller surface
  - `device_Push2FLStudio_DisplayOut.py` — companion that forwards state to the bus
  - `push2_map.py`, `protocol.py` — control map + SysEx encoder
- [display_daemon/](display_daemon/) — external Python process (pyusb + Pillow):
  - `app.py` / `__main__.py` — entry point and 60 fps render loop
  - `usb_display.py` — Push 2 bulk-transfer protocol (spec-accurate)
  - `renderer.py` — Pillow → RGB565 framebuffer
  - `midi_listener.py`, `protocol.py` — virtual-bus listener + SysEx decoder

## Quick start (display daemon)

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 1) Create the virtual MIDI bus:
#    macOS  — Audio MIDI Setup → IAC Driver → enable a bus
#    Windows — install loopMIDI and add a port
# 2) List MIDI ports the daemon can see:
python -m display_daemon
# 3) Run it against your bus + Push 2 (quit Ableton Live first — it grabs the display):
python -m display_daemon --midi-port "IAC Driver Bus 1"
```

Then install the FL scripts — see [fl_script/README.md](fl_script/README.md).

## Status

Scaffold. The USB display protocol and SysEx bridge are implemented; the FL
control mapping (pad routing, encoder targets, button map, display layout) is
stubbed with `TODO`s and meant to be grown against real hardware.

## Reference

Ableton Push 2 MIDI & Display Interface manual:
https://github.com/Ableton/push-interface
