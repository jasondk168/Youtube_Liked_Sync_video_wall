@echo off
set "BASE=%~dp0"
:loop
if exist "%BASE%python.exe" goto found
set "BASE=%BASE%..\"
goto loop
:found
cd /d "%~dp0"
"%BASE%python.exe" -m streamlit run app.py
pause