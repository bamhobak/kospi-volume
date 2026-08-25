@echo off
cd /d "%~dp0"
python pipeline.py
start "" http://127.0.0.1:8765/
python -m http.server 8765 -d site
