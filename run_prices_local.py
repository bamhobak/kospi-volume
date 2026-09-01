# -*- coding: utf-8 -*-
"""장중 시세 수집 로컬 러너 (PC 작업 스케줄러 'BamhobakPricesLive' 전용).

배경: GitHub Actions 의 예약 실행이 대량 유실된다(2026-09-01 실측 — 하루 41회
예약 중 1회만 실행). 그래서 PC 가 켜져 있는 동안은 이쪽이 주 경로다.

pythonw 로 호출되므로 stdout 이 없다 → prices.py 를 창 없이 돌리고 결과를
prices_local.log 에 한 줄씩 남긴다(최근 400줄 유지).
"""
import datetime as dt, subprocess, sys
from pathlib import Path

BASE = Path(__file__).parent
LOG = BASE / "prices_local.log"
CREATE_NO_WINDOW = 0x08000000

# pythonw.exe 로 실행돼도 자식은 python.exe 로 돌린다(출력을 받기 위해)
exe = sys.executable
if exe.lower().endswith("pythonw.exe"):
    exe = exe[:-len("pythonw.exe")] + "python.exe"

t0 = dt.datetime.now()
try:
    p = subprocess.run([exe, str(BASE / "prices.py")], cwd=BASE, capture_output=True,
                       text=True, encoding="utf-8", errors="replace",
                       creationflags=CREATE_NO_WINDOW, timeout=300)
    out = (p.stdout or "").strip().splitlines()
    tail = out[-1][:160] if out else ""
    line = f"[{t0:%m-%d %H:%M:%S}] rc={p.returncode} ({(dt.datetime.now()-t0).seconds}s) {tail}"
    if p.returncode:
        line += "\n    " + (p.stderr or "").strip()[-300:]
except subprocess.TimeoutExpired:
    line = f"[{t0:%m-%d %H:%M:%S}] 시간 초과(300s) — 건너뜀"
except Exception as e:
    line = f"[{t0:%m-%d %H:%M:%S}] 실행 실패: {str(e)[:200]}"

with open(LOG, "a", encoding="utf-8") as f:
    f.write(line + "\n")

try:                                   # 로그가 무한정 커지지 않게
    lines = LOG.read_text(encoding="utf-8").splitlines()
    if len(lines) > 400:
        LOG.write_text("\n".join(lines[-400:]) + "\n", encoding="utf-8")
except Exception:
    pass
