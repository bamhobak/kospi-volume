# -*- coding: utf-8 -*-
"""2018년 이전 보조자료 과거 백필 — 우선순위 순서대로.

시세는 2005년까지 있는데 규칙이 쓰는 보조자료는 2018년부터라 2008·2011년 폭락에서
규칙 검증이 반쪽이었다. 실측으로 확인한 시작 가능 시점대로 받는다.
  1) 신용잔고    2008~   KIS 종목별   [폭락반등]의 핵심 축
  2) 밸류에이션  2005~   KRX 날짜별   [저PBR 낙폭] 을 시점 PBR 로 재검증
  3) 공매도 거래량 2005~ KRX 날짜별   규칙 5개가 쓰는 공매도 비중
  4) 공매도 잔고  2016~   KRX 날짜별
  5) 지수 편입    2014~   KRX 월별
⚠ KRX 는 순차로만. 도는 동안 data/.backfill_lock 을 잡아 일일 갱신 작업이 비켜가게 한다.
병렬: KIS(1번)와 KRX(2~5번)는 서로 다른 서비스라 동시에 돌려도 된다. 실제로 두 갈래로 나눠 돌린다.
        python backfill_aux.py --only 1      (KIS 신용잔고)
        python backfill_aux.py --only 2,3,4,5 (KRX 순차)
사용: python backfill_aux.py [--only 1,2]
"""
import os, subprocess, sys, time
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = Path(__file__).parent
LOCK = BASE / "data" / ".backfill_lock"
LOG = BASE / "backfill_aux.log"
PY = sys.executable
arg = lambda k, d: sys.argv[sys.argv.index(k)+1] if k in sys.argv else d
ONLY = {int(x) for x in arg("--only", "").split(",") if x.strip().isdigit()}

# ⚠ --fill-before 가 핵심: done 표시된 종목도 그 날짜 이전 이력이 없으면 받는다.
#   이게 없으면 2,916종목 중 415종목만 받고 끝난다(2026-09-05 실측).
STEPS = [
 (1, "신용잔고 2008~ 코스피",  ["collect_kis.py","credit","--from","20080101","--fill-before","20180102","--market","KOSPI","--workers","4"]),
 (1, "신용잔고 2008~ 코스닥",  ["collect_kis.py","credit","--from","20080101","--fill-before","20180102","--market","KOSDAQ","--workers","4"]),
 (2, "밸류에이션 2005~",       ["collect_krx_daily.py","fund","--from","20050103","--gap","1.6"]),
 (3, "공매도 거래량 2005~",     ["collect_krx_daily.py","shortvol","--from","20050103","--gap","1.6"]),
 (4, "공매도 잔고 2016~",      ["collect_krx_daily.py","shortbal","--from","20160601","--gap","1.6"]),
 (5, "지수 편입 2014~",        ["collect_index_members.py"]),
]
def say(m):
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} " + "".join(c for c in str(m) if c != "\ufffd")
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f: f.write(line + "\n")

LOCK.parent.mkdir(parents=True, exist_ok=True)
MINE = str(os.getpid())
if not LOCK.exists(): LOCK.write_text(MINE, encoding="utf-8")   # 이미 다른 갈래가 잡았으면 그대로 둔다
say(f"=== 보조자료 과거 백필 시작 (잠금 {LOCK.name}) ===")
t0 = time.time(); fail = []
try:
    for no, name, cmd in STEPS:
        if ONLY and no not in ONLY: continue
        say(f"[{no}] {name} 시작"); t = time.time()
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        r = subprocess.run([PY, "-u", *cmd], cwd=str(BASE), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", env=env)
        tail = "\n".join((r.stdout or "").strip().splitlines()[-2:])
        if r.returncode == 0: say(f"[{no}] {name} 완료 ({(time.time()-t)/3600:.1f}시간) {tail[:200]}")
        else:
            fail.append(name)
            say(f"[{no}] {name} 실패 rc={r.returncode}\n" + "\n".join((r.stderr or "").strip().splitlines()[-3:])[:400])
        if LOCK.exists() and LOCK.read_text(encoding="utf-8").strip() == MINE:
            LOCK.write_text(MINE, encoding="utf-8")             # 내 잠금이면 시각만 갱신
finally:
    # 남의 잠금은 건드리지 않는다(KIS 갈래와 KRX 갈래를 병렬로 돌리기 때문)
    try:
        if LOCK.exists() and LOCK.read_text(encoding="utf-8").strip() == MINE: LOCK.unlink()
    except Exception: pass
say(f"=== 끝 ({(time.time()-t0)/3600:.1f}시간) · 실패 {len(fail)}건 " + (", ".join(fail) if fail else "없음") + " ===")
import sqlite3
for db, tabs in (("data/kis/market.db", ("credit",)), ("data/krx_daily.db", ("fundamental","short_volume","short_balance")),
                 ("data/index_members.db", ("members",))):
    p = BASE / db
    if not p.exists(): say(f"  {db} (없음)"); continue
    c = sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=60)
    for t in tabs:
        try:
            n, a, b = c.execute(f"select count(*),min(date),max(date) from {t}").fetchone()
            say(f"  {t:<15} {n:>10,}행  {a}~{b}")
        except Exception as e: say(f"  {t}: {str(e)[:50]}")
    c.close()
