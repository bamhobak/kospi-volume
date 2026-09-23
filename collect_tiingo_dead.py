# -*- coding: utf-8 -*-
"""미장 **상장폐지 종목** 일봉을 Tiingo 에서 받는다 — 생존편향을 없애기 위한 원료 (2026-09-23).

왜: 미국 패널(us_scan.pkl)은 **지금 상장된 종목만**으로 과거를 거슬러 만든 판이라, 중간에 망하거나
인수된 종목이 통째로 없다. 그래서 미장 규칙 성적은 부풀려져 있고 2016 이전은 검증을 못 했다
([[kr-holdout-2005-2015]] · [[lookahead-surv]]).

Tiingo 를 고른 이유(실측):
  · 공개 목록(supported_tickers.zip, 키 불필요)에 **끝난 종목이 폐지일과 함께** 있다.
  · 파산주는 **마지막 티커(Q)로 상장 시절부터 이력이 이어진다** — BBBYQ 2015 $76.73 → 2023 $0.08,
    SIVBQ 2023-03-09 $106(거래정지) → 03-28 장외 $0.40. 빠진 날 0일(BBBYQ·TWTR).
  · 우리 값과 맞는다 — 우리 close = Tiingo adjClose(0.005~0.04%), rawclose = Tiingo close(0.03% 이내).

대상 묶음:
  A  미국 거래소(NYSE·NASDAQ·AMEX 등)에서 2016 이후 끝난 보통주 ~5,600
  B  장외(PINK·OTC)로 내려간 파산주 — 티커가 Q 로 끝남        ~770
  C  장외 일반(2016 이전 시작) — 옛 상장사와 외국 ADR 이 섞임       ~9,600  (--with-otc 일 때만)

요금제: 무료는 **월 500종목** · 시간당 50 · 하루 1,000. A+B 만 해도 6,400종목이라 유료(Power, 시간당 1만)가 필요하다.
요청 속도는 --per-hour 로 맞춘다(무료 45 · Power 9000). 한도에 걸리면 멈추고, 다시 돌리면 이어 받는다.

저장: data/us/tiingo_dead.db
  px(ticker, date, open, high, low, close, volume, adjOpen, adjHigh, adjLow, adjClose, adjVolume, divCash, splitFactor)
  meta(ticker, exchange, startDate, endDate, grp)
  done(ticker, n, status, at)       — 재개키

    python collect_tiingo_dead.py --plan              # 몇 종목인지 세기만
    python collect_tiingo_dead.py --limit 3           # 시험 3종목
    python collect_tiingo_dead.py --per-hour 9000     # Power 요금제로 전부
"""
import io, os, sqlite3, sys, time, zipfile
from pathlib import Path
import pandas as pd, requests

BASE = Path(__file__).parent
for _n in ("stdout", "stderr"):                      # pythonw(예약 작업)에서는 None 이다
    _f = getattr(sys, _n, None)
    if _f is None:
        setattr(sys, _n, io.open(os.devnull, "w", encoding="utf-8"))
    else:
        try: _f.reconfigure(encoding="utf-8", errors="replace")
        except Exception: pass

arg = lambda k, d=None: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d
PER_HOUR = int(arg("--per-hour", "45"))
LIMIT = int(arg("--limit", "0"))
START = arg("--from", "2004-06-01")          # 2005~15 과거 검증까지 하려면 여기부터 필요하다
ENDED = arg("--ended-since", "2005-01-01")    # 이 날 이후 끝난 종목을 받는다
WORKERS = int(arg("--workers", "4"))
WITH_OTC = "--with-otc" in sys.argv
DB = BASE / "data" / "us" / "tiingo_dead.db"
LIST_URL = "https://apimedia.tiingo.com/docs/tiingo/daily/supported_tickers.zip"
LISTED = {"NYSE", "NASDAQ", "AMEX", "NYSE MKT", "NYSE ARCA", "BATS"}
OTC = {"PINK", "OTCMKTS", "EXPM", "OTCQX", "OTCQB", "OTCBB", "OTCGREY", "OTCCE", "GREY"}
COLS = ["open", "high", "low", "close", "volume", "adjOpen", "adjHigh", "adjLow", "adjClose",
        "adjVolume", "divCash", "splitFactor"]


def log(m):
    print(f"{time.strftime('%H:%M:%S')} {m}", flush=True)


