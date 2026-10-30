@echo off
rem JingJing desktop console launcher
setlocal
set "PYDIR=C:\Users\ASUS\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python"
set "PYW=%PYDIR%\pythonw.exe"
if exist "%PYW%" goto run
set "PYW=pythonw"
:run
start "" "%PYW%" "%~dp0app.py"
endlocal
