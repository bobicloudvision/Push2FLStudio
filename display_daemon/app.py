"""Display daemon entry point.

Owns the Push 2 display USB endpoint, listens to the virtual MIDI port for
state from the FL Studio script, and pushes frames at ~60 fps (the panel
blanks after 2 s of silence, so we render continuously even when idle).
"""

from __future__ import annotations

import argparse
import math
import time

from . import renderer
from .midi_listener import MidiStateListener
from .protocol import DisplayModel
from .usb_display import Push2Display, Push2DisplayNotFound

FRAME_INTERVAL = 1.0 / 60.0


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

    print("Push 2 connected — driving the real display (Ctrl-C to stop).")
    try:
        frame = 0
        while True:
            start = time.perf_counter()
            _demo_model(model, frame)
            display.send_frame(renderer.render(model))
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
        display.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Push 2 display daemon for FL Studio")
    parser.add_argument(
        "--midi-port",
        help="Virtual MIDI input port name (IAC bus / loopMIDI port). "
        "Omit to list available ports and exit.",
    )
    parser.add_argument("--fps", type=int, default=60)
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
