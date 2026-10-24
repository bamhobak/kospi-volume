# -*- coding: utf-8 -*-
"""NXT 장후 빠진 종목 → 다음 날 KRX 시가 — **그림자 기록 + 1주 실주문 시험** (2026-10-25 사용자 "둘다해줘", 후보 H0366).

조건(research/nxt_wide.py '체결 가능한 안정 조건'):
  유니버스 = 시가총액 상위 50%(krx_daily.db short_balance 의 가장 최근 mktcap) 중 NXT 장후 시세가 오늘 찍힌 종목
  19:50  AH = 지금가 / 오늘 KRX 종가 - 1 · 시장 = 그 평균 · rel = AH - 시장
         시장 ≤ -1% 면 쉼 · rel ≤ -2%p · 19:41~19:50 거래대금 3천만↑ · 깊은 순 10종목
  매수 가정 4가지 → 다음 날 KRX 시가(1분봉 첫 봉 시가)에 판다 · 비용 0.23
    ask = 19:50 매도 1호가(바로 사는 지정가) · bid = 19:50 매수 1호가(걸어 두기 — 그 뒤 10분 최저가가 닿았을 때만 체결로 본다)
    vwap = 19:51~20:00 거래량 가중 평균 · high = 같은 구간 최고가
  **매수는 지정가**(장후는 얇아 시장가는 호가를 쓸고 올라간다).
실주문 시험(FIRST_TEST — 처음 한 번만): 19:52 고른 종목 중 가장 싼 것 1주를 매도 1호가 지정가로 사 본다 → 19:59 까지 안 되면 취소
  → 다음 날 08:45 시가(OPG) 시장가 매도. 결과는 텔레그램. data/autotrade/STOP 이 있으면 안 한다.

  python nxt_shadow.py close     15:36 — KRX 종가 기록
  python nxt_shadow.py pick      19:48 시작 → 19:50 고르기(+ 첫날 실주문)
  python nxt_shadow.py fill      20:02 — 19:51~20:00 체결 자료
  python nxt_shadow.py sellopen  08:45 — 시험으로 산 1주 시가 매도
  python nxt_shadow.py review    09:12 — 어제 고른 종목 성적 → data/nxt/log.csv
"""
import csv, datetime as dt, json, sqlite3, sys, time
from pathlib import Path

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))
OUT = BASE / "data" / "nxt"; OUT.mkdir(parents=True, exist_ok=True)
LOG = OUT / "run.log"
if sys.stdout is not None:
    try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass
import collect_m1 as M
import autotrade as AT

KST = M.KST
COST = 0.23
REL, CALM, LIQ, CAP = -2.0, -1.0, 3e7, None       # 10-25 사용자: 하루 10종목 제한 풀기(CAP None) — research/nxt_depth.py
# 10-25 사용자 "최대 몇만원까지 살 수 있는지 · 종목당 금액 올리면 · 대형주 위주로" — 대형 따로 기록 + 호가 10단계로 금액별 평균 단가
BIG_N, BIG_REL, BIG_LIQ = 200, -1.5, 1e8          # 시총 상위 200 · 시장 대비 1.5%p↓ · 19:41~19:50 1억↑
SIZES = (100, 300, 500, 1000)                      # 만원 — 매도 호가를 타고 올라가며 샀을 때 평균 단가
# 10-25 사용자 "대형은 많이, 거래 적은 건 적게": 금액 = 19:41~19:50 거래대금 × DYN_K, 상한 DYN_CAPS(만원)
#   research/nxt_sizing.py — 5%·상한 1천만이 2025 에도 시장충격 뒤 플러스(+1,035만/년) · 상한 3천만은 2026 두 배지만 2025 최고가면 -958만
DYN_K, DYN_CAPS, DYN_MIN = 0.05, (1000, 3000), 30
# 10-25 사용자 "갭 하락 조용주처럼 시장 대비 더 빠질수록 더": 계단 배율(-2~-3%p 1배 · -3~-5 2배 · -5↓ 3배)을 금액·상한에 곱하고
#   천장 = 19:41~19:50 거래대금 10%. research/nxt_depth.py: 깊이별 건당(충격 뒤) 2025 -0.10/+0.47/+0.79/+1.14/+2.53 → 계단이 연속보다 약간 나음
DYN_CEIL = 0.10


