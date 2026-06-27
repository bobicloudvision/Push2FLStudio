"""State-mirroring SysEx protocol — DISPLAY DAEMON side (decoder).

The FL Studio script can only emit MIDI, so it mirrors its state to the
display daemon as SysEx messages on a virtual MIDI port (IAC on macOS,
loopMIDI on Windows).

This module MUST stay byte-for-byte compatible with
``fl_script/protocol.py`` (the encoder). They are duplicated on purpose:
the two halves live in different processes and the FL sandbox cannot
import code from outside its own folder.

Wire format (all payload bytes are 7-bit / < 0x80, MIDI-safe):

    F0 7D <type> <payload...> F7

    0x7D = the SysEx "non-commercial / educational" manufacturer id.
"""

from __future__ import annotations

from dataclasses import dataclass, field

SYSEX_START = 0xF0
SYSEX_END = 0xF7
EDU_ID = 0x7D  # non-commercial manufacturer id

# Message types
MSG_TRANSPORT = 0x01      # [playing, recording, bpm_int_hi7, bpm_int_lo7]
MSG_SELECTED_TRACK = 0x02  # [index]
MSG_TRACK_NAME = 0x10      # [index, *ascii]
MSG_TRACK_LEVEL = 0x11     # [index, value 0..127]
MSG_PARAM = 0x20           # [encoder, value 0..127, *ascii name]
MSG_CLEAR = 0x7F           # []  -> reset display model


@dataclass
class DisplayModel:
    """Everything the renderer needs to draw a frame.

    The MIDI listener mutates this; the renderer reads it. One process,
    so a plain object + the GIL is enough — no locking needed.
    """

    playing: bool = False
    recording: bool = False
    bpm: int = 120
    selected_track: int = 0
    track_names: list[str] = field(default_factory=lambda: [""] * 8)
    track_levels: list[int] = field(default_factory=lambda: [0] * 8)
    params: list[tuple[str, int]] = field(default_factory=lambda: [("", 0)] * 8)


def _decode_ascii(data) -> str:
    return bytes(b for b in data if b < 0x80).decode("ascii", "ignore")


def apply_sysex(model: DisplayModel, payload: list[int]) -> None:
    """Apply one SysEx *payload* (the bytes between F0 7D ... F7) to *model*.

    ``payload`` excludes the EDU_ID, i.e. it starts at <type>.
    """
    if not payload:
        return
    msg_type, body = payload[0], payload[1:]

    if msg_type == MSG_TRANSPORT and len(body) >= 4:
        model.playing = bool(body[0])
        model.recording = bool(body[1])
        model.bpm = (body[2] << 7) | body[3]
    elif msg_type == MSG_SELECTED_TRACK and body:
        model.selected_track = body[0]
    elif msg_type == MSG_TRACK_NAME and body:
        idx = body[0]
        if 0 <= idx < len(model.track_names):
            model.track_names[idx] = _decode_ascii(body[1:])
    elif msg_type == MSG_TRACK_LEVEL and len(body) >= 2:
        idx = body[0]
        if 0 <= idx < len(model.track_levels):
            model.track_levels[idx] = body[1]
    elif msg_type == MSG_PARAM and len(body) >= 2:
        idx = body[0]
        if 0 <= idx < len(model.params):
            model.params[idx] = (_decode_ascii(body[2:]), body[1])
    elif msg_type == MSG_CLEAR:
        model.__init__()  # type: ignore[misc]  # reset to defaults
