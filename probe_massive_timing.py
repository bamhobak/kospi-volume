# -*- coding: utf-8 -*-
"""Massive(옛 Polygon) 무료 플랜이 전날 미장 전 종목을 **한국 시각 몇 시에** 올리는지 잰다 (2026-09-23).

야후는 장 마감 16시간 뒤에도 종가를 비워 두는 날이 있었다(09-22). 공급처를 바꿀 가치가 있으려면
아침 수집(08:30) 전에 올라와야 한다. 미국 장 마감(KST 05:00) 뒤 10분마다 grouped daily 를 불러
처음으로 5,000종목 넘게 들어온 시각을 적는다. 무료 한도(분당 5콜)에 한참 못 미친다.

    python probe_massive_timing.py 2026-09-23        # 그날 장 자료를 기다린다
로그: data/us/massive_timing.log
"""
import sys, time
from datetime import datetime
from pathlib import Path
import requests

BASE = Path(__file__).parent
LOG = BASE / "data" / "us" / "massive_timing.log"
DAY = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime("%Y-%m-%d")
KEY = [l.split("=", 1)[1].strip() for l in (BASE / ".env").read_text(encoding="utf-8").splitlines()
       if l.startswith("MASSIVE_API_KEY=")][0]


def say(m):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%m-%d %H:%M:%S} {m}\n")


say(f"=== {DAY} 자료 기다림 시작")
end = time.time() + 16 * 3600
while time.time() < end:
    try:
        j = requests.get(f"https://api.massive.com/v2/aggs/grouped/locale/us/market/stocks/{DAY}",
                         params={"adjusted": "true", "apiKey": KEY}, timeout=60).json()
        n = j.get("resultsCount") or 0
        say(f"  {j.get('status')} · {n:,}종목")
        if n > 5000:
            say(f"=== 올라옴: {DAY} 자료 {n:,}종목")
            break
    except Exception as e:
        say(f"  실패 {str(e)[:80]}")
    time.sleep(600)
