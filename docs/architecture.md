# Architecture

## The constraint that shapes everything

FL Studio's MIDI Controller Scripting runs in a **stripped-down Python 3.9
interpreter** that exposes only safe built-ins plus the FL API modules
(`device`, `mixer`, `channels`, `transport`, `playlist`, `ui`, …). It has **no**
`usb`, `ctypes`, `socket`, `os`, or file I/O.

The Push 2 color display is **not** a MIDI device. It is a USB **bulk OUT
endpoint** that expects ~327 KB frames at 60 fps and requires libusb. There is
therefore no way to render to the display from within the FL sandbox — its only
outbound channel is MIDI.

**Conclusion:** the project is necessarily two processes that talk over MIDI.

## Components

### 1. FL Studio script (`fl_script/`)
- Receives Push 2 MIDI (pads → notes, encoders → params, buttons → transport).
- Drives Push 2 LEDs via `device.midiOutMsg` / `midiOutSysex` (output port = Push 2).
- Mirrors FL state (transport, track names, meters, selected track, params) to
  the display daemon as SysEx.

A single script writes MIDI to exactly one output port. Since that port is the
Push 2 (for LEDs), a **companion script** (`device_Push2FLStudio_DisplayOut.py`)
owns the virtual-bus output. The main script hands it SysEx via
`device.dispatch(...)`; the companion re-emits it with `device.midiOutSysex`.

### 2. Display daemon (`display_daemon/`)
- `midi_listener.py` listens on the virtual bus, decodes state SysEx into a
  `DisplayModel`.
- `renderer.py` draws the model (Pillow) and converts to the padded RGB565,
  scrambled wire buffer.
- `usb_display.py` pushes header + frame to bulk endpoint `0x01` at 60 fps.
  (The panel blanks after 2 s of silence, so we render continuously.)

## The state protocol

Custom SysEx, `F0 7D <type> <payload…> F7` (`0x7D` = non-commercial id). All
payload bytes are 7-bit. Defined twice — `fl_script/protocol.py` (encoder) and
`display_daemon/protocol.py` (decoder) — because the two halves cannot share an
import. **Keep them in sync.**

| Type | Name | Payload |
|------|------|---------|
| `0x01` | transport | playing, recording, bpm_hi7, bpm_lo7 |
| `0x02` | selected track | index |
| `0x10` | track name | index, ascii… |
| `0x11` | track level | index, 0..127 |
| `0x20` | param | encoder, 0..127, ascii… |
| `0x7F` | clear | — |

## Display wire format (from the Ableton spec)

- USB IDs: vendor `0x2982`, product `0x1967`; bulk OUT endpoint `0x01`.
- Frame header: `FF CC AA 88` + 12 × `00`.
- 160 lines × 1024-pixel padded buffer (960 visible) × 2 bytes = **327,680 bytes**.
- Pixel: RGB565 little-endian (`(r>>3)<<11 | (g>>2)<<5 | (b>>3)`).
- Each 32-bit word XOR'd with `0xFFE7F3E7` (bytes `E7 F3 E7 FF`) before send.

## Known open questions / next steps

- Confirm exact button CCs against the manual for your firmware.
- Decide pad behavior (drum pads vs step sequencer vs note grid).
- Decide encoder targets (mixer vs focused plugin params) and add pickup/feedback.
- Replace the placeholder display layout with the real 8-strip UI + fonts.
- Verify RGB565 bit order on hardware (some implementations differ).
