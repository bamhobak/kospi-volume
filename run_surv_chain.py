# -*- coding: utf-8 -*-
"""미장 생존편향 실측 사슬 — 이름 채우기가 끝나면 나머지를 순서대로 돌린다 (2026-09-23).

  1 match_sec_cik.py   폐지 종목 ↔ SEC 회사번호
  2 us_dead_sec.py     폐지 종목 재무·자사주
  3 us_panel_full.py   생존 + 폐지 패널
  4 us_surv_measure.py 생존만 vs 폐지 포함 — N1~N5

로그: data/us/surv_chain.log (단계마다 출력 전부) · 한 단계라도 실패하면 거기서 멈춘다.
    python run_surv_chain.py --wait
"""
import io, os, subprocess, sys, time
from pathlib import Path

BASE = Path(__file__).parent
LOG = BASE / "data" / "us" / "surv_chain.log"
NAMELOG = BASE / "data" / "us" / "tiingo_names.log"
PY = sys.executable.replace("pythonw.exe", "python.exe")


def say(m):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%H:%M:%S')} {m}\n")


if "--wait" in sys.argv:
    say("이름 채우기가 끝나길 기다린다")
    while "끝: names" not in NAMELOG.read_text(encoding="utf-8", errors="replace"):
        time.sleep(60)
for script in ("match_sec_cik.py", "us_dead_sec.py", "us_panel_full.py", "us_surv_measure.py"):
    say(f"=== {script} 시작")
    r = subprocess.run([PY, "-u", script], cwd=str(BASE), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(r.stdout[-20000:])
        if r.returncode:
            f.write(r.stderr[-5000:])
    say(f"=== {script} 끝 rc={r.returncode}")
    if r.returncode:
        say("실패 — 여기서 멈춘다")
        break
say("사슬 끝")
