"""`py -m dornick` girişi.

Konsol betiği (dornick.exe) hangi ortama kurulduysa oradan çalışır ve sanal
ortam karmaşasında kaybolabiliyor; `py -m dornick --app` ise py başlatıcısının
varsayılan Python'unu kullanır — aktif venv ne olursa olsun aynı kapı.
"""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
