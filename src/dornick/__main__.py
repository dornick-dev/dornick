"""The `py -m dornick` entry point.

The console script (dornick.exe) runs from whichever environment it was
installed into and can get lost in virtual-environment tangles;
`py -m dornick --app` uses the py launcher's default Python — the same
door regardless of the active venv.
"""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
