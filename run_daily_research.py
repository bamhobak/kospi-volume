# -*- coding: utf-8 -*-
"""연구용 데이터 매일 갱신 — 신용잔고·공매도·밸류에이션·공매도잔고·투자자 11분할.

왜 이 PC 에서 도는가: 이 자료들은 0.6~1.2GB 짜리 로컬 DB 에 쌓인다. GitHub Actions 에는
그 DB 가 없고, 매번 2.5GB 를 캐시로 오르내리게 하면 수집 워크플로가 너무 무거워진다.
**사이트·텔레그램 알림이 쓰는 실전 데이터는 이미 CI 가 매일 받는다.** 여기서 채우는 건
백테스트·연구용 이력이라 하루이틀 밀려도 실전에 지장이 없고, 전부 재개 가능해서
PC 가 꺼져 있던 날은 다음 실행 때 알아서 따라잡는다.

순서(전부 순차 — KRX 는 동시 실행하면 차단된다):
  1) KIS 신용잔고   최근 N일 · 코스피/코스닥      → data/kis/market.db · credit
  2) KIS 공매도     최근 N일 · 코스피/코스닥      → data/kis/market.db · short_sale
  3) KRX 밸류에이션  못 받은 날짜                 → data/krx_daily.db · fundamental
  4) KRX 공매도잔고  못 받은 날짜                 → data/krx_daily.db · short_balance
  5) KRX 11분할     최근 N일 · 날짜별            → data/investor.db · flow11

사용: python run_daily_research.py [--days 10] [--only 1,3]
등록: schtasks 로 매일 20:30 실행(아래 '자동 등록' 참조)
"""
import os, subprocess, sys, time
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # 자식 출력에 깨진 글자가 섞여도 죽지 않게

BASE = Path(__file__).parent
arg = lambda k, d: sys.argv[sys.argv.index(k)+1] if k in sys.argv else d
DAYS = arg("--days", "10")
ONLY = {int(x) for x in arg("--only", "").split(",") if x.strip().isdigit()}
LOG = BASE / "daily_research.log"
PY = sys.executable

STEPS = [
    (1, "신용잔고 코스피",   ["collect_kis.py", "credit", "--days", DAYS, "--market", "KOSPI",  "--workers", "4"]),
    (1, "신용잔고 코스닥",   ["collect_kis.py", "credit", "--days", DAYS, "--market", "KOSDAQ", "--workers", "4"]),
    (2, "공매도 코스피",     ["collect_kis.py", "short",  "--days", DAYS, "--market", "KOSPI",  "--workers", "4"]),
    (2, "공매도 코스닥",     ["collect_kis.py", "short",  "--days", DAYS, "--market", "KOSDAQ", "--workers", "4"]),
    (3, "밸류에이션",        ["collect_krx_daily.py", "fund", "--gap", "1.6"]),
    (4, "공매도잔고",        ["collect_krx_daily.py", "shortbal", "--gap", "1.6"]),
    (5, "투자자 11분할",     ["collect_investor_daily.py", "--days", DAYS, "--gap", "1.8"]),
]

def clean(t):
    """자식 프로세스 출력에 섞인 복원 불가 문자를 지운다(예전에 여기서 죽었다)."""
    return "".join(ch for ch in (t or "") if ch != "�")

def say(m):
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {clean(m)}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f: f.write(line + "\n")

say(f"=== 연구용 일일 갱신 시작 (최근 {DAYS}일) ===")
t0 = time.time(); fail = []
for no, name, cmd in STEPS:
    if ONLY and no not in ONLY: continue
    say(f"[{no}] {name} 시작")
    t = time.time()
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    r = subprocess.run([PY, "-u", *cmd], cwd=str(BASE), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env)
    tail = "\n".join((r.stdout or "").strip().splitlines()[-2:])
    if r.returncode == 0:
        say(f"[{no}] {name} 완료 ({(time.time()-t)/60:.1f}분) {tail[:200]}")
    else:
        fail.append(name)
        err = "\n".join((r.stderr or "").strip().splitlines()[-3:])
        say(f"[{no}] {name} 실패 rc={r.returncode} ({(time.time()-t)/60:.1f}분)\n{err[:400]}")
say(f"=== 끝 ({(time.time()-t0)/60:.1f}분) · 실패 {len(fail)}건 " + (", ".join(fail) if fail else "없음") + " ===")

# 결과 요약
import sqlite3
for db, tabs in (("data/kis/market.db", ("credit", "short_sale")),
                 ("data/krx_daily.db", ("fundamental", "short_balance")),
                 ("data/investor.db", ("flow11",))):
    p = BASE / db
    if not p.exists(): continue
    c = sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=60)
    for t in tabs:
        try:
            n, a, b = c.execute(f"select count(*),min(date),max(date) from {t}").fetchone()
            say(f"  {t:<14} {n:>10,}행  {a}~{b}")
        except Exception as e: say(f"  {t}: {str(e)[:60]}")
    c.close()
sys.exit(1 if fail else 0)
