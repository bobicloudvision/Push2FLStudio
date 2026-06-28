# Push2FLStudio  —  Copyright (c) 2026 Bozhidar Slaveykov.
# Licensed under the project's Attribution-Required License (see LICENSE).
# Any use or modification must credit the author: BOZHIDAR SLAVEYKOV.

"""PyInstaller entry point — builds to a single self-contained binary so end
users don't need Python. See build-binary.sh."""

import sys

from display_daemon.app import main

if __name__ == "__main__":
    sys.exit(main())
