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

    def __init__(self, model: DisplayModel, port_name: str,
                 virtual: bool = False, debug: bool = False,
                 forward_port=None) -> None:
        self._model = model
        self._port_name = port_name
        self._virtual = virtual
        self._debug = debug
        self._forward = forward_port   # open mido output to the Push (LEDs)
        self._port = None
        self._thread: threading.Thread | None = None
        self._running = False

    @staticmethod
    def available_ports() -> list[str]:
        return mido.get_input_names()

    def start(self) -> None:
        # virtual=True creates our OWN port (no IAC / Audio MIDI Setup needed);
        # it appears system-wide so FL can send to it directly.
        self._port = mido.open_input(self._port_name, virtual=self._virtual)
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        for msg in self._port:  # blocks; iterator ends when port closes
            if not self._running:
                break
            if self._debug:
                if msg.type == "sysex":
                    print(f"[recv] sysex {len(msg.data)} bytes, "
                          f"id=0x{msg.data[0]:02X}" if msg.data else "[recv] sysex empty")
                else:
                    print(f"[recv] {msg}")
            if msg.type == "sysex" and msg.data and msg.data[0] == EDU_ID:
                # Our display state — render it, do NOT pass to the Push.
                apply_sysex(self._model, list(msg.data[1:]))
            elif self._forward is not None:
                # Everything else from FL (pad/button LEDs, palette sysex) is
                # meant for the Push hardware — forward it on.
                try:
                    self._forward.send(msg)
                except Exception:
                    pass

    def stop(self) -> None:
        self._running = False
        if self._port is not None:
            self._port.close()
