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

# Buttons (CC). RGB buttons take a palette index (same palette as pads);
# white buttons take a brightness 0..127. From Ableton/push-interface map.
BUTTONS_RGB = [
    60, 61, 29, 89, 86, 85,                       # mute/solo/stop/automate/rec/play
    102, 103, 104, 105, 106, 107, 108, 109,       # upper display row
    20, 21, 22, 23, 24, 25, 26, 27,               # lower display row
    43, 42, 41, 40, 39, 38, 37, 36,               # time-division row
]
BUTTONS_WHITE = [
    3, 9, 118, 119, 35, 117, 116, 88, 87, 90, 30, 59, 52, 53,
    110, 112, 111, 113, 28, 46, 47, 44, 45, 56, 57, 58, 31, 50,
    51, 55, 54, 62, 63, 49, 48,
]


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
        self._btn_cache: dict = {}  # cc -> last value, avoids flicker

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

    def set_button(self, cc: int, value: int) -> None:
        """Set a button LED. RGB button: value = color index; white: brightness.

        No-op if unchanged (prevents flicker).
        """
        if self._out is None:
            return
        if self._btn_cache.get(cc) == value:
            return
        self._btn_cache[cc] = value
        self._out.send(mido.Message("control_change", control=cc,
                                    value=value, channel=0))

    def clear(self) -> None:
        for note in range(PAD_NOTE_MIN, PAD_NOTE_MAX + 1):
            self.set_pad(note, OFF)
        for cc in BUTTONS_RGB + BUTTONS_WHITE:
            self.set_button(cc, 0)

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