def token():
    for line in (BASE / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("TIINGO_TOKEN="):
            return line.split("=", 1)[1].strip()
    raise SystemExit(".env 에 TIINGO_TOKEN 이 없다")


def targets():
    r = requests.get(LIST_URL, timeout=120)
    d = pd.read_csv(zipfile.ZipFile(io.BytesIO(r.content)).open("supported_tickers.csv"))
    d = d[(d.assetType == "Stock") & d.ticker.notna()].copy()
    d["ticker"] = d.ticker.astype(str).str.upper()
    # 보통주만 — 우선주(-P-HIZ)·발행 전 거래(AA-W)·권리·유닛은 기호가 붙는다. 우리 패널도 보통주만이다.
    d = d[d.ticker.str.fullmatch(r"[A-Z]{1,5}")]
    e = pd.to_datetime(d.endDate, errors="coerce")
    s = pd.to_datetime(d.startDate, errors="coerce")
    q = d.ticker.str.endswith("Q")
    today = pd.Timestamp.today().normalize() - pd.Timedelta(days=20)
    A = d[d.exchange.isin(LISTED) & (e >= ENDED) & (e < today)].assign(grp="A")
    B = d[d.exchange.isin(OTC) & q & (e >= ENDED)].assign(grp="B")
    parts = [A, B]
    if WITH_OTC:
        parts.append(d[d.exchange.isin(OTC) & ~q & (s <= "2016-01-01") & (e >= ENDED)].assign(grp="C"))
    T = pd.concat(parts).drop_duplicates("ticker")
    # 파산주(B)부터 — 생존편향에 제일 큰 몫(몽땅 잃은 종목)이라 무료 한도로 조금씩 받을 때도 먼저 채운다.
    T = T.assign(_o=T.grp.map({"B": 0, "A": 1, "C": 2})).sort_values(["_o", "ticker"]).drop(columns="_o")
    return T[["ticker", "exchange", "startDate", "endDate", "grp"]]


def setup():
    DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB, timeout=600)
    c.executescript(f"""
    create table if not exists px(ticker text, date text, {', '.join(x + ' real' for x in COLS)},
                                  primary key(ticker, date));
    create table if not exists meta(ticker text primary key, exchange text, startDate text, endDate text, grp text);
    create table if not exists done(ticker text primary key, n integer, status text, at text);""")
    c.commit()
    return c


def main():
    T = targets()
    log("대상 " + " · ".join(f"{g} {n:,}" for g, n in T.grp.value_counts().sort_index().items())
        + f" = {len(T):,}종목")
    if "--plan" in sys.argv:
        return 0
    tok, c = token(), setup()
    c.executemany("insert or replace into meta values(?,?,?,?,?)", T.itertuples(index=False))
    c.commit()
    done = {r[0] for r in c.execute("select ticker from done where status in ('ok','empty')")}
    todo = [t for t in T.ticker if t not in done]
    if LIMIT:
        todo = todo[:LIMIT]
    log(f"남은 {len(todo):,} (완료 {len(done):,}) · 시간당 {PER_HOUR} · 예상 {len(todo) / PER_HOUR:.1f}시간")
    # 동시에 WORKERS 개씩 요청하되, 전체 속도는 시간당 PER_HOUR 를 넘지 않게 한 줄로 세운다.
    # (한 개씩 받으면 응답 대기만으로 시간당 3~4천이 한계라 1만7천 종목에 5시간이 걸린다.)
    import threading
    from concurrent.futures import ThreadPoolExecutor
    gap, lock, slot = 3600.0 / PER_HOUR, threading.Lock(), [time.time()]
    stop = threading.Event()

    def fetch(tk):
        if stop.is_set():
            return tk, "skip", None
        with lock:
            wait = slot[0] - time.time()
            slot[0] = max(slot[0], time.time()) + gap
        if wait > 0:
            time.sleep(wait)
        for att in range(3):
            try:
                r = requests.get(f"https://api.tiingo.com/tiingo/daily/{tk}/prices",
                                 params={"token": tok, "startDate": START}, timeout=90)
                break
            except Exception as e:
                if att == 2:
                    return tk, "net", str(e)[:60]
                time.sleep(5 * (att + 1))
        if r.status_code == 429 or (r.status_code >= 400 and "limit" in r.text[:200].lower()):
            stop.set()
            return tk, "limit", f"{r.status_code} {r.text[:120]}"
        if r.status_code == 404:
            return tk, "404", None
        try:
            j = r.json()
        except Exception:
            return tk, "parse", f"{r.status_code} {r.text[:100]}"
        if not isinstance(j, list):
            return tk, "bad", str(j)[:120]
        return tk, "ok", [(tk, x["date"][:10].replace("-", ""), *[x.get(k) for k in COLS]) for x in j]

    t0, rows, n = time.time(), 0, 0
    with ThreadPoolExecutor(WORKERS) as ex:
        for tk, st, v in ex.map(fetch, todo):
            if st == "skip":
                continue
            if st == "limit":
                log(f"  요금제 한도에 걸렸다({v}) — 멈춘다. 다시 돌리면 이어 받는다.")
                continue
            if st in ("net", "parse"):
                log(f"  {tk} {st} 실패 {v}")           # done 에 안 적는다 → 다음 실행에서 다시
                continue
            if st == "ok":
                c.executemany(f"insert or replace into px values({','.join('?' * (2 + len(COLS)))})", v)
                rows += len(v)
            c.execute("insert or replace into done values(?,?,?,?)",
                      (tk, len(v) if st == "ok" else 0, ("ok" if v else "empty") if st == "ok" else st,
                       time.strftime("%F %T")))
            n += 1
            if n % 200 == 0:
                c.commit()
                el = time.time() - t0
                log(f"  {n:,}/{len(todo):,} · {rows:,}행 · {el / 60:.1f}분 · 남은 {(len(todo) - n) * el / n / 60:.0f}분")
    c.commit()
    n, k = c.execute("select count(*), count(distinct ticker) from px").fetchone()
    log(f"끝: px {n:,}행 · {k:,}종목")
    c.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
