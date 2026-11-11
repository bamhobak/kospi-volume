# -*- coding: utf-8 -*-
"""녹화 넓히기 (2026-11-12 사용자 "④ 녹화 넓히기" — 지금 안 쌓으면 영영 없는 자료). auction.py·tape.py 가 안 찍는 빈칸 두 개를 메운다.

  ① NXT 장전 호가창 08:12 · 08:25 — 오늘 NXT 장전 체결이 있는 종목(auction 의 _nxt.parquet 에서 읽음) 호가 10단계.
     auction.py 는 08:30 부터 KRX 단일가 호가만, 08:40·08:45 에 유니버스 밖 얇은 종목만 찍는다 → 08:00~08:30 NXT 호가가 없었다.
     (토스 /orderbook 은 NXT 가 열려 있으면 NXT 호가를 준다 — 11-11 20:00 호가 시각 확인. 08:12 값이 NXT 인지는 첫 녹화로 확인할 것)
  ② 시가 직후 체결가 09:00:01~09:01:00 5초마다 · 09:01:00~09:03:00 15초마다 — 데이 유니버스(snap_오늘.json all) 전부 /prices.
     '시가에 샀다'고 잰 연구가 실제 몇 초 뒤 시장가면 얼마였는지(시가 직후 미끄러짐) 재는 용도. /prices 에는 거래량이 없다 — 가격·체결 시각만.
  저장: data/factory/auction/KR_YYYYMMDD_nxtbook.parquet (tag·ticker·side·lvl·price·vol·bts)
        data/factory/auction/KR_YYYYMMDD_open.parquet (tag·ticker·price·ts)
  토스 한도(초당 20, 프로세스 합): 여기 RATE 4(약 780종목 3분 남짓). 08:12·08:25 는 auction(분마다 /prices 13번)·nxt_pre(08:00 준비) 말고는 비어 있다.
    09:00~09:03 은 한 바퀴 5번 호출이라 초당 1번 안팎 — day_alert 09:00 취소·09:03 동기화와 겹쳐도 넉넉하다.
  하루 호출 약 1,700번(NXT 호가 2 × 약 780 + 시가 직후 약 100) · 저장 약 0.6MB(한 해 150MB).
  python research/factory/opentick.py [YYYYMMDD]   (예약 \\BamhobakFactory\\OpenTick 08:05)
"""
import sys, json, time, datetime as dt
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C

AD = C.DATA / "auction"; AD.mkdir(exist_ok=True)
RATE = 4.0
NXT_BOOK = [(8, 12, 0), (8, 25, 0)]
OPEN_WIN = [((9, 0, 1), (9, 1, 0), 5), ((9, 1, 0), (9, 3, 0), 15)]


def _save(path, rows, cols):
    if not rows: return
    import pandas as pd
    D = pd.DataFrame(rows, columns=cols)
    if path.exists(): D = pd.concat([pd.read_parquet(path), D], ignore_index=True)
    D.to_parquet(path, index=False)


def nxt_traded(day):
    """오늘 NXT 장전 체결이 있는 종목 — auction.morning 이 분마다 쓰는 _nxt.parquet."""
    import pandas as pd
    f = AD / ("KR_%s_nxt.parquet" % day)
    for _ in range(3):
        try:
            X = pd.read_parquet(f, columns=["ticker", "today"])
            return sorted(set(X.ticker[X.today]))
        except Exception:
            time.sleep(5)
    return []


def book_pass(M, syms, tag):
    from concurrent.futures import ThreadPoolExecutor
    rows, t0 = [], time.time()

    def one(s):
        try: r = M.get("/api/v1/orderbook", symbol=s) or {}
        except Exception: return []
        bts, out = r.get("timestamp") or "", []
        for side, key in (("A", "asks"), ("B", "bids")):
            for k, x in enumerate(r.get(key) or []):
                try: out.append((tag, s, side, k, float(x["price"]), float(x["volume"]), bts))
                except Exception: pass
        return out
    with ThreadPoolExecutor(3) as ex:
        for r in ex.map(one, syms): rows += r
    C.log("NXT 장전 호가 %s %d종목 · %.0f초" % (tag, len(syms), time.time() - t0))
    return rows


def day_uni(day):
    """데이 유니버스 = 데이 아침 snap 의 all(08:52~54 생김). 없으면 auction 의 유니버스."""
    f = C.BASE / "data" / "day" / ("snap_%s.json" % day)
    try:
        U = sorted((json.loads(f.read_text(encoding="utf-8")).get("all") or {}).keys())
        if len(U) >= 300: return U
    except Exception: pass
    import auction
    U, _ = auction.uni_today()
    return U


def px_pass(M, syms, tag):
    rows = []
    for i in range(0, len(syms), 200):
        try:
            for x in M.get("/api/v1/prices", symbols=",".join(syms[i:i + 200])) or []:
                rows.append((tag, x["symbol"], float(x["lastPrice"]), x.get("timestamp") or ""))
        except Exception as ex:
            C.log("시가 직후 체결가 실패:", repr(ex)[:120])
    return rows


def run(day):
    M = C.toss(RATE)
    fb, fo = AD / ("KR_%s_nxtbook.parquet" % day), AD / ("KR_%s_open.parquet" % day)
    with C.Busy("otick"):
        for t in NXT_BOOK:
            if C.now() >= C.at(*t) + dt.timedelta(minutes=2): continue
            C.sleep_until(C.at(*t))
            S = nxt_traded(day)
            if not S:
                C.log("NXT 장전 체결 종목 없음 — %02d:%02d 호가 건너뜀" % t[:2]); continue
            S = S[: int(RATE * 200)]                      # 08:30 KRX 단일가 녹화(auction·tape) 전에 끝나게
            _save(fb, book_pass(M, S, C.now().strftime("%H%M%S")), ["tag", "ticker", "side", "lvl", "price", "vol", "bts"])
        C.sleep_until(C.at(8, 59, 30))
        U = day_uni(day)
        C.log("시가 직후 녹화 %d종목" % len(U))
        buf, n = [], 0
        for a, b, step in OPEN_WIN:
            A, B = C.at(*a), C.at(*b)
            if C.now() >= B: continue
            C.sleep_until(A)
            nxt = max(C.now(), A)
            while C.now() < B:
                buf += px_pass(M, U, C.now().strftime("%H%M%S")); n += 1
                nxt = nxt + dt.timedelta(seconds=step)
                if nxt > C.now(): C.sleep_until(min(nxt, B))
        _save(fo, buf, ["tag", "ticker", "price", "ts"])
    C.log("녹화 넓히기 끝 — 시가 직후 %d바퀴" % n)


if __name__ == "__main__":
    day = sys.argv[1] if len(sys.argv) > 1 else None
    if not day:
        day, _ = C.kr_session()
    if not day:
        C.log("휴장 — 녹화 넓히기 안 함"); sys.exit(0)
    try:
        run(day)
    except Exception:
        import traceback; C.log("녹화 넓히기 오류:", traceback.format_exc()[-600:])
        try: C.tg("⚠ 녹화 넓히기(opentick) 오류 — run.log")
        except Exception: pass
