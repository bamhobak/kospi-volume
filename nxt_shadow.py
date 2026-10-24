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
REL, CALM, LIQ, CAP = -2.0, -1.0, 3e7, 10
# 10-25 사용자 "최대 몇만원까지 살 수 있는지 · 종목당 금액 올리면 · 대형주 위주로" — 대형 따로 기록 + 호가 10단계로 금액별 평균 단가
BIG_N, BIG_REL, BIG_LIQ = 200, -1.5, 1e8          # 시총 상위 200 · 시장 대비 1.5%p↓ · 19:41~19:50 1억↑
SIZES = (100, 300, 500, 1000)                      # 만원 — 매도 호가를 타고 올라가며 샀을 때 평균 단가
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
            seen[s] = x; time.sleep(0.12)
        x = seen[s]
        return x if x and x["v10"] >= liq else None

    if mkt <= CALM:
        log("pick: 시장 장후 %.2f%% ≤ %.1f — 쉼" % (mkt, CALM))
    else:
        for s in cand[:30]:
            if len(snap["picks"]) >= CAP: break
            x = take(s, LIQ)
            if x: snap["picks"].append(x)
        bc = sorted([s for s in rel if s in BIG and rel[s] <= BIG_REL], key=lambda s: rel[s])
        for s in bc[:30]:
            if len(snap["big"]) >= CAP: break
            x = take(s, BIG_LIQ)
            if x: snap["big"].append(x)
        log("pick: 시장 %.2f%% · 후보 %d · 고름 %d · 대형 %d" % (mkt, len(cand), len(snap["picks"]), len(snap["big"])))
    jsave(OUT / ("pick_%s.json" % d), snap)
    if snap["picks"] and not TEST_FLAG.exists():
        try: first_test(snap)
        except Exception as ex:
            log("실주문 시험 오류", repr(ex)[:300]); telegram("⚠ NXT 장후 1주 실주문 시험 오류: %s" % repr(ex)[:200])


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
            rows.append([pd_, d, grp, x["t"], x["krx"], x["p50"], x["ah"], x["rel"], x.get("v10"), x.get("cap05"), x.get("cap10"), x.get("ask"), x.get("bid"),
                         x.get("bid_fill"), x.get("vwap"), x.get("high"), o, r_(x.get("ask")), r_(x.get("bid")) if x.get("bid_fill") else "",
                         r_(x.get("vwap")), r_(x.get("high"))] + [r_(x.get("p%d" % sz)) for sz in SIZES])
    f = OUT / "log.csv"; new = not f.exists()
    with open(f, "a", newline="", encoding="utf-8") as w:
        cw = csv.writer(w)
        if new: cw.writerow(["pick_day", "sell_day", "grp", "t", "krx_close", "p1950", "ah", "rel", "v1941_50", "cap05", "cap10", "ask", "bid", "bid_fill",
                             "vwap", "high", "open1", "r_ask", "r_bid", "r_vwap", "r_high"] + ["r_%d만" % sz for sz in SIZES])
        cw.writerows(rows)
    snap["reviewed"] = d; jsave(OUT / ("pick_%s.json" % pd_), snap)
    log("review %s → %s: %d종목" % (pd_, d, len(rows)))
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


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        {"close": do_close, "pick": do_pick, "fill": do_fill, "sellopen": do_sellopen, "review": do_review}[mode]()
    except Exception as ex:
        log("오류", mode, repr(ex)[:300]); telegram("⚠ NXT 그림자 %s 오류: %s" % (mode, repr(ex)[:200]))
