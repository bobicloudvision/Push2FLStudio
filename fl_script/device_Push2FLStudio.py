# name=Push 2 FL Studio
# url=https://github.com/Ableton/push-interface
# supportedDevices=Ableton Push 2
#
# Controller surface for the Ableton Push 2 in FL Studio.
#
# Milestone 1: DRUM PADS + TRANSPORT.
#   * Each pad triggers one Channel Rack channel (bottom-left pad = channel 0,
#     left-to-right, bottom-to-top). Velocity-sensitive.
#   * Pads with a channel are lit; pressing one flashes it white.
#   * Play / Stop / Record buttons drive the FL transport, with LED feedback.
#
# State mirroring to the display daemon is kept but guarded — it is a no-op if
# the companion "Push 2 Display Out" script isn't set up, so this milestone
# can be tested without the display.
# Push2FLStudio  —  Copyright (c) 2026 Bozhidar Slaveykov.
# Licensed under the project's Attribution-Required License (see LICENSE).
# Any use or modification must credit the author: BOZHIDAR SLAVEYKOV.
#

import transport
import channels
import mixer
import device

import push2_map as p2
import protocol as proto
import scales

NUM_TRACKS = 8
MAX_CHANNELS = 64  # 8x8 pad grid

# Push 2 sysex prefix for device commands (Set/Reapply palette etc.).
_PUSH_PREFIX = [0xF0, 0x00, 0x21, 0x1D, 0x01, 0x01]

# We remap palette indices 1..64 to the exact Channel Rack channel colors.
# Index 0 = off; 122 = white (pressed); 124..127 used by transport — untouched.
_CH_PALETTE_BASE = 1

_last = {
    "playing": None,
    "recording": None,
    "bpm": None,
    "selected": None,
    "names": [None] * NUM_TRACKS,
    "levels": [None] * NUM_TRACKS,
}

_chan_colors = [None] * MAX_CHANNELS   # cache: last channel color synced
_pad_cache = {}                        # note -> last color sent
_btn_cache = {}                        # cc -> last value sent

# Pad modes: "drum" (pad -> channel) or "note" (chromatic piano-roll grid).
_mode = "drum"
_root = 48                             # root note (C3); octave buttons shift it
IN_KEY_ROW_STEP = 3                    # scale-steps each row goes up (~a fourth)
_scale = 0                             # active scale (applied live as you browse)
_scale_mode = False                    # scale screen open (Scale button toggles)


# --------------------------------------------------------------------------
# Low-level LED helpers
# --------------------------------------------------------------------------
def _pad_led(note, color):
    # Note On, channel 1: velocity = palette color index. Cached.
    if _pad_cache.get(note) == color:
        return
    _pad_cache[note] = color
    device.midiOutMsg(0x90 + (note << 8) + (color << 16))


def _btn_led(cc, value):
    # CC, channel 1: value = palette index (RGB buttons) or brightness (white).
    if _btn_cache.get(cc) == value:
        return
    _btn_cache[cc] = value
    device.midiOutMsg(0xB0 + (cc << 8) + (value << 16))


def _set_palette(index, r, g, b):
    """Define Push palette entry `index` as 8-bit r/g/b (white left at 0)."""
    msg = _PUSH_PREFIX + [0x03, index & 0x7F,
                          r & 0x7F, (r >> 7) & 1,
                          g & 0x7F, (g >> 7) & 1,
                          b & 0x7F, (b >> 7) & 1,
                          0x00, 0x00, 0xF7]
    device.midiOutSysex(bytes(msg))


def _reapply_palette():
    device.midiOutSysex(bytes(_PUSH_PREFIX + [0x05, 0xF7]))


def _sync_palette():
    """Push the current channel colors into palette slots 1..N. Reapply if any
    changed so already-lit pads recolor without resending notes."""
    count = channels.channelCount()
    changed = False
    for i in range(min(count, MAX_CHANNELS)):
        c = channels.getChannelColor(i)
        if _chan_colors[i] != c:
            _chan_colors[i] = c
            _set_palette(_CH_PALETTE_BASE + i,
                         (c >> 16) & 0xFF, (c >> 8) & 0xFF, c & 0xFF)
            changed = True
    if changed:
        _reapply_palette()


