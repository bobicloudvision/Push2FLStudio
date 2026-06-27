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

# Buttons used by the on-display scale browser.
CC_SCALE = 58             # toggle the scale screen on/off
CC_LOAD = 20              # "Lower Row 1" display button = LOAD selected scale
CC_UP, CC_DOWN, CC_LEFT, CC_RIGHT = 46, 47, 44, 45
SCALE_COUNT = 23          # FL's 23 scales (see renderer.SCALE_NAMES)
_SCALE_COLS = 4           # menu grid width, for up/down stepping


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
        self.scale_menu_open = False  # toggled by the Scale button
        self.scale_index = 0          # cursor scale (navigated by arrows)
        self.loaded_scale = 0         # the scale that was LOADed

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
            cc, val = msg.control, msg.value
            if cc == CC_SCALE and val >= 64:
                self.scale_menu_open = not self.scale_menu_open   # toggle on press
            elif self.scale_menu_open and val >= 64 and cc == CC_LOAD:
                self.loaded_scale = self.scale_index               # load selection
            elif self.scale_menu_open and val >= 64 and cc in (CC_UP, CC_DOWN, CC_LEFT, CC_RIGHT):
                delta = {CC_LEFT: -1, CC_RIGHT: 1,
                         CC_UP: -_SCALE_COLS, CC_DOWN: _SCALE_COLS}[cc]
                self.scale_index = max(0, min(SCALE_COUNT - 1, self.scale_index + delta))
            elif cc in _ENC_CC:
                i = _ENC_CC.index(cc)
                self.encoders[i] = max(0, min(127, self.encoders[i]
                                              + _decode_relative(val)))
            else:
                self.last_cc, self.last_cc_val = cc, val
            self.events += 1
