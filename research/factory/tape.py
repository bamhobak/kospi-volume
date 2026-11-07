# -*- coding: utf-8 -*-
"""실매매 대상 종목 촘촘 녹화기 (2026-11-07 사용자 "응 시작" — 자료 보강 ①).

auction.py 는 넓게(유동성 상위 40%·하루 8번) 찍는다. 여기는 **그날 실제로 사고팔 종목만 15초마다** 찍는다
— 예상체결(단일가 호가) 흐름·체결 충격·조용히 팔기 크기를 나중에 재려고. 소형주(유동성 하위 60%)도 빠짐없이.

  python research/factory/tape.py am   (run.py morning 이 띄움, 08:30:00~09:00:20 15초 · 09:01:30~09:05 1분)
  python research/factory/tape.py pm   (run.py close 가 띄움, 띄운 때~15:30:40 15초)
대상
  am: 스윙 신호(사이트 __filters__ 국장 전 규칙) + 스윙 보유(autotrade 원장) + 08:53~ 데이 주문 종목(data/day/ledger.json 오늘 BUY)
      + 데이 후보(snap_오늘.json cand) — 한 바퀴 최대 MAXN 종목
  pm: 스윙 보유 + 스윙 신호(어제 신호 = [외인 매집] 종가 매수 대상) + 데이 오늘 산 종목
저장 data/factory/tape/KR_YYYYMMDD_{am,pm}.parquet — 열 tag(HHMMSS) · ticker · side(A 매도호가/B 매수호가/P 체결가) · lvl · price · vol · bts(호가·체결 시각) · grp(왜 찍나)
토스 한도(초당 20, 프로세스 합): 여기 RATE 4 + auction 7 + day_alert ~14 가 겹치면 넘친다 → day_alert 가 바쁠 때(.busy=day)는 쉰다.
"""
import sys, time, json, datetime as dt
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C

TD = C.DATA / "tape"; TD.mkdir(exist_ok=True)
RATE = 4.0
MAXN = 60
STEP = 15
COLS = ["tag", "ticker", "side", "lvl", "price", "vol", "bts", "grp"]


def _day_busy():
    p = C.BASE / "data" / "m1" / ".busy"
    try: return p.exists() and p.read_text().strip() == "day"
    except Exception: return False


def swing_targets():
    """(신호 종목, 보유 종목) — 국장(6자리 숫자)만. 실패하면 빈 것."""
    sig, held = [], []
    try:
        import autotrade as AT
        F = AT.filters_state() or {}
        for rid, L in (F.get("filters") or {}).items():
            if rid[:1] in ("P", "D"):
                sig += [t for t in L if str(t).isdigit() and len(str(t)) == 6]
        held = [p.get("code") for p in AT.ledger_positions("KR") if p.get("code")]
    except Exception as ex:
        C.log("녹화 대상(스윙) 못 읽음:", repr(ex)[:200])
    return sorted(set(sig)), sorted(set(held))


def day_targets(day, pm=False):
    """(오늘 데이 주문 종목, 데이 후보) — 후보는 snap 의 순서(깊은 순) 그대로."""
    orders, cand = [], []
    try:
        L = json.loads((C.BASE / "data" / "day" / "ledger.json").read_text(encoding="utf-8"))
        for o in L.get("orders") or []:
            if o.get("side") == "BUY" and o.get("date") == day and o.get("t"):
                if pm and not (o.get("fq") or 0) > 0: continue
                orders.append(o["t"])
    except Exception: pass
    if not pm:
        try:
            S = json.loads((C.BASE / "data" / "day" / ("snap_%s.json" % day)).read_text(encoding="utf-8"))
            cand = [c["t"] for c in S.get("cand") or [] if c.get("t")]
        except Exception: pass
    return list(dict.fromkeys(orders)), cand


def pick(groups):
    """[(grp, [종목])] 앞 그룹부터 MAXN 까지. {종목: grp}"""
    out = {}
    for g, L in groups:
        for t in L:
            if len(out) >= MAXN: return out
            out.setdefault(t, g)
    return out


