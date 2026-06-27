"""Direct Push 2 MIDI access for the demo (pads + LEDs).

Separate from the display USB path and from FL Studio: this opens the Push 2's
own USB-MIDI ports so the demo can light pads and react to presses standalone.

Pads: 8x8 grid, notes 36 (bottom-left) .. 99 (top-right), channel 1.
LED:  Note On, velocity = color index into the Push 2 palette.
      The MIDI channel selects the animation (ch 1 = solid). Velocity 0 = off.
"""

from __future__ import annotations

import mido

PAD_NOTE_MIN = 36
PAD_NOTE_MAX = 99
PAD_COLS = 8
PAD_ROWS = 8

# A few default-palette color indices that read well on the pads.
OFF = 0
WHITE = 122
RED = 127
GREEN = 126
BLUE = 125
YELLOW = 124


def pad_note(row: int, col: int) -> int:
    """row 0 = bottom, col 0 = left."""
    return PAD_NOTE_MIN + row * PAD_COLS + col


def is_pad(note: int) -> bool:
    return PAD_NOTE_MIN <= note <= PAD_NOTE_MAX


class Push2Pads:
    """Owns the Push 2 MIDI in/out ports for pad LEDs and input."""

    def __init__(self, port_name: str = "Ableton Push 2 Live Port") -> None:
        self._port_name = port_name
        self._out = None
        self._in = None
        self._cache: dict = {}  # note -> last (color, channel), avoids flicker

    @staticmethod
    def available() -> bool:
        return any("Push 2" in n for n in mido.get_output_names())

    def open(self) -> None:
        self._out = mido.open_output(self._port_name)
        # Input is optional — open it if the same-named port exists.
        try:
            self._in = mido.open_input(self._port_name)
        except (OSError, IOError):
            self._in = None

    def set_pad(self, note: int, color: int, channel: int = 0) -> None:
        """Set a pad LED. No-op if it's already that color (prevents flicker)."""
        if self._out is None:
            return
        if self._cache.get(note) == (color, channel):
            return
        self._cache[note] = (color, channel)
        self._out.send(mido.Message("note_on", note=note,
                                    velocity=color, channel=channel))

    def clear(self) -> None:
        for note in range(PAD_NOTE_MIN, PAD_NOTE_MAX + 1):
            self.set_pad(note, OFF)

    def poll(self):
        """Yield (note, pressed) for pad events since the last call."""
        if self._in is None:
            return
        for msg in self._in.iter_pending():
            if msg.type == "note_on" and is_pad(msg.note):
                yield msg.note, msg.velocity > 0
            elif msg.type == "note_off" and is_pad(msg.note):
                yield msg.note, False

    def close(self) -> None:
        if self._out is not None:
            self.clear()
            self._out.close()
            self._out = None
        if self._in is not None:
            self._in.close()
            self._in = None