def _pad_to_channel(note):
    """Pad note -> Channel Rack channel index (or -1 if out of grid)."""
    idx = note - p2.PAD_NOTE_MIN
    return idx if 0 <= idx < p2.PAD_ROWS * p2.PAD_COLS else -1


# --------------------------------------------------------------------------
# Display mirroring (guarded; optional for this milestone)
# --------------------------------------------------------------------------
def _mirror(sysex_bytes):
    try:
        device.dispatch(0, 0xF0, sysex_bytes)
    except Exception:
        pass  # companion display-out script not configured — fine


# --------------------------------------------------------------------------
# Pad LEDs
# --------------------------------------------------------------------------
def _channel_pad_color(idx):
    """Palette index showing channel `idx`'s own Channel Rack color."""
    return _CH_PALETTE_BASE + idx


def _pad_scale_index(note):
    """Note-mode: pad -> index into the in-key note run (isomorphic grid)."""
    idx = note - p2.PAD_NOTE_MIN
    row, col = idx // p2.PAD_COLS, idx % p2.PAD_COLS
    return row * IN_KEY_ROW_STEP + col


def _scale_note(scale_index):
    """The MIDI note for the Nth in-key step above the root."""
    s = scales.SCALES[_scale]
    n = len(s)
    return _root + (scale_index // n) * 12 + s[scale_index % n]


def _note_pad_color(scale_index):
    """In-key pad color: root/octave highlighted, other in-key = channel color."""
    n = len(scales.SCALES[_scale])
    if scale_index % n == 0:
        return p2.PAD_BLUE            # root / octave
    sel = channels.selectedChannel()
    if 0 <= sel < MAX_CHANNELS:
        return _channel_pad_color(sel)
    return p2.PAD_GREEN


def _refresh_pads():
    """Light the pads for the current mode."""
    _sync_palette()
    if _mode == "note":
        for note in range(p2.PAD_NOTE_MIN, p2.PAD_NOTE_MAX + 1):
            si = _pad_scale_index(note)
            _pad_led(note, _note_pad_color(si) if _scale_note(si) <= 127 else p2.PAD_OFF)
        return
    count = channels.channelCount()
    for note in range(p2.PAD_NOTE_MIN, p2.PAD_NOTE_MAX + 1):
        idx = _pad_to_channel(note)
        if 0 <= idx < count and idx < MAX_CHANNELS:
            _pad_led(note, _channel_pad_color(idx))
        else:
            _pad_led(note, p2.PAD_OFF)


# --------------------------------------------------------------------------
# Transport LEDs
# --------------------------------------------------------------------------
WHITE_BTN_GLOW = 25  # soft default brightness for white buttons


def _refresh_white_buttons():
    """Softly light all supported white buttons so it's clear the script is on."""
    for cc in p2.BUTTONS_WHITE:
        _btn_led(cc, WHITE_BTN_GLOW)


def _refresh_transport():
    playing = transport.isPlaying()
    recording = transport.isRecording()
    # Default white; light up in their state color when active.
    _btn_led(p2.BTN_PLAY, p2.PAD_GREEN if playing else p2.PAD_WHITE)
    _btn_led(p2.BTN_RECORD, p2.PAD_RED if recording else p2.PAD_WHITE)
    _btn_led(p2.BTN_STOP, p2.PAD_WHITE)

    bpm = int(round(mixer.getCurrentTempo() / 1000.0))
    if (playing, recording, bpm) != (_last["playing"], _last["recording"], _last["bpm"]):
        _last.update(playing=playing, recording=recording, bpm=bpm)
        _mirror(proto.transport(playing, recording, bpm))


# --------------------------------------------------------------------------
# FL Studio callbacks
# --------------------------------------------------------------------------
def OnInit():
    _refresh_pads()
    _refresh_white_buttons()
    _refresh_mode_leds()
    _refresh_transport()
    _mirror(proto.clear())


def OnDeInit():
    # Turn everything off on unload.
    for note in range(p2.PAD_NOTE_MIN, p2.PAD_NOTE_MAX + 1):
        _pad_led(note, p2.PAD_OFF)
    _btn_led(p2.BTN_PLAY, p2.PAD_OFF)
    _btn_led(p2.BTN_RECORD, p2.PAD_OFF)
    _btn_led(p2.BTN_STOP, p2.PAD_OFF)
    for cc in p2.BUTTONS_WHITE:
        _btn_led(cc, p2.PAD_OFF)
    _mirror(proto.clear())


def OnMidiMsg(event):
    status = event.status & 0xF0

    # Pads -> Channel Rack channels
    if status in (0x90, 0x80):
        if p2.is_pad(event.data1):
            _handle_pad(event)
            event.handled = True
        return

    # Buttons (press only, value 127)
    if status == 0xB0 and event.data2 == 127:
        _handle_button(event.data1)
        event.handled = True


def _toggle_scale_mode():
    global _scale_mode
    _scale_mode = not _scale_mode
    _btn_led(p2.BTN_SCALE, 127 if _scale_mode else WHITE_BTN_GLOW)
    _mirror_scale()


def _change_scale(cc):
    """Arrows pick a scale; it applies live (no Load step)."""
    global _scale
    delta = {p2.BTN_LEFT: -1, p2.BTN_RIGHT: 1,
             p2.BTN_UP: -p2.SCALE_GRID_COLS,
             p2.BTN_DOWN: p2.SCALE_GRID_COLS}[cc]
    _scale = max(0, min(scales.COUNT - 1, _scale + delta))
    _refresh_pads()
    _mirror_scale()


def _change_root(delta):
    """Shift the key by a semitone (Page buttons) and relayout note pads."""
    global _root
    _root = max(0, min(127, _root + delta))
    _refresh_pads()
    _mirror_scale()


def _mirror_scale():
    _mirror(proto.scale(_scale_mode, _scale, _root % 12))


def _handle_pad(event):
    pressed = (event.status & 0xF0) == 0x90 and event.data2 > 0
    note = event.data1

    if _mode == "note":
        si = _pad_scale_index(note)
        played = _scale_note(si)
        if played > 127:
            return
        sel = channels.selectedChannel()
        channels.midiNoteOn(sel, played, event.data2 if pressed else 0)
        _pad_led(note, p2.PAD_WHITE if pressed else _note_pad_color(si))
        return

    idx = _pad_to_channel(note)
    if idx < 0 or idx >= channels.channelCount():
        return
    # Play the channel (note 60 = middle C) at the pad's velocity.
    channels.midiNoteOn(idx, 60, event.data2 if pressed else 0)
    _pad_led(note, p2.PAD_WHITE if pressed else _channel_pad_color(idx))


def _handle_button(cc):
    global _mode
    if cc == p2.BTN_SCALE:
        _toggle_scale_mode()
        return
    # Arrows pick the scale while the scale screen is open.
    if _scale_mode and cc in (p2.BTN_UP, p2.BTN_DOWN, p2.BTN_LEFT, p2.BTN_RIGHT):
        _change_scale(cc)
        return
    # Key (root) +/- a semitone, any time.
    if cc == p2.BTN_PAGE_LEFT:
        _change_root(-1)
        return
    if cc == p2.BTN_PAGE_RIGHT:
        _change_root(1)
        return

    if cc == p2.BTN_PLAY:
        transport.start()
    elif cc == p2.BTN_STOP:
        transport.stop()
    elif cc == p2.BTN_RECORD:
        transport.record()
    elif cc == p2.BTN_METRONOME:
        transport.globalTransport(110, 1)  # FPT_Metronome
    elif cc == p2.BTN_NOTE:
        _mode = "note" if _mode == "drum" else "drum"
        _pad_cache.clear()                 # force full repaint
        _refresh_pads()
        _refresh_mode_leds()
    elif cc == p2.BTN_OCTAVE_UP:
        _change_root(12)
    elif cc == p2.BTN_OCTAVE_DOWN:
        _change_root(-12)
    _refresh_transport()


def _refresh_mode_leds():
    """Light the Note button bright in note mode, dim glow in drum mode."""
    _btn_led(p2.BTN_NOTE, 127 if _mode == "note" else WHITE_BTN_GLOW)
    active = p2.PAD_WHITE if _mode == "note" else p2.PAD_OFF
    _btn_led(p2.BTN_OCTAVE_UP, active)
    _btn_led(p2.BTN_OCTAVE_DOWN, active)


def OnRefresh(flags):
    _refresh_pads()
    _refresh_white_buttons()
    _refresh_transport()


def OnUpdateBeatIndicator(value):
    pass


def OnIdle():
    pass