def sweep(M, T, tag):
    rows = []
    syms = sorted(T)
    for i in range(0, len(syms), 200):
        try:
            for x in M.get("/api/v1/prices", symbols=",".join(syms[i:i + 200])) or []:
                rows.append((tag, x["symbol"], "P", -1, float(x["lastPrice"]), float("nan"), x.get("timestamp") or "", T.get(x["symbol"], "")))
        except Exception as ex:
            C.log("녹화 체결가 실패:", repr(ex)[:120])
    from concurrent.futures import ThreadPoolExecutor

    def one(s):
        try: r = M.get("/api/v1/orderbook", symbol=s) or {}
        except Exception: return []
        bts, out = r.get("timestamp") or "", []
        for side, key in (("A", "asks"), ("B", "bids")):
            for k, x in enumerate(r.get(key) or []):
                try: out.append((tag, s, side, k, float(x["price"]), float(x["volume"]), bts, T[s]))
                except Exception: pass
        return out
    with ThreadPoolExecutor(2) as ex:
        for r in ex.map(one, syms): rows += r
    return rows


def flush(path, rows):
    if not rows: return
    import pandas as pd
    D = pd.DataFrame(rows, columns=COLS)
    if path.exists(): D = pd.concat([pd.read_parquet(path), D], ignore_index=True)
    D.to_parquet(path, index=False)
    rows.clear()


def run(day, part, windows, targets):
    """windows = [(시작, 끝, 간격초)] — 간격마다 targets() 를 다시 읽고 한 바퀴."""
    M = C.toss(RATE)
    path = TD / ("KR_%s_%s.parquet" % (day, part))
    buf, last_flush, n_sw, seen = [], time.time(), 0, {}
    with C.Busy("tape"):
        for a, b, step in windows:
            if C.now() >= b: continue
            C.sleep_until(a)
            nxt = max(C.now(), a)
            while C.now() < b:
                if _day_busy():
                    time.sleep(2); continue
                T = targets()
                for t, g in T.items(): seen.setdefault(t, g)
                if T:
                    t0 = time.time()
                    buf += sweep(M, T, C.now().strftime("%H%M%S")); n_sw += 1
                    if time.time() - t0 > step + 3:
                        C.log("녹화 한 바퀴 %d종목 %.0f초 — 간격 %d초보다 김" % (len(T), time.time() - t0, step))
                if time.time() - last_flush > 60:
                    flush(path, buf); last_flush = time.time()
                nxt = nxt + dt.timedelta(seconds=step)
                if nxt <= C.now(): nxt = C.now()
                else: C.sleep_until(min(nxt, b))
        flush(path, buf)
    g = {}
    for t, k in seen.items(): g[k] = g.get(k, 0) + 1
    C.log("촘촘 녹화 %s 끝 — %d바퀴 · 종목 %s" % (part, n_sw, " · ".join("%s %d" % kv for kv in g.items())))


def am(day):
    sig, held = swing_targets()
    cache = {"t": 0, "T": {}}

    def targets():
        if time.time() - cache["t"] > 30:                # 30초마다 데이 쪽 다시 읽음(08:53~ 주문·후보 생김)
            od, cd = day_targets(day)
            cache["T"] = pick([("swing_held", held), ("swing_sig", sig), ("day_order", od), ("day_cand", cd)])
            cache["t"] = time.time()
        return cache["T"]
    run(day, "am", [(C.at(8, 30, 0), C.at(9, 0, 20), STEP), (C.at(9, 1, 30), C.at(9, 5, 30), 60)], targets)


def pm(day):
    sig, held = swing_targets()
    od, _ = day_targets(day, pm=True)
    T = pick([("swing_held", held), ("swing_sig", sig), ("day_held", od)])
    run(day, "pm", [(C.now(), C.at(15, 30, 40), STEP)], lambda: T)


if __name__ == "__main__":
    part = sys.argv[1] if len(sys.argv) > 1 else ""
    day = sys.argv[2] if len(sys.argv) > 2 else None
    if not day:
        day, _ = C.kr_session()
    if not day:
        C.log("휴장 — 촘촘 녹화 안 함"); sys.exit(0)
    try:
        {"am": am, "pm": pm}[part](day)
    except Exception:
        import traceback; C.log("촘촘 녹화 오류:", traceback.format_exc()[-600:])
