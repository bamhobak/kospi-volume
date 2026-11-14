@echo off
chcp 65001 >nul
rem 2026-11-14 효율화 감시 스윙·반대매매 판(매주 토 10:00 \BamhobakFactory\DecayWeekly) — 가는 패널 → 스윙 신호표 → 감시. 단계마다 RAM 확인·memguard 10GB.
cd /d C:\vscode\kospi-volume
set PY=C:\Users\bamhobak\AppData\Local\Python\pythoncore-3.14-64\python.exe
set LOG=data\decay\weekly.log
echo ===== %date% %time% >> %LOG%
%PY% -X utf8 research\ramcheck.py 12 >> %LOG% 2>&1 || goto skip
%PY% -X utf8 research\memguard.py research\slim_panels.py kp >> %LOG% 2>&1 || goto fail
%PY% -X utf8 research\memguard.py research\slim_panels.py kq >> %LOG% 2>&1 || goto fail
set MIX_DUMP_ONLY=1
%PY% -X utf8 research\memguard.py research\mix_swing_1114.py >> %LOG% 2>&1 || goto fail
set MIX_DUMP_ONLY=
%PY% -X utf8 research\decay_watch.py --swing >> %LOG% 2>&1
echo 끝 %time% >> %LOG%
goto :eof
:skip
echo 남은 램 모자라 건너뜀 >> %LOG%
goto :eof
:fail
echo 중간 실패 — 감시는 지난 신호표로 >> %LOG%
%PY% -X utf8 research\decay_watch.py --swing >> %LOG% 2>&1
