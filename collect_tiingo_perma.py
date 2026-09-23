# -*- coding: utf-8 -*-
"""공개 목록 밖의 옛 폐지 종목을 **Tiingo 고유번호(permaTicker)**로 받는다 (2026-09-24).

왜: collect_tiingo_dead.py 는 공개 목록(supported_tickers.zip)의 '끝난 종목' 만 받았는데, 그 목록은 티커당
한 줄이라 **티커가 재사용되면 옛 회사가 밀려난다.** 그래서 2012 이전 폐지분이 1할도 없었다.
재무 메타(collect_tiingo_meta.py)에는 비활성(폐지) 회사가 12,517곳 있고 고유번호가 붙어 있다.

실측(2026-09-24): 대형 폐지 20개 중 7개가 시세를 준다(메릴린치·XTO·하인즈·월그린·세이프웨이 등).
**티커로 부르면 재사용한 다른 회사가 나온다**(DNA → Ginkgo, EDS → Exceed) — 고유번호로 부르면 옛 회사가
나온다(US000000012555 → 2008 제넨텍 $73.95). 그래서 반드시 고유번호로 부른다.
리먼·베어스턴스·컨트리와이드·와이어스 등은 회사 정보만 있고 시세가 없다(빈 결과) — **2008 공백은 못 메운다.**

대상: 재무 메타 비활성 회사 중 collect_tiingo_dead.py 가 이미 받은 티커를 뺀 곳(약 7,800).
저장: data/us/tiingo_dead.db · pxp(perma, date, …) · metap(perma, ticker, name, isADR) · donep(perma, n, status, at)
    python collect_tiingo_perma.py --per-hour 9000
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
START = arg("--from", "2004-06-01")
DB = BASE / "data" / "us" / "tiingo_dead.db"
COLS = ["open", "high", "low", "close", "volume", "adjOpen", "adjHigh", "adjLow", "adjClose",
        "adjVolume", "divCash", "splitFactor"]


def log(m):
    print(f"{time.strftime('%H:%M:%S')} {m}", flush=True)


def main():
    tok = [l.split("=", 1)[1].strip() for l in (BASE / ".env").read_text(encoding="utf-8").splitlines()
           if l.startswith("TIINGO_TOKEN=")][0]
    c = sqlite3.connect(DB, timeout=600)
    c.executescript(f"""
    create table if not exists pxp(perma text, date text, {', '.join(x + ' real' for x in COLS)}, primary key(perma, date));
    create table if not exists metap(perma text primary key, ticker text, name text, isADR integer);
    create table if not exists donep(perma text primary key, n integer, status text, at text);""")
    F = pd.read_pickle(BASE / "data" / "us" / "tiingo_fund_meta.pkl")
    F = F[~F.isActive & F.permaTicker.notna()]
    have = {r[0] for r in c.execute("select ticker from meta")}
    T = F[~F.ticker.isin(have)]
    c.executemany("insert or replace into metap values(?,?,?,?)",
                  [(p, t, n, int(a)) for p, t, n, a in zip(T.permaTicker, T.ticker, T.name, T.isADR)])
    c.commit()
    done = {r[0] for r in c.execute("select perma from donep where status in ('ok','empty')")}
    todo = [p for p in T.permaTicker if p not in done]
    log(f"대상 {len(T):,} · 남은 {len(todo):,} · 시간당 {PER_HOUR} · 예상 {len(todo) / PER_HOUR * 60:.0f}분")

    gap, lock, slot = 3600.0 / PER_HOUR, threading.Lock(), [time.time()]

    def fetch(p):
        with lock:
            wait = slot[0] - time.time()
            slot[0] = max(slot[0], time.time()) + gap
        if wait > 0:
            time.sleep(wait)
        for att in range(3):
            try:
                r = requests.get(f"https://api.tiingo.com/tiingo/daily/{p}/prices",
                                 params={"token": tok, "startDate": START}, timeout=90)
                break
            except Exception as e:
                if att == 2:
                    return p, "net", str(e)[:60]
                time.sleep(5 * (att + 1))
        if r.status_code == 429 or (r.status_code >= 400 and "limit" in r.text[:200].lower()):
            return p, "limit", r.text[:120]
        if r.status_code == 404:
            return p, "404", None
        try:
            j = r.json()
        except Exception:
            return p, "parse", r.text[:80]
        if not isinstance(j, list):
            return p, "bad", str(j)[:80]
        return p, "ok", [(p, x["date"][:10].replace("-", ""), *[x.get(k) for k in COLS]) for x in j]

    n, rows, t0 = 0, 0, time.time()
    with ThreadPoolExecutor(WORKERS) as ex:
        for p, st, v in ex.map(fetch, todo):
            n += 1
            if st == "limit":
                log(f"  한도({v}) — 멈춘다. 다시 돌리면 이어 받는다."); break
            if st in ("net", "parse"):
                continue
            if st == "ok" and v:
                c.executemany(f"insert or replace into pxp values({','.join('?' * (2 + len(COLS)))})", v)
                rows += len(v)
            c.execute("insert or replace into donep values(?,?,?,?)",
                      (p, len(v) if st == "ok" and v else 0,
                       ("ok" if v else "empty") if st == "ok" else st, time.strftime("%F %T")))
            if n % 200 == 0:
                c.commit()
                el = time.time() - t0
                log(f"  {n:,}/{len(todo):,} · {rows:,}행 · {el / 60:.1f}분 · 남은 {(len(todo) - n) * el / n / 60:.0f}분")
    c.commit()
    k, m = c.execute("select count(*), sum(status='ok') from donep").fetchone()
    log(f"끝: 고유번호 {k:,}곳 중 시세 있음 {m:,} · 이번 {rows:,}행")
    c.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
