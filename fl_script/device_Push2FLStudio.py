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
# Mixer track colors live in palette slots 100..107 (8 tracks).
_MIX_PALETTE_BASE = 100

_last = {
    "playing": None,
    "recording": None,
    "bpm": None,
    "selected": None,
    "names": [None] * NUM_TRACKS,
    "levels": [None] * NUM_TRACKS,
}

_chan_colors = [None] * MAX_CHANNELS   # cache: last channel color synced
_mix_colors = [None] * 8               # cache: last mixer-track color synced
_pad_cache = {}                        # note -> last color sent
_btn_cache = {}                        # cc -> last value sent

# Pad modes: "drum" (pad -> channel), "note" (in-key grid), "mix" (mixer).
_mode = "drum"
_prev_play_mode = "drum"               # mode to restore when leaving mix
MIX_TRACKS = 8                         # mixer tracks shown (1..8)
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
    # Two routes to the daemon; whichever is wired works, the other no-ops.
    #  1) Direct: if the IAC bus output shares this controller's Port number,
    #     device.midiOutSysex reaches it (and the Push, which ignores our id).
    #  2) Companion: dispatch to the "Display Out" script, which re-emits it.
    try:
        device.midiOutSysex(sysex_bytes)
    except Exception:
        pass
    try:
        device.dispatch(-1, 0xF4, sysex_bytes)
    except Exception:
        pass


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


def _sync_mix_palette():
    """Mirror the 8 mixer-track colors into palette slots 100..107."""
    count = mixer.trackCount()
    changed = False
    for i in range(8):
        track = i + 1
        c = mixer.getTrackColor(track) if track < count else 0
        if _mix_colors[i] != c:
            _mix_colors[i] = c
            _set_palette(_MIX_PALETTE_BASE + i,
                         (c >> 16) & 0xFF, (c >> 8) & 0xFF, c & 0xFF)
            changed = True
    if changed:
        _reapply_palette()


def _refresh_mix_meters():
    """Each column = a mixer track: bar in the track's own color = live output
    level (peak). The fader setting is shown on the screen, not the pads."""
    _sync_mix_palette()
    count = mixer.trackCount()
    for col in range(p2.PAD_COLS):
        track = col + 1
        present = track < count
        peak = mixer.getTrackPeaks(track, 0) if present else 0.0
        peak_lit = int(round(max(0.0, min(1.0, peak)) * p2.PAD_ROWS))
        bar_color = _MIX_PALETTE_BASE + col if present else p2.PAD_OFF
        for row in range(p2.PAD_ROWS):
            _pad_led(p2.pad_note(row, col), bar_color if row < peak_lit else p2.PAD_OFF)


def _refresh_mix_buttons():
    """Lower display row = mute, upper row = solo (per track), with LEDs."""
    count = mixer.trackCount()
    for i in range(MIX_TRACKS):
        track = i + 1
        present = track < count
        muted = present and mixer.isTrackMuted(track)
        solo = present and mixer.isTrackSolo(track)
        _btn_led(p2.BTN_BELOW_DISPLAY_CC[i], p2.PAD_RED if muted else (WHITE_BTN_GLOW if present else p2.PAD_OFF))
        _btn_led(p2.BTN_ABOVE_DISPLAY_CC[i], p2.PAD_BLUE if solo else (WHITE_BTN_GLOW if present else p2.PAD_OFF))


def _clear_mix_buttons():
    for cc in p2.BTN_BELOW_DISPLAY_CC + p2.BTN_ABOVE_DISPLAY_CC:
        _btn_led(cc, p2.PAD_OFF)


def _mirror_mix_meta():
    """Send each track's name + color to the display (changes rarely)."""
    count = mixer.trackCount()
    for i in range(MIX_TRACKS):
        track = i + 1
        if track < count:
            _mirror(proto.mix_meta(i, mixer.getTrackColor(track),
                                   mixer.getTrackName(track)))


def _mirror_mix_live():
    """Send each track's volume + peak + mute/solo to the display."""
    count = mixer.trackCount()
    for i in range(MIX_TRACKS):
        track = i + 1
        if track >= count:
            continue
        vol = int(max(0.0, min(1.0, mixer.getTrackVolume(track))) * 127)
        peak = int(max(0.0, min(1.0, mixer.getTrackPeaks(track, 0))) * 127)
        _mirror(proto.mix_live(i, vol, peak,
                               mixer.isTrackMuted(track), mixer.isTrackSolo(track)))


def _refresh_pads():
    """Light the pads for the current mode."""
    _sync_palette()
    if _mode == "mix":
        _refresh_mix_meters()
        return
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
    _clear_mix_buttons()
    _mirror(proto.clear())


def OnMidiMsg(event):
    status = event.status & 0xF0

    # Pads -> Channel Rack channels
    if status in (0x90, 0x80):
        if p2.is_pad(event.data1):
            _handle_pad(event)
            event.handled = True
        return

    if status == 0xB0:
        cc, val = event.data1, event.data2
        if cc in p2.ENCODER_TRACK_CC:
            _handle_encoder(p2.ENCODER_TRACK_CC.index(cc), p2.decode_relative(val))
            event.handled = True
        elif val == 127:                      # button press
            _handle_button(cc)
            event.handled = True


def _handle_encoder(idx, delta):
    """Mix mode: encoder idx adjusts mixer track (idx+1) volume."""
    if _mode != "mix":
        return
    track = idx + 1
    if track >= mixer.trackCount():
        return
    vol = mixer.getTrackVolume(track)
    mixer.setTrackVolume(track, max(0.0, min(1.0, vol + delta * 0.02)))
    _refresh_mix_meters()


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
    global _mode, _prev_play_mode
    if cc == p2.BTN_MIX:
        if _mode != "mix":
            _prev_play_mode = _mode
            _mode = "mix"
        else:
            _mode = _prev_play_mode
            _clear_mix_buttons()
        _pad_cache.clear()
        _refresh_pads()
        _refresh_mode_leds()
        if _mode == "mix":
            _refresh_mix_buttons()
            _mirror(proto.mix_active(True))
            _mirror_mix_meta()
        else:
            _mirror(proto.mix_active(False))
        return
    if _mode == "mix":
        if cc in p2.BTN_BELOW_DISPLAY_CC:
            mixer.muteTrack(p2.BTN_BELOW_DISPLAY_CC.index(cc) + 1)
            _refresh_mix_buttons()
            return
        if cc in p2.BTN_ABOVE_DISPLAY_CC:
            mixer.soloTrack(p2.BTN_ABOVE_DISPLAY_CC.index(cc) + 1)
            _refresh_mix_buttons()
            return
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
    """Highlight the active mode's button."""
    _btn_led(p2.BTN_NOTE, 127 if _mode == "note" else WHITE_BTN_GLOW)
    _btn_led(p2.BTN_MIX, 127 if _mode == "mix" else WHITE_BTN_GLOW)
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
    if _mode == "mix":
        _refresh_mix_meters()           # live VU on the pads
        _mirror(proto.mix_active(True))  # re-assert so a late daemon syncs
        _mirror_mix_live()              # live faders/levels on the display
