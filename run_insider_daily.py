# -*- coding: utf-8 -*-
"""DART 내부자 공시 수집 — 예약 작업(BamhobakInsiderDaily)이 매일 밤 부르는 실행기 (2026-09-20).

왜 .cmd 대신 이것인가: 예약 작업이 cmd.exe 를 부르면 **검은 창이 1분쯤 떠 있다** (사용자 지적).
창을 없애는 정공법은 작업을 '로그온 여부와 무관하게 실행'(S4U)으로 바꾸는 것인데 관리자 권한이 필요해
거부됐다. 대신 **콘솔이 없는 pythonw.exe** 로 부르면 창이 뜨지 않는다.
옛 run_insider_daily.ps1(숨긴 파워셸 + Bypass)은 백신(Malware Zero)이 악성으로 오인해 작업을 지웠었다 —
평범한 파이썬이라 그 휴리스틱에는 걸리지 않는다.

기록은 예전 .cmd 와 같은 형식으로 insider_task.log 에 이어 쓴다(시작·종료·종료코드).

    예약 작업 명령:  pythonw.exe -u G:\vscode\kospi-volume\run_insider_daily.py
"""
import subprocess, sys, time
from pathlib import Path

BASE = Path(__file__).resolve().parent
LOG = BASE / "insider_task.log"
NO_WINDOW = 0x08000000          # CREATE_NO_WINDOW — 자식 파이썬도 창을 띄우지 않는다


def say(m):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write("=== %s %s ===\n" % (m, time.strftime("%Y-%m-%d %H:%M:%S")))


say("task start")
try:
    r = subprocess.run([sys.executable.replace("pythonw.exe", "python.exe"), "collect_insider.py"],
                       cwd=str(BASE), creationflags=NO_WINDOW,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=4 * 3600)
    code = r.returncode
except Exception as e:
    code = "예외 %r" % (e,)
say("task end exit=%s" % code)
