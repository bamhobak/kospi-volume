# -*- coding: utf-8 -*-
"""1분봉 수집기 — 단타 규칙 연구용 (2026-10-03 사용자: "수집기 만들어줘").

토스 Open API 1분봉(REST)을 **정규장만** 모은다. 실시간 소켓은 계정당 200종목이 한계라 전 종목 연구 재료로는
REST 가 맞다(장 끝나고 그날 것을 받는다). 단타 규칙이 생기면 그때 후보 종목만 소켓으로 본다.

과거가 언제부터 쓸 만한가(2026-10-03 실측):
  국장  2022-12-01~  — 2022-11 까지는 1분 거래량이 실제의 1%도 안 된다(삼성전자 2시간 합 1.5만주 vs 정상 300만주+)
  미장  2021-12-01~  — 그 전은 비어 있다
봉 시각은 **봉이 끝난 시각**이다(토스 FAQ) — 국장 09:00 시가 단일가는 09:01 봉, 15:30 종가 단일가는 15:31 봉.
  국장 정규장 = 09:01~15:31 봉 · 미장 정규장 = 뉴욕 09:31~16:00 봉(+16:01 이 있으면 종가 경매)

저장(이 PC · 깃에 안 올림):
  data/m1/{KR|US}/day/YYYYMMDD.parquet   매일 수집 — 그날 전 종목
  data/m1/{KR|US}/bf/{티커}.parquet       과거 채우기 — 종목 하나의 시작일~채운 날
  열: t(티커) ts(봉 끝 시각, UTC 초) o h l c v
쓰는 법:
  python collect_m1.py daily kr        장 끝난 뒤(16:05) — 오늘 국장 전 종목
  python collect_m1.py daily us        06:35 — 방금 끝난 미장 전 종목(서머타임 자동)
  python collect_m1.py backfill --hours 22   거래대금 상위(국장 500·미장 1000)부터 과거 채우기, 시간 다 되면 멈추고 다음에 이어서
  python collect_m1.py status          얼마나 모였나
⚠ 토큰은 autotrade·collect_toss 와 같은 캐시(toss.token) — 따로 받으면 서로를 끊는다.
⚠ 시세 API 는 초당 10회 — 여기선 초당 ~7회로 줄이고, 매일 수집이 도는 동안 과거 채우기는 쉰다(.busy 파일).
⚠ 예약작업(pythonw)은 sys.stdout 이 None — log() 로만 쓴다.
"""
import datetime as dt, json, sys, time, urllib.parse, urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))
import toss

ROOT = BASE / "data" / "m1"; ROOT.mkdir(parents=True, exist_ok=True)
LOG = ROOT / "run.log"; BUSY = ROOT / ".busy"
if sys.stdout is not None:
    try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass
KST, NY = ZoneInfo("Asia/Seoul"), ZoneInfo("America/New_York")
START = {"KR": "20221201", "US": "20211201"}
TOP = {"KR": 500, "US": 1000}
EXTRA = {"KR": ["069500", "229200"], "US": ["SPY", "QQQ", "IWM"]}     # 시장 잣대용 ETF
GAP = 0.14                                                          # 초당 ~7회


def log(*a):
    s = time.strftime("%Y-%m-%d %H:%M:%S ") + " ".join(str(x) for x in a)
    try:
        with open(LOG, "a", encoding="utf-8") as f: f.write(s + "\n")
    except Exception: pass
    if sys.stdout is not None:
        try: print(s, flush=True)
        except Exception: pass


_last = [0.0]


def get(path, **q):
    u = toss.B + path + "?" + urllib.parse.urlencode(q)
    for att in range(6):
        w = GAP - (time.time() - _last[0])
        if w > 0: time.sleep(w)
        _last[0] = time.time()
        try:
            rq = urllib.request.Request(u, headers={"Authorization": "Bearer " + toss.token(), "Accept": "application/json"})
            return json.loads(urllib.request.urlopen(rq, timeout=30).read().decode()).get("result")
        except urllib.error.HTTPError as ex:
            if ex.code == 401 and att == 0:
                toss._TOK.update(v=None, exp=0)
                try: (BASE / "data" / ".toss_token.json").unlink()
                except Exception: pass
                continue
            if ex.code == 429 or ex.code >= 500:
                time.sleep(2 * (att + 1)); continue
            if ex.code in (400, 404):
                return None                                       # 그 종목에 없는 것 — 다시 물어도 같다
            raise
        except Exception:
            time.sleep(3 * (att + 1))
    raise RuntimeError("반복 실패 " + path)


