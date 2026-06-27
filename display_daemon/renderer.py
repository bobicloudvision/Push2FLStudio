"""Render a DisplayModel into a scrambled Push 2 framebuffer.

Drawing is done with Pillow into a 960x160 RGB image, then converted to the
padded RGB565 wire buffer and scrambled. The conversion uses numpy if it is
available (fast) and falls back to a pure-Python path otherwise.
"""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

from .protocol import DisplayModel
from .usb_display import (
    BYTES_PER_PIXEL,
    HEIGHT,
    LINE_BUFFER_WIDTH,
    LINE_WIDTH,
    scramble,
)

try:
    import numpy as np
except ImportError:  # pragma: no cover - optional fast path
    np = None

_FONT = ImageFont.load_default()


def draw(model: DisplayModel) -> Image.Image:
    """Build the 960x160 RGB image for the current state.

    Intentionally minimal — this is the surface you'll grow into the real UI
    (8 track strips, meters, param names, transport). Treat it as a layout
    placeholder, not the final design.
    """
    img = Image.new("RGB", (LINE_WIDTH, HEIGHT), (0, 0, 0))
    d = ImageDraw.Draw(img)

    transport = "PLAY" if model.playing else "STOP"
    if model.recording:
        transport += " REC"
    d.text((8, 4), f"{transport}   {model.bpm} BPM", fill=(255, 255, 255), font=_FONT)

    col_w = LINE_WIDTH // 8
    for i in range(8):
        x = i * col_w
        selected = i == model.selected_track
        if selected:
            d.rectangle([x, 22, x + col_w - 2, HEIGHT - 2], outline=(80, 160, 255))
        name = (model.track_names[i] or f"Trk {i + 1}")[:10]
        d.text((x + 4, 26), name, fill=(200, 200, 200), font=_FONT)

        pname, pval = model.params[i]
        if pname:
            d.text((x + 4, 44), pname[:10], fill=(160, 160, 160), font=_FONT)

        # level meter (0..127 -> bar height)
        lvl = model.track_levels[i]
        bar_h = int((HEIGHT - 70) * (lvl / 127.0))
        d.rectangle(
            [x + 4, HEIGHT - 6 - bar_h, x + 16, HEIGHT - 6],
            fill=(0, 220, 120),
        )
    return img


def draw_monitor(state) -> Image.Image:
    """Live MIDI activity view: last note, velocity, encoders, last button."""
    img = Image.new("RGB", (LINE_WIDTH, HEIGHT), (0, 0, 0))
    d = ImageDraw.Draw(img)

    d.text((8, 4), "PUSH 2  -  LIVE MIDI MONITOR", fill=(120, 180, 255), font=_FONT)
    d.text((760, 4), f"evt {state.events}", fill=(90, 90, 90), font=_FONT)

    # Last note + a big velocity bar
    rc = state.pad_rc()
    where = f"PAD r{rc[0]} c{rc[1]}" if rc else "-"
    note_txt = "-" if state.last_note is None else str(state.last_note)
    d.text((8, 30), f"NOTE {note_txt}   {where}", fill=(255, 255, 255), font=_FONT)
    d.text((8, 48), f"VEL  {state.last_vel}", fill=(0, 220, 120), font=_FONT)
    bar_w = int((LINE_WIDTH - 320) * (state.last_vel / 127.0))
    color = (0, 220, 120) if state.note_on else (60, 110, 80)
    d.rectangle([90, 50, 90 + bar_w, 60], fill=color)

    cc_txt = "-" if state.last_cc is None else f"CC {state.last_cc} = {state.last_cc_val}"
    d.text((8, 70), f"LAST BUTTON  {cc_txt}", fill=(200, 200, 120), font=_FONT)

    # 8 encoder bars along the bottom
    col_w = LINE_WIDTH // 8
    for i, val in enumerate(state.encoders):
        x = i * col_w + 8
        h = int(40 * (val / 127.0))
        d.rectangle([x, HEIGHT - 8 - h, x + col_w - 20, HEIGHT - 8],
                    fill=(80, 160, 255))
        d.text((x, HEIGHT - 56), f"E{i + 1}", fill=(120, 120, 120), font=_FONT)
    return img


def render_monitor(state) -> bytes:
    return to_framebuffer(draw_monitor(state))


def to_framebuffer(img: Image.Image) -> bytes:
    """Convert a 960x160 RGB image to a scrambled 327,680-byte wire frame."""
    if img.size != (LINE_WIDTH, HEIGHT):
        img = img.resize((LINE_WIDTH, HEIGHT))
    rgb = img.convert("RGB")

    if np is not None:
        arr = np.asarray(rgb, dtype=np.uint16)  # (160, 960, 3)
        r = (arr[:, :, 0] >> 3) << 11
        g = (arr[:, :, 1] >> 2) << 5
        b = arr[:, :, 2] >> 3
        rgb565 = (r | g | b).astype("<u2")  # little-endian
        # pad each line from 960 to 1024 pixels
        padded = np.zeros((HEIGHT, LINE_BUFFER_WIDTH), dtype="<u2")
        padded[:, :LINE_WIDTH] = rgb565
        return scramble(padded.tobytes())

    # Pure-Python fallback
    px = rgb.load()
    buf = bytearray(LINE_BUFFER_WIDTH * HEIGHT * BYTES_PER_PIXEL)
    o = 0
    for y in range(HEIGHT):
        for x in range(LINE_BUFFER_WIDTH):
            if x < LINE_WIDTH:
                r, g, b = px[x, y]
                val = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
            else:
                val = 0
            buf[o] = val & 0xFF
            buf[o + 1] = (val >> 8) & 0xFF
            o += 2
    return scramble(buf)


def render(model: DisplayModel) -> bytes:
    return to_framebuffer(draw(model))
