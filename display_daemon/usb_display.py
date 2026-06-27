"""Push 2 color display over USB bulk transfer.

Spec: Ableton/push-interface (AbletonPush2MIDIDisplayInterface.asc).

  * USB IDs:        vendor 0x2982, product 0x1967
  * Display iface:  bulk OUT endpoint 0x01
  * Resolution:     960 x 160 visible, but each line is padded to 1024
                    pixels in the wire buffer  ->  1024 * 2 bytes = 2048
                    bytes/line, 160 lines = 327,680 bytes/frame.
  * Pixel format:   RGB565, little-endian, 2 bytes/pixel.
  * Frame header:   16 bytes:  FF CC AA 88  00 x12
  * Scramble:       every 32-bit word is XOR'd with 0xFFE7F3E7 before send.
  * Timeout:        the panel blanks if no frame arrives within 2 s, so the
                    daemon must keep pushing frames even when idle.
"""

from __future__ import annotations

import usb.core
import usb.util

PUSH2_VENDOR_ID = 0x2982
PUSH2_PRODUCT_ID = 0x1967

DISPLAY_ENDPOINT = 0x01

LINE_WIDTH = 960          # visible
LINE_BUFFER_WIDTH = 1024  # padded buffer width on the wire
HEIGHT = 160
BYTES_PER_PIXEL = 2
LINE_BUFFER_BYTES = LINE_BUFFER_WIDTH * BYTES_PER_PIXEL  # 2048
FRAME_BYTES = LINE_BUFFER_BYTES * HEIGHT                 # 327,680

FRAME_HEADER = bytes(
    [0xFF, 0xCC, 0xAA, 0x88, 0x00, 0x00, 0x00, 0x00,
     0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
)

# XOR scramble: pattern 0xFFE7F3E7 over each 32-bit little-endian word,
# i.e. the repeating byte sequence E7 F3 E7 FF.
_XOR_PATTERN = bytes([0xE7, 0xF3, 0xE7, 0xFF])
XOR_MASK = (_XOR_PATTERN * (FRAME_BYTES // 4))

WRITE_TIMEOUT_MS = 1000


class Push2DisplayNotFound(RuntimeError):
    pass


class Push2Display:
    """Owns the USB handle for the Push 2 display endpoint."""

    def __init__(self) -> None:
        self._device = None

    def open(self) -> None:
        dev = usb.core.find(idVendor=PUSH2_VENDOR_ID, idProduct=PUSH2_PRODUCT_ID)
        if dev is None:
            raise Push2DisplayNotFound(
                "Push 2 not found on USB. Check the cable and that no other "
                "app (e.g. Ableton Live) owns the display."
            )
        # On Linux the kernel may have claimed the interface; detach if so.
        try:
            if dev.is_kernel_driver_active(0):
                dev.detach_kernel_driver(0)
        except (NotImplementedError, usb.core.USBError):
            pass  # not applicable on macOS / Windows
        dev.set_configuration()
        self._device = dev

    def send_frame(self, frame: bytes | bytearray) -> None:
        """Send one already-scrambled 327,680-byte frame buffer."""
        if self._device is None:
            raise RuntimeError("Display not opened; call open() first.")
        if len(frame) != FRAME_BYTES:
            raise ValueError(f"frame must be {FRAME_BYTES} bytes, got {len(frame)}")
        self._device.write(DISPLAY_ENDPOINT, FRAME_HEADER, WRITE_TIMEOUT_MS)
        self._device.write(DISPLAY_ENDPOINT, frame, WRITE_TIMEOUT_MS)

    def close(self) -> None:
        if self._device is not None:
            usb.util.dispose_resources(self._device)
            self._device = None

    def __enter__(self) -> "Push2Display":
        self.open()
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def scramble(frame: bytes | bytearray) -> bytes:
    """XOR a raw RGB565 framebuffer with the Push 2 scramble mask."""
    return bytes(b ^ m for b, m in zip(frame, XOR_MASK))
