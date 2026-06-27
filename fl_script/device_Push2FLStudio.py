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

import transport
import channels
import mixer
import device

import push2_map as p2
import protocol as proto

NUM_TRACKS = 8

_last = {
    "playing": None,
    "recording": None,
    "bpm": None,
    "selected": None,
    "names": [None] * NUM_TRACKS,
    "levels": [None] * NUM_TRACKS,
}


# --------------------------------------------------------------------------
# Low-level LED helpers
# --------------------------------------------------------------------------
def _pad_led(note, color):
    # Note On, channel 1: velocity = palette color index.
    device.midiOutMsg(0x90 + (note << 8) + (color << 16))


def _btn_led(cc, value):
    # CC, channel 1: value = palette index (RGB buttons) or brightness (white).
    device.midiOutMsg(0xB0 + (cc << 8) + (value << 16))


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
def _refresh_pads():
    """Light pads that map to an existing channel; others off."""
    count = channels.channelCount()
    for note in range(p2.PAD_NOTE_MIN, p2.PAD_NOTE_MAX + 1):
        idx = _pad_to_channel(note)
        if 0 <= idx < count:
            _pad_led(note, p2.PAD_BLUE)
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
    _btn_led(p2.BTN_PLAY, p2.PAD_GREEN if playing else p2.PAD_OFF)
    _btn_led(p2.BTN_RECORD, p2.PAD_RED if recording else p2.PAD_OFF)
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

    # Buttons (press only)
    if status == 0xB0 and event.data2 == 127:
        _handle_button(event.data1)
        event.handled = True


def _handle_pad(event):
    note = event.data1
    idx = _pad_to_channel(note)
    if idx < 0 or idx >= channels.channelCount():
        return
    pressed = (event.status & 0xF0) == 0x90 and event.data2 > 0
    # Play the channel (note 60 = middle C) at the pad's velocity.
    channels.midiNoteOn(idx, 60, event.data2 if pressed else 0)
    _pad_led(note, p2.PAD_WHITE if pressed else p2.PAD_BLUE)


def _handle_button(cc):
    if cc == p2.BTN_PLAY:
        transport.start()
    elif cc == p2.BTN_STOP:
        transport.stop()
    elif cc == p2.BTN_RECORD:
        transport.record()
    elif cc == p2.BTN_METRONOME:
        transport.globalTransport(110, 1)  # FPT_Metronome
    _refresh_transport()


def OnRefresh(flags):
    _refresh_pads()
    _refresh_white_buttons()
    _refresh_transport()


def OnUpdateBeatIndicator(value):
    pass


def OnIdle():
    pass
