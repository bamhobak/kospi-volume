# -*- coding: utf-8 -*-
"""폐지 종목의 **회사 이름·사업 설명·거래소**를 채운다 — SEC 재무와 짝을 맞추기 위한 재료 (2026-09-23).

재무 메타(collect_tiingo_meta.py)로 이름이 채워진 종목은 건너뛰고, 빈 것만 종목별 일봉 메타
(/tiingo/daily/<티커>)로 부른다. 대상은 A(거래소 폐지)·B(장외 파산주)만 — C(장외 일반)는 대부분
SEC 에 재무를 안 내는 외국 장외 종목이라 이름을 알아도 재무를 못 붙인다(--with-otc 로 넣을 수 있다).

시세 수집(collect_tiingo_dead.py)과 시간당 한도(1만)를 나눠 쓰면 둘 다 느려지므로, --wait 를 주면
그 수집기 로그에 '끝:' 이 찍힐 때까지 기다렸다가 시작한다.

저장: data/us/tiingo_dead.db · names(ticker, name, description, exchangeCode, startDate, endDate, src)
    python collect_tiingo_names.py --wait
"""
import io, os, sqlite3, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pandas as pd, requests

BASE = Path(__file__).parent
for _n in ("stdout", "stderr"):
    _f = getattr(sys, _n, None)
    if _f is None:
        setattr(sys, _n, io.open(os.devnull, "w", encoding="utf-8"))
    else:
        try: _f.reconfigure(encoding="utf-8", errors="replace")
        except Exception: pass

arg = lambda k, d=None: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d
PER_HOUR = int(arg("--per-hour", "9000"))
WORKERS = int(arg("--workers", "4"))
DB = BASE / "data" / "us" / "tiingo_dead.db"
DEADLOG = BASE / "data" / "us" / "tiingo_dead.log"


def log(m):
    print(f"{time.strftime('%H:%M:%S')} {m}", flush=True)


def token():
    for line in (BASE / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("TIINGO_TOKEN="):
            return line.split("=", 1)[1].strip()
    raise SystemExit(".env 에 TIINGO_TOKEN 이 없다")


def wait_for_prices():
    """시세 수집기 로그의 마지막 '대상' 줄 뒤에 '끝:' 이 나올 때까지 기다린다."""
    log("시세 수집이 끝나길 기다린다")
    while True:
        try:
            t = DEADLOG.read_text(encoding="utf-8", errors="replace")
        except Exception:
            t = ""
        tail = t[t.rfind("대상 "):] if "대상 " in t else t
        if "끝: px" in tail:
            log("시세 수집 끝남 — 시작")
            return
        time.sleep(60)


def main():
    if "--wait" in sys.argv:
        wait_for_prices()
    tok = token()
    c = sqlite3.connect(DB, timeout=600)
    c.execute("""create table if not exists names(ticker text primary key, name text, description text,
                 exchangeCode text, startDate text, endDate text, src text)""")
    c.commit()
    M = pd.read_sql("select ticker, grp from meta", c)
    grps = {"A", "B", "C"} if "--with-otc" in sys.argv else {"A", "B"}
    M = M[M.grp.isin(grps)]
    F = pd.read_pickle(BASE / "data" / "us" / "tiingo_fund_meta.pkl")
    F = F[F.name.notna()]
    fm = dict(zip(F.ticker, F.name))
    # 재무 메타에 이름이 있으면 그걸로 먼저 채운다(호출 없이)
    have = M[M.ticker.isin(fm)]
    c.executemany("insert or ignore into names(ticker, name, src) values(?,?,'fund_meta')",
                  [(t, fm[t]) for t in have.ticker])
    c.commit()
    done = {r[0] for r in c.execute("select ticker from names where src='daily_meta'")}
    todo = [t for t in M.ticker if t not in fm and t not in done]
    log(f"대상 {len(M):,} · 재무 메타로 채움 {len(have):,} · 부를 것 {len(todo):,} · 예상 {len(todo) / PER_HOUR * 60:.0f}분")

    gap, lock, slot = 3600.0 / PER_HOUR, threading.Lock(), [time.time()]

    def fetch(tk):
        with lock:
            wait = slot[0] - time.time()
            slot[0] = max(slot[0], time.time()) + gap
        if wait > 0:
            time.sleep(wait)
        for att in range(3):
            try:
                r = requests.get(f"https://api.tiingo.com/tiingo/daily/{tk}", params={"token": tok}, timeout=60)
                if r.status_code == 429 or (r.status_code >= 400 and "limit" in r.text[:200].lower()):
                    return tk, "limit", r.text[:120]
                j = r.json()
                return tk, ("ok" if isinstance(j, dict) and j.get("ticker") else "bad"), j
            except Exception as e:
                if att == 2:
                    return tk, "net", str(e)[:60]
                time.sleep(5 * (att + 1))

    n = ok = 0
    t0 = time.time()
    with ThreadPoolExecutor(WORKERS) as ex:
        for tk, st, j in ex.map(fetch, todo):
            n += 1
            if st == "limit":
                log(f"  한도({j}) — 멈춘다. 다시 돌리면 이어 받는다."); break
            if st == "ok":
                c.execute("insert or replace into names values(?,?,?,?,?,?,'daily_meta')",
                          (tk, j.get("name"), j.get("description"), j.get("exchangeCode"),
                           j.get("startDate"), j.get("endDate")))
                ok += 1
            if n % 200 == 0:
                c.commit()
                log(f"  {n:,}/{len(todo):,} · 이름 {ok:,} · {(time.time() - t0) / 60:.1f}분")
    c.commit()
    tot, nm = c.execute("select count(*), sum(name is not null and name != '') from names").fetchone()
    log(f"끝: names {tot:,}종목 · 이름 있음 {nm:,}")
    c.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
