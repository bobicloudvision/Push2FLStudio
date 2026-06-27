# name=Push 2 FL Studio
# url=https://github.com/Ableton/push-interface
# supportedDevices=Ableton Push 2
#
# Main controller surface for the Ableton Push 2 in FL Studio.
#
# Responsibilities:
#   * Translate Push 2 controls (pads, encoders, transport buttons) into FL
#     actions via the transport / mixer / channels modules.
#   * Drive Push 2 pad/button LEDs (this script's OUTPUT port = Push 2).
#   * Mirror FL state to the display daemon by DISPATCHING SysEx to the
#     companion "Push 2 Display Out" script, which owns the virtual MIDI port.
#
# Why dispatch?  An FL controller script writes MIDI to exactly ONE output
# port. This script's output is the Push 2 (for LEDs), so it cannot also
# write to the IAC/loopMIDI bus. device.dispatch() hands the SysEx to the
# companion script, whose output IS that bus. See fl_script/README.md.

import transport
import mixer
import device

import push2_map as p2
import protocol as proto

NUM_TRACKS = 8

# Cache of last-sent state so we only mirror what changed.
_last = {
    "playing": None,
    "recording": None,
    "bpm": None,
    "selected": None,
    "names": [None] * NUM_TRACKS,
    "levels": [None] * NUM_TRACKS,
}


# --------------------------------------------------------------------------
# Mirroring to the display daemon
# --------------------------------------------------------------------------
def _mirror(sysex_bytes):
    """Forward a SysEx message to the companion display-out script.

    ctrlIndex 0 = first script that declares `receiveFrom` this controller.
    """
    device.dispatch(0, 0xF0, sysex_bytes)


def _push_transport():
    playing = transport.isPlaying()
    recording = transport.isRecording()
    bpm = int(round(mixer.getCurrentTempo() / 1000.0))
    if (playing, recording, bpm) != (_last["playing"], _last["recording"], _last["bpm"]):
        _last.update(playing=playing, recording=recording, bpm=bpm)
        _mirror(proto.transport(playing, recording, bpm))


def _push_tracks():
    sel = mixer.trackNumber()
    if sel != _last["selected"]:
        _last["selected"] = sel
        _mirror(proto.selected_track(min(sel, NUM_TRACKS - 1)))

    for i in range(NUM_TRACKS):
        name = mixer.getTrackName(i)
        if name != _last["names"][i]:
            _last["names"][i] = name
            _mirror(proto.track_name(i, name))

        # peak level 0.0..~1.0 -> 0..127
        peak = mixer.getTrackPeaks(i, 0)  # 0 = left/mono
        level = max(0, min(127, int(peak * 127)))
        if level != _last["levels"][i]:
            _last["levels"][i] = level
            _mirror(proto.track_level(i, level))


# --------------------------------------------------------------------------
# FL Studio callbacks
# --------------------------------------------------------------------------
def OnInit():
    _mirror(proto.clear())
    # TODO: send Push 2 into the desired mode / set up the pad LED layout.


def OnDeInit():
    _mirror(proto.clear())


def OnMidiMsg(event):
    """Central handler for incoming Push 2 MIDI."""
    status = event.status & 0xF0

    # Notes 0x90/0x80 -> pads
    if status in (0x90, 0x80):
        if p2.is_pad(event.data1):
            _handle_pad(event)
            event.handled = True
        return

    # CC 0xB0 -> encoders + buttons
    if status == 0xB0:
        cc, val = event.data1, event.data2
        if cc in p2.ENCODER_TRACK_CC:
            _handle_encoder(p2.ENCODER_TRACK_CC.index(cc), p2.decode_relative(val))
            event.handled = True
        elif val == 127:  # button press only
            _handle_button(cc)
            event.handled = True


def _handle_pad(event):
    velocity = event.data2 if (event.status & 0xF0) == 0x90 else 0
    # TODO: route to FL — e.g. channels.midiNoteOn / step sequencer / drum pads.
    # Placeholder: light the pad while held.
    device.midiOutMsg((0x90, event.data1, p2.PAD_GREEN if velocity else p2.PAD_OFF))


def _handle_encoder(index, delta):
    # Placeholder: encoder N nudges mixer track N+1 volume.
    track = index + 1
    vol = mixer.getTrackVolume(track)
    mixer.setTrackVolume(track, max(0.0, min(1.0, vol + delta * 0.01)))


def _handle_button(cc):
    if cc == p2.BTN_PLAY:
        transport.start()
    elif cc == p2.BTN_RECORD:
        transport.record()
    elif cc == p2.BTN_METRONOME:
        transport.globalTransport(110, 1)  # FPT_Metronome
    # TODO: map remaining transport/global buttons.


def OnRefresh(flags):
    _push_transport()
    _push_tracks()


def OnUpdateBeatIndicator(value):
    # value: 0 off, 1 bar, 2 beat — good hook for a flashing tempo LED.
    pass


def OnIdle():
    # Meters change continuously; refresh them off the idle tick.
    _push_tracks()
