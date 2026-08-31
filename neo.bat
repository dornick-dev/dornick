@echo off
rem neo'yu baslatir — cift tikla ya da herhangi bir terminalden "neo" yaz.
rem `py` baslaticisi Windows'un kendi klasorunde: aktif venv olsa da olmasa da
rem ayni (global) Python'u kullanir; "neocp bulunamadi" derdi bitmistir.
rem Acilis eski neo orneklerini kendisi temizler (hayalet avi).
cd /d "%~dp0"
rem Her zaman bu depodaki src — site-packages'taki eski kopya layout'u bozmasin.
set "PYTHONPATH=%~dp0src"
rem pywebview su an 3.13'te; varsayilan `py` 3.14 olunca pencere acilmiyor.
set "NEO_KEEP_INTERPRETER=1"
py -3.13 -m neocp --app %*
if errorlevel 1 python -m neocp --app %*
