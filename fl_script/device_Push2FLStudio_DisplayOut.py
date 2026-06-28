# name=Push 2 Display Out
# receiveFrom=Push 2 FL Studio
# supportedDevices=
#
# Companion script. Its job is tiny: receive SysEx dispatched by the main
# "Push 2 FL Studio" script and emit it out THIS script's output port, which
# you set to the virtual MIDI bus (IAC on macOS / loopMIDI on Windows) that
# the display daemon listens on.
#
# Wiring (FL MIDI settings):
#   * Input:  the virtual bus (or "(none)" — this script doesn't read input)
#   * Output: the virtual bus the display daemon listens on
#   * `receiveFrom` above links it to the main script for device.dispatch().
# Push2FLStudio  —  Copyright (c) 2026 Bozhidar Slaveykov.
# Licensed under the project's Attribution-Required License (see LICENSE).
# Any use or modification must credit the author: BOZHIDAR SLAVEYKOV.
#

import device


def OnInit():
    pass


def OnDeInit():
    pass


def OnMidiIn(event):
    """Dispatched messages from the main script arrive here. Forward any SysEx
    out this script's output port (the virtual bus the daemon listens on)."""
    if event.sysex:
        device.midiOutSysex(bytes(event.sysex))
        event.handled = True
