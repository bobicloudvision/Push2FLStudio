# Push2FLStudio  —  Copyright (c) 2026 Bozhidar Slaveykov.
# Licensed under the project's Attribution-Required License (see LICENSE).
# Any use or modification must credit the author: BOZHIDAR SLAVEYKOV.

"""Live MIDI monitor state for the Push 2 display.

Listens to what you play on the Push (pads, buttons, encoders) and keeps a
small state the renderer can draw. macOS CoreMIDI allows multiple listeners
on one source, so this works alongside FL Studio with no extra setup.
"""

from __future__ import annotations

from . import push2_midi

# Track encoders send relative CC 71..78.
_ENC_CC = list(range(71, 79))


def _decode_relative(value: int) -> int:
    return value if value < 64 else value - 128


class MonitorState:
    def __init__(self) -> None:
        self.last_note = None
        self.last_vel = 0
        self.note_on = False
        self.last_cc = None
        self.last_cc_val = 0
        self.encoders = [0] * 8       # accumulated 0..127
        self.events = 0

    def pad_rc(self):
        """(row, col) of the last note if it's a pad, else None."""
        if self.last_note is None or not push2_midi.is_pad(self.last_note):
            return None
        idx = self.last_note - push2_midi.PAD_NOTE_MIN
        return idx // push2_midi.PAD_COLS, idx % push2_midi.PAD_COLS

    def update(self, msg) -> None:
        if msg.type == "note_on" and msg.velocity > 0:
            self.last_note, self.last_vel, self.note_on = msg.note, msg.velocity, True
            self.events += 1
        elif msg.type in ("note_off",) or (msg.type == "note_on" and msg.velocity == 0):
            if msg.note == self.last_note:
                self.note_on = False
        elif msg.type == "control_change":
            if msg.control in _ENC_CC:
                i = _ENC_CC.index(msg.control)
                self.encoders[i] = max(0, min(127, self.encoders[i]
                                              + _decode_relative(msg.value)))
            else:
                self.last_cc, self.last_cc_val = msg.control, msg.value
            self.events += 1
