@echo off
cd /d "%~dp0"

echo Dang khoi dong moi truong ao...
call "%USERPROFILE%\miniconda3\Scripts\activate.bat" dichgame

echo Dang chay phan mem...
python main.py

pause