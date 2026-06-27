"""Display daemon entry point.

Owns the Push 2 display USB endpoint, listens to the virtual MIDI port for
state from the FL Studio script, and pushes frames at ~60 fps (the panel
blanks after 2 s of silence, so we render continuously even when idle).
"""

from __future__ import annotations

import argparse
import math
import time

import mido
import usb.core

from . import pad_text, push2_midi, renderer
from .midi_listener import MidiStateListener
from .monitor import MonitorState
from .protocol import DisplayModel
from .usb_display import Push2Display, Push2DisplayNotFound

FRAME_INTERVAL = 1.0 / 60.0

# Vivid solid colors (Push 2 default palette indices) cycled one per fill.
_COLORS = [127, 9, 124, 126, 37, 125, 49, 22]

_FILL_FRAMES = 40    # frames to fill the whole grid (ease-in)
_HOLD_FRAMES = 5     # hold the full grid before switching color
_CYCLE_FRAMES = _FILL_FRAMES + _HOLD_FRAMES


def _fill_order():
    """Pad notes ordered diagonally from the bottom-left corner (flow-in)."""
    order = []
    for dist in range(push2_midi.PAD_ROWS + push2_midi.PAD_COLS - 1):
        for row in range(push2_midi.PAD_ROWS):
            col = dist - row
            if 0 <= col < push2_midi.PAD_COLS:
                order.append(push2_midi.pad_note(row, col))
    return order


_FILL_ORDER = _fill_order()  # 64 notes
_TOTAL = len(_FILL_ORDER)