def mult(rel):
    return 3.0 if rel <= -5 else 2.0 if rel <= -3 else 1.0
TEST_FLAG = OUT / "first_test_done"


def log(*a):
    s = dt.datetime.now(KST).strftime("%m-%d %H:%M:%S ") + " ".join(str(x) for x in a)
    with open(LOG, "a", encoding="utf-8") as f: f.write(s + "\n")
    if sys.stdout is not None:
        try: print(s, flush=True)
        except Exception: pass


def telegram(text):
    try:
        import day_alert
        day_alert.telegram(text)
    except Exception as ex:
        log("텔레그램 실패", repr(ex)[:120])


def today():
    return dt.datetime.now(KST).strftime("%Y%m%d")


def jsave(p, d): p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
def jload(p, d=None):
    try: return json.loads(p.read_text(encoding="utf-8"))
    except Exception: return d


def trading_today():
    try:
        s = AT.session("KR")
        return bool(s) and s["date"] == today()
    except Exception as ex:
        log("장 달력 실패", repr(ex)[:120]); return False


def universe():
    c = sqlite3.connect("file:" + str(BASE / "data" / "krx_daily.db") + "?mode=ro", uri=True)
    d = c.execute("select max(date) from short_balance").fetchone()[0]
    rows = c.execute("select ticker, mktcap from short_balance where date=? and mktcap>0", (d,)).fetchall()
    rows.sort(key=lambda r: -r[1])
    return [r[0] for r in rows[:len(rows) // 2]], d, [r[0] for r in rows[:BIG_N]]


def depth(s):
    """호가 10단계 [(가격, 잔량)] — 매도·매수"""
    r = M.get("/api/v1/orderbook", symbol=s) or {}
    lv = lambda k: [(float(x.get("price") or 0), float(x.get("quantity") or x.get("volume") or 0)) for x in (r.get(k) or [])[:10] if x.get("price")]
    return lv("asks"), lv("bids")


def walk(asks, won):
    """won 원어치를 매도 호가를 타고 올라가며 살 때 평균 단가(호가가 모자라면 None)"""
    left, cost, q = won, 0.0, 0.0
    for p, n in asks:
        take = min(n, left / p)
        cost += take * p; q += take; left -= take * p
        if left <= p * 0.5: break
    return cost / q if q and left <= asks[-1][0] else None


def cap_within(asks, pct=0.5):
    """매도 1호가 +pct% 안에서 살 수 있는 금액(원)"""
    if not asks: return 0
    lim = asks[0][0] * (1 + pct / 100)
    return round(sum(p * n for p, n in asks if p <= lim))


def prices(syms):
    out = {}
    for i in range(0, len(syms), 200):
        for x in M.get("/api/v1/prices", symbols=",".join(syms[i:i + 200])) or []:
            out[x["symbol"]] = (float(x["lastPrice"]), x.get("timestamp") or "")
        time.sleep(0.1)
    return out


def book(s):
    r = M.get("/api/v1/orderbook", symbol=s) or {}
    a = (r.get("asks") or [{}])[0].get("price"); b = (r.get("bids") or [{}])[0].get("price")
    return (float(a) if a else None), (float(b) if b else None)


def bars(s, day, upto):
    b = "%s-%s-%sT%s:%s:00.000+09:00" % (day[:4], day[4:6], day[6:], upto[:2], upto[2:])
    c = (M.get("/api/v1/candles", symbol=s, interval="1m", count=200, before=b) or {}).get("candles") or []
    out = []
    for x in c:
        if x["timestamp"][:10].replace("-", "") != day: continue
        hm = int(x["timestamp"][11:13]) * 100 + int(x["timestamp"][14:16])
        out.append((hm, float(x["openPrice"]), float(x["highPrice"]), float(x["lowPrice"]), float(x["closePrice"]), float(x["volume"])))
    return sorted(out)


def do_close():
    if not trading_today(): log("close: 장 없는 날"); return
    U, asof, BIG = universe()
    px = prices(U)
    cl = {s: p for s, (p, ts) in px.items() if ts[:10].replace("-", "") == today()}
    jsave(OUT / ("close_%s.json" % today()), {"at": dt.datetime.now(KST).isoformat(), "mcap_asof": asof, "close": cl, "big": BIG})
    log("close: 시총 상위 절반 %d(기준 %s) · 오늘 종가 %d" % (len(U), asof, len(cl)))


def do_pick():
    if not trading_today(): log("pick: 장 없는 날"); return
    d = today()
    CJ = jload(OUT / ("close_%s.json" % d)) or {}
    C = CJ.get("close") or {}
    BIG = set(CJ.get("big") or [])
    if not C:
        telegram("⚠ NXT 그림자: 오늘 KRX 종가 기록(15:36)이 없어 못 고름"); log("pick: 종가 없음"); return
    at = dt.datetime.now(KST).replace(hour=19, minute=50, second=5, microsecond=0)
    w = (at - dt.datetime.now(KST)).total_seconds()
    if w > 0: log("19:50 까지 기다림 %.0f초" % w); time.sleep(w)
    px = prices(sorted(C))
    ah = {}
    for s, (p, ts) in px.items():
        if s in C and ts[:10].replace("-", "") == d and ts[11:16] >= "15:41":       # 오늘 장후에 체결된 종목만(= NXT 거래)
            ah[s] = (p / C[s] - 1) * 100
    if len(ah) < 30:
        log("pick: 장후 시세 종목 %d — 너무 적음" % len(ah)); telegram("⚠ NXT 그림자: 장후 시세 종목 %d개뿐" % len(ah)); return
    mkt = sum(ah.values()) / len(ah)
    rel = {s: v - mkt for s, v in ah.items()}
    cand = sorted([s for s in rel if rel[s] <= REL], key=lambda s: rel[s])
    snap = {"date": d, "at": dt.datetime.now(KST).isoformat(), "n_nxt": len(ah), "mkt": round(mkt, 3), "calm": mkt > CALM,
            "n_cand": len(cand), "picks": [], "big": []}
    seen = {}

    def take(s, liq):
        if s not in seen:
            try: B = bars(s, d, "1951")
            except Exception: seen[s] = None; return None
            val = sum(c_ * v for hm, o, h, l, c_, v in B if 1941 <= hm <= 1950)
            try: A_, B_ = depth(s)
            except Exception: A_, B_ = [], []
            x = {"t": s, "krx": C[s], "p50": px[s][0], "ah": round(ah[s], 3), "rel": round(rel[s], 3), "v10": round(val),
                 "ask": A_[0][0] if A_ else None, "bid": B_[0][0] if B_ else None, "asks": A_, "bids": B_[:3],
                 "cap05": cap_within(A_, 0.5), "cap10": cap_within(A_, 1.0)}
            for sz in SIZES: x["p%d" % sz] = walk(A_, sz * 1e4) if A_ else None
            x["mult"] = mult(rel[s])
            for cp in DYN_CAPS:                      # 거래대금 비례 금액(원) × 깊이 배율, 천장 10% · 그만큼 호가 타고 샀을 때 평균 단가
                amt = min(cp * 1e4 * x["mult"], DYN_K * val * x["mult"], DYN_CEIL * val)
                x["amt%d" % cp] = round(amt) if amt >= DYN_MIN * 1e4 else 0
                x["pd%d" % cp] = walk(A_, amt) if (A_ and amt >= DYN_MIN * 1e4) else None
            seen[s] = x; time.sleep(0.12)
        x = seen[s]
        return x if x and x["v10"] >= liq else None

    if mkt <= CALM:
        log("pick: 시장 장후 %.2f%% ≤ %.1f — 쉼" % (mkt, CALM))
    else:
        for s in cand:
            if CAP and len(snap["picks"]) >= CAP: break
            x = take(s, LIQ)
            if x: snap["picks"].append(x)
        bc = sorted([s for s in rel if s in BIG and rel[s] <= BIG_REL], key=lambda s: rel[s])
        for s in bc:
            if CAP and len(snap["big"]) >= CAP: break
            x = take(s, BIG_LIQ)
            if x: snap["big"].append(x)
        log("pick: 시장 %.2f%% · 후보 %d · 고름 %d · 대형 %d" % (mkt, len(cand), len(snap["picks"]), len(snap["big"])))
    jsave(OUT / ("pick_%s.json" % d), snap)
    publish("19:50 고름")
    if snap["picks"] and not TEST_FLAG.exists():
        try: first_test(snap)
        except Exception as ex:
            log("실주문 시험 오류", repr(ex)[:300]); telegram("⚠ NXT 장후 1주 실주문 시험 오류: %s" % repr(ex)[:200])
        publish("19:50 고름 · 실주문 시험")


def first_test(snap):
    if (AT.OUT / "STOP").exists():
        log("STOP 파일 — 실주문 시험 안 함"); return
    p = min((x for x in snap["picks"] if x.get("ask")), key=lambda x: x["ask"], default=None)
    if not p: log("시험: 매도 호가 있는 종목 없음"); return
    at = dt.datetime.now(KST).replace(hour=19, minute=52, second=0, microsecond=0)
    w = (at - dt.datetime.now(KST)).total_seconds()
    if w > 0: time.sleep(w)
    a, b = book(p["t"])
    lim = a or p["ask"]
    cid = ("nxt-%s-%s" % (snap["date"], p["t"]))[:36]
    body = {"clientOrderId": cid, "symbol": p["t"], "side": "BUY", "orderType": "LIMIT", "price": str(int(lim)), "quantity": "1"}
    res = {"date": snap["date"], "t": p["t"], "limit": lim, "body": body}
    try:
        oid = AT.place(body); res["oid"] = oid; log("시험 주문 접수", p["t"], lim, oid)
    except Exception as ex:
        res["error"] = repr(ex)[:400]; log("시험 주문 거절", res["error"])
        jsave(OUT / "test_order.json", res); TEST_FLAG.write_text(snap["date"])
        telegram("🧪 NXT 장후 1주 지정가 매수 시험 — **거절**\n%s %s원\n%s" % (p["t"], f"{lim:,.0f}", res["error"][:300]))
        return
    st = None
    for _ in range(40):
        time.sleep(10)
        try: st = AT.detail(oid, p["t"], 1)
        except Exception as ex: log("체결 확인 실패", repr(ex)[:120]); continue
        if (st or {}).get("status") in ("FILLED", "CANCELED", "REJECTED"): break
        if dt.datetime.now(KST).strftime("%H%M") >= "1959": break
    if (st or {}).get("status") != "FILLED":
        try: AT.call("POST", "/api/v1/orders/%s/cancel" % oid, acct=True, body={})
        except Exception as ex: log("취소 실패/이미 끝", repr(ex)[:120])
        try: st = AT.detail(oid, p["t"], 1)
        except Exception: pass
    ex_ = (st or {}).get("execution") or {}
    res.update(status=(st or {}).get("status"), filled=float(ex_.get("filledQuantity") or 0), avg=float(ex_.get("averageFilledPrice") or 0), raw=st)
    jsave(OUT / "test_order.json", res); TEST_FLAG.write_text(snap["date"])
    telegram("🧪 NXT 장후 1주 지정가 매수 시험 — %s\n%s 지정가 %s원 · 체결 %d주 @ %s원\n다음 날 시가(OPG)에 팝니다" % (
        res["status"], p["t"], f"{lim:,.0f}", res["filled"], f"{res['avg']:,.0f}"))


def do_fill():
    d = today()
    snap = jload(OUT / ("pick_%s.json" % d))
    if not snap or not (snap.get("picks") or snap.get("big")): log("fill: 고른 종목 없음"); return
    done = {}
    for x in (snap.get("picks") or []) + (snap.get("big") or []):
        if x["t"] in done:
            x.update({k: done[x["t"]].get(k) for k in ("vwap", "high", "low", "val10", "bid_fill")}); continue
        done[x["t"]] = x
        try: B = [r for r in bars(x["t"], d, "2001") if 1951 <= r[0] <= 2000]
        except Exception as ex: log("fill 실패", x["t"], repr(ex)[:80]); continue
        v = sum(r[5] for r in B)
        x["vwap"] = sum(r[4] * r[5] for r in B) / v if v else None
        x["high"] = max((r[2] for r in B if r[5] > 0), default=None)
        x["low"] = min((r[3] for r in B if r[5] > 0), default=None)
        x["val10"] = round(sum(r[4] * r[5] for r in B))
        x["bid_fill"] = bool(x.get("bid") and x["low"] is not None and x["low"] <= x["bid"])
        time.sleep(0.12)
    jsave(OUT / ("pick_%s.json" % d), snap)
    log("fill: %d종목" % len(done))
    publish("20:02 장후 체결 기록")


def last_pick_day():
    fs = sorted(OUT.glob("pick_*.json"))
    fs = [f for f in fs if f.stem[5:] < today()]
    return fs[-1].stem[5:] if fs else None


def do_sellopen():
    if not trading_today(): return
    r = jload(OUT / "test_order.json")
    if not r or r.get("sold") or not r.get("filled"): return
    if (AT.OUT / "STOP").exists(): log("STOP — 시험 1주 매도 안 함"); return
    q = int(r["filled"])
    body = {"clientOrderId": ("nxs-%s-%s" % (today(), r["t"]))[:36], "symbol": r["t"], "side": "SELL", "orderType": "MARKET", "quantity": str(q), "timeInForce": "OPG"}
    try:
        r["sell_oid"] = AT.place(body); r["sold"] = today(); log("시험 1주 시가 매도 주문", r["t"], r["sell_oid"])
    except Exception as ex:
        r["sell_error"] = repr(ex)[:300]; telegram("⚠ NXT 시험 1주 시가 매도 실패: %s" % r["sell_error"][:200])
    jsave(OUT / "test_order.json", r)


def do_review():
    if not trading_today(): return
    pd_ = last_pick_day()
    if not pd_: return
    snap = jload(OUT / ("pick_%s.json" % pd_))
    if not snap or snap.get("reviewed"): return
    d = today()
    rows, opn = [], {}
    for grp in ("picks", "big"):
        for x in snap.get(grp) or []:
            if x["t"] not in opn:
                try:
                    B = bars(x["t"], d, "0903")
                    opn[x["t"]] = next((r[1] for r in B if r[0] >= 901), None)
                except Exception:
                    opn[x["t"]] = None
                time.sleep(0.12)
            o = opn[x["t"]]
            if not o: continue
            def r_(p): return round((o / p - 1) * 100 - COST, 3) if p else ""
            rows.append([pd_, d, grp, x["t"], x["krx"], x["p50"], x["ah"], x["rel"], x.get("mult"), x.get("v10"), x.get("cap05"), x.get("cap10"), x.get("ask"), x.get("bid"),
                         x.get("bid_fill"), x.get("vwap"), x.get("high"), o, r_(x.get("ask")), r_(x.get("bid")) if x.get("bid_fill") else "",
                         r_(x.get("vwap")), r_(x.get("high"))] + [r_(x.get("p%d" % sz)) for sz in SIZES]
                        + sum(([x.get("amt%d" % cp), r_(x.get("pd%d" % cp))] for cp in DYN_CAPS), []))
    f = OUT / "log.csv"; new = not f.exists()
    with open(f, "a", newline="", encoding="utf-8") as w:
        cw = csv.writer(w)
        if new: cw.writerow(["pick_day", "sell_day", "grp", "t", "krx_close", "p1950", "ah", "rel", "mult", "v1941_50", "cap05", "cap10", "ask", "bid", "bid_fill",
                             "vwap", "high", "open1", "r_ask", "r_bid", "r_vwap", "r_high"] + ["r_%d만" % sz for sz in SIZES]
                            + sum((["amt_cap%d만" % cp, "r_cap%d만" % cp] for cp in DYN_CAPS), []))
        cw.writerows(rows)
    snap["reviewed"] = d; jsave(OUT / ("pick_%s.json" % pd_), snap)
    log("review %s → %s: %d종목" % (pd_, d, len(rows)))
    publish("다음 날 시가 채점")
    t = jload(OUT / "test_order.json")
    if t and t.get("sold") == d and not t.get("reported"):
        try:
            st = AT.detail(t["sell_oid"], t["t"], t["filled"]); ex_ = (st or {}).get("execution") or {}
            sp = float(ex_.get("averageFilledPrice") or 0)
            t["sell_avg"] = sp; t["reported"] = True
            telegram("🧪 NXT 시험 1주 정리 — %s 산 값 %s원 → 시가 %s원 (%+.2f%%, 비용 전)" % (t["t"], f"{t['avg']:,.0f}", f"{sp:,.0f}", (sp / t["avg"] - 1) * 100 if t.get("avg") else 0))
        except Exception as ex:
            log("시험 매도 확인 실패", repr(ex)[:120])
        jsave(OUT / "test_order.json", t)


def publish(stage):
    """10-25 사용자 "그림자 테스트 중인 것들 규칙 후보 페이지에 실시간으로" — Supabase '__nxt__' 에 요약을 올린다(factory.html 이 읽는다).
    단계마다(고름·체결 기록·채점·성적표) 다시 쓴다. 실패해도 그림자 기록은 그대로 간다."""
    try:
        fs = sorted(OUT.glob("pick_*.json"))
        snap = jload(fs[-1]) if fs else None
        S = None
        if snap:
            syms = sorted({x["t"] for g in ("picks", "big") for x in (snap.get(g) or [])})
            nm = {}
            try: nm = {k: v[0] for k, v in AT.names(syms).items()} if syms else {}
            except Exception: pass
            lg = {}
            f = OUT / "log.csv"
            if f.exists():
                for r in csv.DictReader(open(f, encoding="utf-8")):
                    if r["pick_day"] == snap["date"]: lg[(r["grp"], r["t"])] = r
            def row(g, x):
                r = lg.get((g, x["t"])) or {}
                return {"t": x["t"], "n": nm.get(x["t"], x["t"]), "ah": x.get("ah"), "rel": x.get("rel"), "m": x.get("mult"), "v10": x.get("v10"),
                        "ask": x.get("ask"), "bid": x.get("bid"), "amt": x.get("amt1000"), "vw": x.get("vwap"), "hi": x.get("high"),
                        "o1": float(r["open1"]) if r.get("open1") else None, "r": float(r["r_ask"]) if r.get("r_ask") not in (None, "") else None,
                        "rc": float(r["r_cap1000만"]) if r.get("r_cap1000만") not in (None, "") else None}
            S = {"date": snap["date"], "mkt": snap.get("mkt"), "calm": snap.get("calm"), "n_nxt": snap.get("n_nxt"), "n_cand": snap.get("n_cand"),
                 "reviewed": snap.get("reviewed"), "picks": [row("picks", x) for x in snap.get("picks") or []], "big": [row("big", x) for x in snap.get("big") or []]}
        cum, recent, days = {}, [], []
        f = OUT / "log.csv"
        if f.exists():
            rows = list(csv.DictReader(open(f, encoding="utf-8")))
            days = sorted({r["pick_day"] for r in rows})
            fl = lambda v: float(v) if v not in ("", None, "None") else None
            for g in ("picks", "big"):
                G = [r for r in rows if r["grp"] == g]
                cum[g] = []
                for lab, col, ac in (("매도 1호가", "r_ask", None), ("매수 1호가(체결 때)", "r_bid", None), ("10분 평균가", "r_vwap", None), ("10분 최고가", "r_high", None),
                                     ("비례 상한 1천만", "r_cap1000만", "amt_cap1000만"), ("비례 상한 3천만", "r_cap3000만", "amt_cap3000만")):
                    v = [(fl(r[col]), fl(r.get(ac)) if ac else None) for r in G]
                    v = [(x, a) for x, a in v if x is not None and (a is None or a > 0)]
                    if not v: continue
                    cum[g].append({"k": lab, "n": len(v), "avg": round(sum(x for x, _ in v) / len(v), 3), "win": round(sum(1 for x, _ in v if x > 0) / len(v) * 100),
                                   "tot": round(sum(x / 100 * a for x, a in v) / 1e4) if ac else None})
            recent = [{"d": r["pick_day"], "g": r["grp"], "t": r["t"], "rel": fl(r["rel"]), "r": fl(r["r_ask"]), "rc": fl(r.get("r_cap1000만"))} for r in rows[-30:]][::-1]
        t = jload(OUT / "test_order.json") or {}
        T = {k: t.get(k) for k in ("date", "t", "limit", "status", "filled", "avg", "sold", "sell_avg", "error")} if t else None
        data = {"updated": dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M"), "stage": stage, "hid": "H0366",
                "rule": "시총 상위 절반 · 19:50 장후가 시장 평균보다 2%%p↓ · 시장 장후 %.0f%%↓ 날 쉼 · 19:41~19:50 거래대금 %.0f천만↑ · 깊이 배율 1·2·3배 · 금액 = 거래대금 5%%(상한 1천만×배율, 천장 10%%) · 다음 날 KRX 시가 매도" % (CALM, LIQ / 1e7),
                "big_rule": "시총 상위 %d · 시장 대비 %.1f%%p↓ · %.0f억↑" % (BIG_N, -BIG_REL, BIG_LIQ / 1e8),
                "snap": S, "cum": cum, "recent": recent, "days": len(days), "test": T}
        AT.rpc("kospi_state_set", {"p_pin": "__nxt__", "p_data": data})
        log("페이지 갱신(%s)" % stage)
    except Exception as ex:
        log("페이지 갱신 실패", repr(ex)[:200])


def do_report(send=True):
    """10-25 사용자 "그림자 테스트 해보고 어떤 게 가장 좋을지 알려줘" — 쌓인 log.csv 를 매수 방식·금액·무리·깊이별로.
    매주 월 09:20 텔레그램(지난주까지 누적) · 손으로: python nxt_shadow.py report"""
    f = OUT / "log.csv"
    if not f.exists(): log("report: 기록 없음"); return
    rows = list(csv.DictReader(open(f, encoding="utf-8")))
    if not rows: return
    fl = lambda v: float(v) if v not in ("", None, "None") else None
    days = sorted({r["pick_day"] for r in rows})
    lines = ["📊 NXT 장후 그림자 누적 — %s~%s · %d일" % (days[0][4:], days[-1][4:], len(days))]
    md = ["# NXT 장후 그림자 성적표 · %s" % today(), "", "기간 %s~%s · %d거래일 · 칸 = 건수 · 건당(비용 뒤) · 승률 · 합계(금액 열은 원 → 만원)" % (days[0], days[-1], len(days)), ""]
    def summ(rs, col, amtcol=None):
        v = [(fl(r[col]), fl(r[amtcol]) if amtcol else None) for r in rs]
        v = [(x, a) for x, a in v if x is not None and (a is None or a > 0)]
        if not v: return None
        n = len(v); m = sum(x for x, _ in v) / n; w = sum(1 for x, _ in v if x > 0) / n * 100
        tot = sum(x / 100 * a for x, a in v if a) / 1e4 if amtcol else None
        return n, m, w, tot
    for grp, gl in (("picks", "상위 절반"), ("big", "대형 200")):
        G = [r for r in rows if r["grp"] == grp]
        if not G: continue
        md += ["## %s (%d건)" % (gl, len(G)), "", "| 방식 | 건수 | 건당 | 승률 | 합계 |", "|---|---|---|---|---|"]
        best = []
        for lab, col, ac in (("매도 1호가", "r_ask", None), ("매수 1호가(체결 때만)", "r_bid", None), ("10분 평균가", "r_vwap", None), ("10분 최고가", "r_high", None),
                             ("100만 호가 타기", "r_100만", None), ("300만", "r_300만", None), ("500만", "r_500만", None), ("1000만", "r_1000만", None),
                             ("비례·상한 1천만×배율", "r_cap1000만", "amt_cap1000만"), ("비례·상한 3천만×배율", "r_cap3000만", "amt_cap3000만")):
            s = summ(G, col, ac)
            if not s: continue
            md.append("| %s | %d | %+.2f%% | %.0f%% | %s |" % (lab, s[0], s[1], s[2], ("%+.0f만" % s[3]) if s[3] is not None else "—"))
            best.append((s[1], lab, s))
        for lo, hi, bl in ((-3, -2, "-2~-3%p"), (-5, -3, "-3~-5%p"), (-100, -5, "-5%p↓")):
            B = [r for r in G if fl(r["rel"]) is not None and lo < fl(r["rel"]) <= hi]
            s = summ(B, "r_ask")
            if s: md.append("| 깊이 %s · 매도 1호가 | %d | %+.2f%% | %.0f%% | — |" % (bl, s[0], s[1], s[2]))
        md.append("")
        a = summ(G, "r_ask"); c = summ(G, "r_cap1000만", "amt_cap1000만")
        lines.append("%s %d건 · 매도1호가 %s · 비례(1천만) %s" % (gl, len(G), ("%+.2f%% 승률 %.0f%%" % (a[1], a[2])) if a else "—",
                                                       ("%+.0f만" % c[3]) if c else "—"))
    (OUT / "report.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    log("report: %d건 · %d일" % (len(rows), len(days)))
    if send: telegram("\n".join(lines) + "\n자세히: 서버 data/nxt/report.md")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        {"close": do_close, "pick": do_pick, "fill": do_fill, "sellopen": do_sellopen, "review": do_review, "report": do_report,
         "publish": lambda: publish("손으로 갱신")}[mode]()
    except Exception as ex:
        log("오류", mode, repr(ex)[:300]); telegram("⚠ NXT 그림자 %s 오류: %s" % (mode, repr(ex)[:200]))