def ts_utc(s):
    return int(dt.datetime.fromisoformat(s).timestamp())


def window(mk, day):
    """그 날 정규장 봉 범위(봉 끝 시각, UTC 초)와 첫 요청 before."""
    y, m, d = int(day[:4]), int(day[4:6]), int(day[6:])
    if mk == "KR":
        a = dt.datetime(y, m, d, 9, 1, tzinfo=KST); b = dt.datetime(y, m, d, 15, 31, tzinfo=KST)
    else:
        a = dt.datetime(y, m, d, 9, 31, tzinfo=NY); b = dt.datetime(y, m, d, 16, 1, tzinfo=NY)
    return int(a.timestamp()), int(b.timestamp()), b.astimezone(KST).isoformat()


def fetch_day(mk, sym, day):
    lo, hi, before = window(mk, day)
    rows = []
    for page in range(4):
        r = get("/api/v1/candles", symbol=sym, interval="1m", count=200, before=before)
        c = (r or {}).get("candles") or []
        if not c: break
        oldest = None
        for x in c:
            t = ts_utc(x["timestamp"]); oldest = t if oldest is None else min(oldest, t)
            if lo <= t <= hi:
                rows.append((sym, t, float(x["openPrice"]), float(x["highPrice"]), float(x["lowPrice"]), float(x["closePrice"]), int(float(x["volume"]))))
        if oldest is None or oldest <= lo: break
        before = dt.datetime.fromtimestamp(oldest - 60, KST).isoformat()
    return rows


def frame(rows):
    import pandas as pd
    D = pd.DataFrame(rows, columns=["t", "ts", "o", "h", "l", "c", "v"]).drop_duplicates(["t", "ts"]).sort_values(["t", "ts"])
    for k in ("o", "h", "l", "c"): D[k] = D[k].astype("float32")
    return D


def universe(mk):
    """국장 보통주·미장 보통주+ADR(활성) + 잣대 ETF. 일주일에 한 번 새로 받는다."""
    f = ROOT / ("universe_%s.json" % mk)
    if f.exists() and time.time() - f.stat().st_mtime < 7 * 86400:
        return json.loads(f.read_text(encoding="utf-8"))
    U = []
    for m in (("KOSPI", "KOSDAQ") if mk == "KR" else ("NYSE", "NASDAQ", "AMEX")):
        for x in get("/api/v1/stocks/all", market=m) or []:
            st = x.get("securityType")
            if x.get("status") != "ACTIVE": continue
            if mk == "KR" and not (st == "STOCK" and x.get("isCommonShare")): continue
            if mk == "US" and st not in ("STOCK", "DEPOSITARY_RECEIPT"): continue
            U.append(x["symbol"])
        time.sleep(1.5)
    U = sorted(set(U) | set(EXTRA[mk]))
    f.write_text(json.dumps(U), encoding="utf-8")
    return U


def last_session(mk):
    """방금 끝난 정규장 날짜(YYYYMMDD) — 끝나지 않았으면 None."""
    cal = get("/api/v1/market-calendar/" + mk)
    now = dt.datetime.now(KST)
    for key in ("today", "previousBusinessDay"):
        x = cal.get(key) or {}
        rm = (x.get("integrated") or {}).get("regularMarket") if mk == "KR" else x.get("regularMarket")
        if rm and dt.datetime.fromisoformat(rm["endTime"]) <= now:
            return x["date"].replace("-", "")
    return None


def daily(mk):
    day = last_session(mk)
    if not day:
        log(mk, "끝난 정규장 없음 — 건너뜀"); return
    out = ROOT / mk / "day" / (day + ".parquet")
    if out.exists():
        log(mk, day, "이미 있음"); return
    out.parent.mkdir(parents=True, exist_ok=True)
    BUSY.write_text(mk)
    try:
        U = universe(mk); rows = []; n0 = 0; t0 = time.time()
        for i, s in enumerate(U):
            r = fetch_day(mk, s, day)
            rows += r; n0 += bool(r)
            if i % 500 == 499: log(mk, day, "%d/%d · 봉 있는 종목 %d" % (i + 1, len(U), n0))
        frame(rows).to_parquet(out, index=False, compression="zstd")
        log(mk, day, "끝 — %d종목 중 %d · 봉 %d · %.0f분 · %.1fMB" % (len(U), n0, len(rows), (time.time() - t0) / 60, out.stat().st_size / 1e6))
    finally:
        try: BUSY.unlink()
        except Exception: pass


