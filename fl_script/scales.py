# Push2FLStudio  —  Copyright (c) 2026 Bozhidar Slaveykov.
# Licensed under the project's Attribution-Required License (see LICENSE).
# Any use or modification must credit the author: BOZHIDAR SLAVEYKOV.

"""The 23 musical scales FL Studio ships (from FL's harmonicScales.py).

Each scale is the set of in-key semitone degrees relative to the root.
Kept as a local copy because the FL sandbox can't import another script
folder's module.
"""

SCALE_NAMES = (
    "Major", "Harmonic minor", "Melodic minor", "Whole tone", "Diminished",
    "Major penta", "Minor penta", "Jap in sen", "Major bebop", "Dominant bebop",
    "Blues", "Arabic", "Enigmatic", "Neapolitan", "Neap. minor",
    "Hungarian minor", "Dorian", "Phrygian", "Lydian", "Mixolydian",
    "Aeolian", "Locrian", "Chromatic",
)

SCALES = (
    (0, 2, 4, 5, 7, 9, 11),                 # Major
    (0, 2, 3, 5, 7, 8, 11),                 # Harmonic minor
    (0, 2, 3, 5, 7, 9, 11),                 # Melodic minor
    (0, 2, 4, 6, 8, 10),                    # Whole tone
    (0, 2, 3, 5, 6, 8, 9, 11),              # Diminished
    (0, 2, 4, 7, 9),                        # Major penta
    (0, 3, 5, 7, 10),                       # Minor penta
    (0, 1, 5, 7, 10),                       # Jap in sen
    (0, 2, 4, 5, 7, 8, 9, 11),              # Major bebop
    (0, 2, 4, 5, 7, 9, 10, 11),             # Dominant bebop
    (0, 3, 5, 6, 7, 10),                    # Blues
    (0, 1, 4, 5, 7, 8, 11),                 # Arabic
    (0, 1, 4, 6, 8, 10, 11),                # Enigmatic
    (0, 1, 3, 5, 7, 9, 11),                 # Neapolitan
    (0, 1, 3, 5, 7, 8, 11),                 # Neap. minor
    (0, 2, 3, 6, 7, 8, 11),                 # Hungarian minor
    (0, 2, 3, 5, 7, 9, 10),                 # Dorian
    (0, 1, 3, 5, 7, 8, 10),                 # Phrygian
    (0, 2, 4, 6, 7, 9, 11),                 # Lydian
    (0, 2, 4, 5, 7, 9, 10),                 # Mixolydian
    (0, 2, 3, 5, 7, 8, 10),                 # Aeolian
    (0, 1, 3, 5, 6, 8, 10),                 # Locrian
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11), # Chromatic
)

COUNT = len(SCALES)


def in_scale(degree, scale_index):
    return (degree % 12) in SCALES[scale_index]
