# FL Studio scripts — install & wiring

These scripts run **inside FL Studio's** sandboxed Python. They use only
built-ins + the FL API modules — no `pip install` here.

## 1. Install

Copy this whole folder into FL Studio's MIDI scripts directory:

- **Windows:** `Documents\Image-Line\FL Studio\Settings\Hardware\Push2FLStudio\`
- **macOS:** `~/Documents/Image-Line/FL Studio/Settings/Hardware/Push2FLStudio/`

Each `device_*.py` file becomes a selectable controller type in FL Studio.

## 2. Create the virtual MIDI bus

The display daemon needs a MIDI bus to receive state on:

- **macOS:** Audio MIDI Setup → *Window → Show MIDI Studio* → double-click
  **IAC Driver** → tick *Device is online* → add a bus (e.g. "IAC Driver Bus 1").
- **Windows:** install **loopMIDI**, add a port (e.g. "Push2Display").

## 3. Assign the controllers (Options → MIDI Settings)

You wire up **two** controllers:

### a) Push 2 FL Studio (main)
- Find **Ableton Push 2** (its "Live Port" / port 1) in both the input and
  output lists. Enable input and output.
- Set its **controller type** to **"Push 2 FL Studio"**.

### b) Push 2 Display Out (companion)
- Find your **virtual bus** (IAC / loopMIDI) in the output list. Enable it.
- Set its **controller type** to **"Push 2 Display Out"**.
- This script declares `# receiveFrom=Push 2 FL Studio`, so the main script's
  `device.dispatch(0, …)` reaches it. Make sure both are enabled.

> The companion script's **output** must be the virtual bus the daemon listens
> on. Its input doesn't matter (it only forwards dispatched SysEx).

## 4. Run the daemon

```bash
python -m display_daemon --midi-port "IAC Driver Bus 1"   # or your loopMIDI port
```

Quit Ableton Live first if it's open — it claims the Push 2 display over USB.

## Mapping work (the TODOs)

`device_Push2FLStudio.py` ships with placeholder behavior:
- Pads light green while held (no FL routing yet).
- Encoders 1–8 nudge mixer track volumes.
- Play / Record / Metronome buttons mapped.

Grow these against the control map in `push2_map.py`. Verify button CCs against
the [Ableton manual](https://github.com/Ableton/push-interface) for your firmware.