def ranked(mk):
    """과거 채우기 순서 — 거래대금(20일 평균) 큰 것부터. 사이트 표(로컬)로 줄을 세운다."""
    f = BASE / "site" / "data" / ("table.json" if mk == "KR" else "table_us.json")
    try:
        R = json.loads(f.read_text(encoding="utf-8"))["rows"]
        R = [r for r in R if not r.get("pref") and r.get("amt20")]
        L = [r["t"] for r in sorted(R, key=lambda r: -r["amt20"])][:TOP[mk]]
    except Exception as ex:
        log("순위표 못 읽음", ex); L = []
    return EXTRA[mk] + [t for t in L if t not in EXTRA[mk]]


def days_of(mk, sym):
    """그 종목이 거래된 날(시작일 이후) — 일봉으로."""
    ds, before = set(), None
    for k in range(10):
        q = dict(symbol=sym, interval="1d", count=200)
        if before: q["before"] = before
        r = get("/api/v1/candles", **q); c = (r or {}).get("candles") or []
        if not c: break
        for x in c: ds.add(x["timestamp"][:10].replace("-", ""))
        if min(ds) < START[mk] or not r.get("nextBefore"): break
        before = r["nextBefore"]
    return sorted(d for d in ds if d >= START[mk])


def backfill(hours):
    import pandas as pd
    stop_at = time.time() + hours * 3600
    st_f = ROOT / "backfill_state.json"
    S = json.loads(st_f.read_text(encoding="utf-8")) if st_f.exists() else {"done": {}}
    queue = [("KR", s) for s in ranked("KR")] + [("US", s) for s in ranked("US")]
    for mk, sym in queue:
        key = f"{mk}:{sym}"
        if S["done"].get(key): continue
        if time.time() > stop_at:
            log("시간 다 됨 — 다음에 이어서"); break
        out = ROOT / mk / "bf" / (sym + ".parquet"); out.parent.mkdir(parents=True, exist_ok=True)
        have = set()
        if out.exists():
            have = set(pd.read_parquet(out, columns=["ts"]).ts.map(lambda t: dt.datetime.fromtimestamp(t, KST if mk == "KR" else NY).strftime("%Y%m%d")))
        # 매일 수집이 이미 받은 날은 건너뛴다
        dayfiles = {p.stem for p in (ROOT / mk / "day").glob("*.parquet")}
        todo = [d for d in days_of(mk, sym) if d not in have and d not in dayfiles]
        t0 = time.time(); rows = []; cut = False
        for i, d in enumerate(todo):
            while BUSY.exists():
                time.sleep(30)                                      # 매일 수집이 도는 동안은 쉰다
            rows += fetch_day(mk, sym, d)
            if time.time() > stop_at + 1800:                        # 종목 하나는 마무리하되 30분 넘게 넘기지 않는다
                cut = True; break
        if rows:
            D = frame(rows)
            if out.exists(): D = pd.concat([pd.read_parquet(out), D]).drop_duplicates(["t", "ts"]).sort_values("ts")
            D.to_parquet(out, index=False, compression="zstd")
        if not cut:
            S["done"][key] = time.strftime("%Y-%m-%d")
        st_f.write_text(json.dumps(S, ensure_ascii=False), encoding="utf-8")
        log("채움", key, "%d일 · 봉 %d · %.1f분 · 누적 완료 %d/%d" % (len(todo), len(rows), (time.time() - t0) / 60, len(S["done"]), len(queue)))


def status():
    import pandas as pd
    for mk in ("KR", "US"):
        dd = sorted((ROOT / mk / "day").glob("*.parquet"))
        bf = list((ROOT / mk / "bf").glob("*.parquet"))
        sz = sum(p.stat().st_size for p in dd + bf) / 1e9
        log(mk, "매일 %d일(%s~%s) · 과거 %d종목 · %.2fGB" % (len(dd), dd[0].stem if dd else "-", dd[-1].stem if dd else "-", len(bf), sz))
    f = ROOT / "backfill_state.json"
    if f.exists(): log("과거 채우기 완료", len(json.loads(f.read_text(encoding="utf-8"))["done"]), "/", TOP["KR"] + TOP["US"] + 5)


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    try:
        if a[:1] == ["daily"] and len(a) > 1:
            daily(a[1].upper())
        elif a[:1] == ["backfill"]:
            h = float(sys.argv[sys.argv.index("--hours") + 1]) if "--hours" in sys.argv else 6
            backfill(h)
        elif a[:1] == ["status"]:
            status()
        else:
            log("사용법: python collect_m1.py daily kr|us | backfill --hours N | status")
    except Exception as ex:
        log("실패:", repr(ex)[:500]); raise
