@echo off
rem neo'yu baslatir — cift tikla ya da herhangi bir terminalden "neo" yaz.
rem `py` baslaticisi Windows'un kendi klasorunde: aktif venv olsa da olmasa da
rem ayni (global) Python'u kullanir; "neocp bulunamadi" derdi bitmistir.
rem Acilis eski neo orneklerini kendisi temizler (hayalet avi).
cd /d "%~dp0"
py -m neocp --app %*
