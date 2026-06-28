# Push2FLStudio  —  Copyright (c) 2026 Bozhidar Slaveykov.
# Licensed under the project's Attribution-Required License (see LICENSE).
# Any use or modification must credit the author: BOZHIDAR SLAVEYKOV.

"""State-mirroring SysEx protocol — FL STUDIO side (encoder).

MUST stay byte-for-byte compatible with
``display_daemon/protocol.py`` (the decoder). Duplicated on purpose: the FL
sandbox cannot import code from outside this folder, and the daemon is a
separate process.

Pure built-ins only (FL Studio's Python 3.9 sandbox).
"""

SYSEX_START = 0xF0
SYSEX_END = 0xF7
EDU_ID = 0x7D

MSG_TRANSPORT = 0x01
MSG_SELECTED_TRACK = 0x02
MSG_TRACK_NAME = 0x10
MSG_TRACK_LEVEL = 0x11
MSG_PARAM = 0x20
MSG_SCALE = 0x30
MSG_MIX_ACTIVE = 0x40
MSG_MIX_META = 0x41
MSG_MIX_LIVE = 0x42
MSG_CLEAR = 0x7F


def _ascii7(text):
    """Encode text as MIDI-safe (< 0x80) bytes, max *len* enforced by caller."""
    return [ord(c) & 0x7F for c in text if ord(c) < 0x80]


def _wrap(payload):
    """Wrap a <type>+body payload into full SysEx bytes for midiOutSysex."""
    return bytes([SYSEX_START, EDU_ID] + payload + [SYSEX_END])


def transport(playing, recording, bpm):
    bpm = int(bpm)
    return _wrap([MSG_TRANSPORT, 1 if playing else 0, 1 if recording else 0,
                  (bpm >> 7) & 0x7F, bpm & 0x7F])


def selected_track(index):
    return _wrap([MSG_SELECTED_TRACK, index & 0x7F])


def track_name(index, name):
    return _wrap([MSG_TRACK_NAME, index & 0x7F] + _ascii7(name[:12]))


def track_level(index, value):
    return _wrap([MSG_TRACK_LEVEL, index & 0x7F, value & 0x7F])


def param(index, value, name):
    return _wrap([MSG_PARAM, index & 0x7F, value & 0x7F] + _ascii7(name[:10]))


def mix_active(active):
    return _wrap([MSG_MIX_ACTIVE, 1 if active else 0])


def mix_meta(index, color, name):
    """color is 0xRRGGBB; split each 8-bit channel into lo7 + hi1."""
    r, g, b = (color >> 16) & 0xFF, (color >> 8) & 0xFF, color & 0xFF
    return _wrap([MSG_MIX_META, index & 0x7F,
                  r & 0x7F, (r >> 7) & 1,
                  g & 0x7F, (g >> 7) & 1,
                  b & 0x7F, (b >> 7) & 1] + _ascii7(name[:10]))


def mix_live(index, volume, peak, muted, solo):
    flags = (1 if muted else 0) | (2 if solo else 0)
    return _wrap([MSG_MIX_LIVE, index & 0x7F, volume & 0x7F, peak & 0x7F, flags])


def scale(active, index, root_pc):
    """Scale picker state: active flag, scale index, root pitch class (0..11)."""
    return _wrap([MSG_SCALE, 1 if active else 0, index & 0x7F, root_pc & 0x7F])


def clear():
    return _wrap([MSG_CLEAR])