def _cycle_color(frame: int) -> int:
    """The solid color for the current fill cycle."""
    return _COLORS[(frame // _CYCLE_FRAMES) % len(_COLORS)]


def _animate_buttons(pads, frame: int) -> None:
    """Light the buttons: RGB ones match the pad color, white ones breathe."""
    color = _cycle_color(frame)
    for cc in push2_midi.BUTTONS_RGB:
        pads.set_button(cc, color)
    # Gentle brightness breathing for the white buttons (no harsh blinking).
    brightness = int(40 + 35 * math.sin(frame / 12.0))
    for cc in push2_midi.BUTTONS_WHITE:
        pads.set_button(cc, brightness)


def _animate_pads(pads, frame: int, held: set) -> None:
    """Grow a single-color fill slowly from one corner; switch color per cycle.

    1 pad lit -> 2 -> 3 ... ease-in until all 64 are lit (one color), hold,
    then start over from one corner in the next color. Held pads stay white.
    """
    f = frame % _CYCLE_FRAMES
    color = _cycle_color(frame)

    if f < _FILL_FRAMES:
        progress = f / _FILL_FRAMES          # 0..1
        lit = math.ceil(_TOTAL * progress * progress)  # slow start, accelerates
    else:
        lit = _TOTAL                          # fully lit, holding

    for i, note in enumerate(_FILL_ORDER):
        if note in held:
            continue
        pads.set_pad(note, color if i < lit else push2_midi.OFF)


def _demo_model(model: DisplayModel, frame: int) -> None:
    """Animate a synthetic state so the pipeline can run without FL Studio."""
    model.playing = (frame // 30) % 2 == 0
    model.recording = (frame // 60) % 4 == 0
    model.bpm = 120 + (frame // 10) % 40
    model.selected_track = (frame // 45) % 8
    for i in range(8):
        model.track_names[i] = ["Kick", "Snare", "Hat", "Bass",
                                "Lead", "Pad", "FX", "Vox"][i]
        model.track_levels[i] = int(63 + 63 * math.sin((frame / 12.0) + i))
        model.params[i] = (["Cut", "Res", "Drv", "Att",
                            "Dec", "Sus", "Rel", "Mix"][i],
                           int(63 + 63 * math.cos((frame / 18.0) + i)))


def _run_demo(args) -> int:
    """Animated self-test. Drives the real Push 2 if present, else PNG frames."""
    model = DisplayModel()
    interval = 1.0 / max(1, args.fps)

    try:
        display = Push2Display()
        display.open()
    except Push2DisplayNotFound as exc:
        out = args.png_out or "push2_demo"
        print(f"No Push 2 on USB ({exc.__class__.__name__}); writing PNGs to "
              f"{out}_NNN.png instead.")
        n = args.demo_frames or 5
        for frame in range(n):
            _demo_model(model, frame)
            renderer.draw(model).save(f"{out}_{frame:03d}.png")
        print(f"Wrote {n} demo PNG frame(s). Pipeline OK.")
        return 0

    # Optional scrolling-text marquee on the pads instead of the color fill.
    marquee = (
        pad_text.PadText(args.text, speed=args.text_speed,
                         color=args.text_color, big=args.text_big)
        if args.text else None
    )

    # Pads are a separate MIDI interface — open them if present.
    pads = None
    held: set = set()
    if push2_midi.Push2Pads.available():
        pads = push2_midi.Push2Pads(args.pad_port)
        try:
            pads.open()
            print(f"Pads active on '{args.pad_port}' — press them; they light white.")
        except (OSError, IOError) as exc:
            print(f"Could not open pad port ({exc}); display only.")
            pads = None

    print("Push 2 connected — driving the real display (Ctrl-C to stop).")
    try:
        frame = 0
        while True:
            start = time.perf_counter()
            _demo_model(model, frame)
            display.send_frame(renderer.render(model))
            if pads is not None:
                for note, pressed in pads.poll():
                    if pressed:
                        held.add(note)
                        pads.set_pad(note, push2_midi.WHITE)
                    else:
                        held.discard(note)
                if marquee is not None:
                    marquee.render(pads, frame, held)
                else:
                    _animate_pads(pads, frame, held)
                _animate_buttons(pads, frame)
            frame += 1
            if args.demo_frames and frame >= args.demo_frames:
                print(f"Sent {frame} frames to the Push 2 display. OK.")
                break
            elapsed = time.perf_counter() - start
            if elapsed < interval:
                time.sleep(interval - elapsed)
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        if pads is not None:
            pads.close()
        display.close()
    return 0


def _run_monitor(args) -> int:
    """Show live Push 2 MIDI activity on the display (works alongside FL).

    Resilient: waits for the Push and reconnects if it's unplugged, so it can
    run unattended (e.g. as a login launchd agent).
    """
    state = MonitorState()
    interval = 1.0 / max(1, args.fps)
    retry = 3.0
    while True:
        in_port = None
        try:
            in_port = mido.open_input(args.pad_port)
            with Push2Display() as display:
                print(f"Connected. Monitoring '{args.pad_port}'.")
                while True:
                    start = time.perf_counter()
                    for msg in in_port.iter_pending():
                        state.update(msg)
                    display.send_frame(renderer.render_monitor(state))
                    elapsed = time.perf_counter() - start
                    if elapsed < interval:
                        time.sleep(interval - elapsed)
        except KeyboardInterrupt:
            print("\nStopping.")
            return 0
        except (Push2DisplayNotFound, OSError, IOError, usb.core.USBError) as exc:
            print(f"Waiting for Push 2 ({exc.__class__.__name__}); retry in {retry:.0f}s")
            time.sleep(retry)
        finally:
            if in_port is not None:
                in_port.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Push 2 display daemon for FL Studio")
    parser.add_argument(
        "--midi-port",
        help="Virtual MIDI input port name (IAC bus / loopMIDI port). "
        "Omit to list available ports and exit.",
    )
    parser.add_argument("--fps", type=int, default=60)
    parser.add_argument(
        "--pad-port",
        default="Ableton Push 2 Live Port",
        help="Push 2 MIDI port for pad LEDs/input in --demo mode.",
    )
    parser.add_argument(
        "--text",
        help="In --demo mode, scroll this text across the pads instead of the "
        "color-fill animation.",
    )
    parser.add_argument(
        "--text-speed",
        type=int,
        default=3,
        help="Frames per column step for --text (smaller = faster scroll).",
    )
    parser.add_argument(
        "--text-color",
        type=int,
        default=push2_midi.WHITE,
        help="Palette index for --text (single color). Default: white.",
    )
    parser.add_argument(
        "--text-big",
        action="store_true",
        help="Use the larger 5x7 font for --text (default is compact 3x5).",
    )
    parser.add_argument(
        "--monitor",
        action="store_true",
        help="Show live Push 2 MIDI activity (pads/buttons/encoders) on the "
        "display. Works alongside FL Studio — no IAC/companion setup needed.",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Drive the display with an animated synthetic state (no FL "
        "Studio / no MIDI needed). Falls back to writing PNG frames if no "
        "Push 2 is connected.",
    )
    parser.add_argument(
        "--demo-frames",
        type=int,
        default=0,
        help="In --demo mode, stop after N frames (0 = run forever).",
    )
    parser.add_argument(
        "--png-out",
        help="In --demo mode without hardware, write rendered frames here "
        "(e.g. /tmp/push2_demo). Frame number is appended.",
    )
    args = parser.parse_args()

    if args.monitor:
        return _run_monitor(args)

    if args.demo:
        return _run_demo(args)

    if not args.midi_port:
        print("Available MIDI input ports:")
        for name in MidiStateListener.available_ports():
            print(f"  - {name}")
        print("\nRe-run with: --midi-port \"<one of the above>\"")
        return 0

    model = DisplayModel()
    listener = MidiStateListener(model, args.midi_port)
    listener.start()
    print(f"Listening for FL state on: {args.midi_port}")

    interval = 1.0 / max(1, args.fps)
    try:
        with Push2Display() as display:
            print("Push 2 display connected. Rendering... (Ctrl-C to stop)")
            while True:
                start = time.perf_counter()
                display.send_frame(renderer.render(model))
                elapsed = time.perf_counter() - start
                if elapsed < interval:
                    time.sleep(interval - elapsed)
    except Push2DisplayNotFound as exc:
        print(f"ERROR: {exc}")
        return 1
    except KeyboardInterrupt:
        print("\nStopping.")
        return 0
    finally:
        listener.stop()


if __name__ == "__main__":
    raise SystemExit(main())
