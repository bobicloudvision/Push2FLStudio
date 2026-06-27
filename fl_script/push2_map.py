"""Push 2 MIDI control map (default / "Live" mode).

Values from Ableton/push-interface — AbletonPush2MIDIDisplayInterface.asc.
Verify against the manual as you wire up controls; a few button CCs vary by
firmware. Grouped here so the main script reads cleanly.
"""

# --- 8x8 pad grid -----------------------------------------------------------
# Pads send Note On/Off (channel 1). Bottom-left = 36, increasing right,
# then up by rows of 8, to top-right = 99.
PAD_NOTE_MIN = 36
PAD_NOTE_MAX = 99
PAD_COLS = 8
PAD_ROWS = 8


def pad_note(row: int, col: int) -> int:
    """row 0 = bottom, col 0 = left."""
    return PAD_NOTE_MIN + row * PAD_COLS + col


def is_pad(note: int) -> bool:
    return PAD_NOTE_MIN <= note <= PAD_NOTE_MAX


# --- Rotary encoders (relative) --------------------------------------------
# The 8 encoders above the display, plus tempo/swing/master. Relative mode:
# value 1..63 = clockwise by N, value 127..65 = counter-clockwise (two's
# complement around 128). See decode_relative().
ENCODER_TRACK_CC = list(range(71, 79))  # 71..78, left-to-right
ENCODER_TEMPO_CC = 14
ENCODER_SWING_CC = 15
ENCODER_MASTER_CC = 79


def decode_relative(value: int) -> int:
    """Push 2 relative encoder value -> signed delta."""
    return value if value < 64 else value - 128


# --- Display row buttons ----------------------------------------------------
BTN_ABOVE_DISPLAY_CC = list(range(102, 110))  # 102..109
BTN_BELOW_DISPLAY_CC = list(range(20, 28))    # 20..27

# --- Transport / global buttons (CC, value 127=press 0=release) -------------
BTN_PLAY = 85
BTN_RECORD = 86
BTN_STOP = 29
BTN_METRONOME = 9
BTN_TAP_TEMPO = 3
BTN_NEW = 87
BTN_DUPLICATE = 88
BTN_AUTOMATE = 89
BTN_FIXED_LENGTH = 90
BTN_QUANTIZE = 116
BTN_UNDO = 119
BTN_DELETE = 118

# --- Button groups (CC) -----------------------------------------------------
# White buttons take a brightness 0..127; RGB buttons take a palette index.
BUTTONS_WHITE = [
    3, 9, 118, 119, 35, 117, 116, 88, 87, 90, 30, 59, 52, 53,
    110, 112, 111, 113, 28, 46, 47, 44, 45, 56, 57, 58, 31, 50,
    51, 55, 54, 62, 63, 49, 48,
]
BUTTONS_RGB = [
    60, 61, 29, 89, 86, 85,
    102, 103, 104, 105, 106, 107, 108, 109,
    20, 21, 22, 23, 24, 25, 26, 27,
    43, 42, 41, 40, 39, 38, 37, 36,
]

# --- LED feedback -----------------------------------------------------------
# Pads: Note On velocity indexes the color palette (default palette indices).
# White buttons: CC value 0 (off) .. 127 (full). RGB buttons: value = palette
# index. These are placeholders for a proper palette module.
PAD_OFF = 0
PAD_WHITE = 122
PAD_GREEN = 126
PAD_RED = 127
PAD_BLUE = 125
