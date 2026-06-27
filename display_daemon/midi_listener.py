# Push2FLStudio  —  Copyright (c) 2026 Bozhidar Slaveykov.
# Licensed under the project's Attribution-Required License (see LICENSE).
# Any use or modification must credit the author: BOZHIDAR SLAVEYKOV.

"""Listen on the virtual MIDI port for state SysEx from the FL Studio script.

macOS: enable an IAC Driver bus in Audio MIDI Setup.
Windows: create a loopMIDI port.
Both ends (FL script output, this listener input) must point at the same port.
"""

from __future__ import annotations

import threading

import mido

from .protocol import EDU_ID, DisplayModel, apply_sysex


class MidiStateListener:
    """Opens *port_name* and applies incoming state SysEx to *model*."""

    def __init__(self, model: DisplayModel, port_name: str) -> None:
        self._model = model
        self._port_name = port_name
        self._port = None
        self._thread: threading.Thread | None = None
        self._running = False

    @staticmethod
    def available_ports() -> list[str]:
        return mido.get_input_names()

    def start(self) -> None:
        self._port = mido.open_input(self._port_name)
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        for msg in self._port:  # blocks; iterator ends when port closes
            if not self._running:
                break
            if msg.type == "sysex" and msg.data and msg.data[0] == EDU_ID:
                # msg.data excludes F0/F7; drop the EDU id, keep <type>+body
                apply_sysex(self._model, list(msg.data[1:]))

    def stop(self) -> None:
        self._running = False
        if self._port is not None:
            self._port.close()
