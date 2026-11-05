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
REL, CALM, LIQ, CAP = -2.0, -1.0, 1e7, None       # 10-25 사용자: 하루 10종목 제한 풀기(CAP None) — research/nxt_depth.py
# 10-25 research/nxt_tune.py: 최소 거래대금 1천만이 3천만보다 나음 → 기록은 1천만↑ 전부(계좌별 추천 설정 3천·5천·1억을 나중에 log.csv 로 다시 계산)
# 10-25 사용자 "1억 5천만도" → research/nxt_tune2.py(다음 행≠다음 거래일 버그 고침, 2025 로 고름): 1억 k 5→7%·상한 3천→5천만, 1.5억 추가
TUNED = {"3천만": (-2.0, "123", 0.02, 3000), "5천만": (-2.0, "123", 0.03, 2000), "1억": (-3.0, "1152", 0.07, 5000),
         "1.5억": (-2.0, "123", 0.03, 5000), "2억": (-3.0, "1152", 0.05, 10000)}   # 문턱·배율·k·상한(만원) · 2억 = 10-25 사용자 "2억은?"(nxt_tune2.py 20000 1등)
# 10-25 사용자 "최대 몇만원까지 살 수 있는지 · 종목당 금액 올리면 · 대형주 위주로" — 대형 따로 기록 + 호가 10단계로 금액별 평균 단가
BIG_N, BIG_REL, BIG_LIQ = 200, -1.5, 1e8          # 시총 상위 200 · 시장 대비 1.5%p↓ · 19:41~19:50 1억↑
SIZES = (100, 300, 500, 1000)                      # 만원 — 매도 호가를 타고 올라가며 샀을 때 평균 단가
# 10-25 사용자 "대형은 많이, 거래 적은 건 적게": 금액 = 19:41~19:50 거래대금 × DYN_K, 상한 DYN_CAPS(만원)
#   research/nxt_sizing.py — 5%·상한 1천만이 2025 에도 시장충격 뒤 플러스(+1,035만/년) · 상한 3천만은 2026 두 배지만 2025 최고가면 -958만
DYN_K, DYN_CAPS, DYN_MIN = 0.05, (1000, 3000), 30
# 10-25 사용자 "갭 하락 조용주처럼 시장 대비 더 빠질수록 더": 계단 배율(-2~-3%p 1배 · -3~-5 2배 · -5↓ 3배)을 금액·상한에 곱하고
#   천장 = 19:41~19:50 거래대금 10%. research/nxt_depth.py: 깊이별 건당(충격 뒤) 2025 -0.10/+0.47/+0.79/+1.14/+2.53 → 계단이 연속보다 약간 나음
DYN_CEIL = 0.10


def mult(rel, kind="123"):
    if kind == "1152": return 2.0 if rel <= -5 else 1.5 if rel <= -3 else 1.0
    return 3.0 if rel <= -5 else 2.0 if rel <= -3 else 1.0
TEST_FLAG = OUT / "first_test_done"
# 11-05 규칙 T6 실주문 조건 바꿈(사용자 "장후 등락 ≤ -2.5% + 낮 ±1% 빼기 + 두 조건 다 뺌 + 종목당 금액 = 19:41~50 거래대금 10%까지",
#   research/nxt_grid_1105.py · nxt_exec_1105.py). 그림자(picks·big)는 그대로 두고 실주문만 snap["live"] 로 따로 고른다.
#   장후 등락 = 19:50 가격 ÷ 오늘 KRX 종가 - 1(시장 평균 안 뺌) · 낮 등락 = 오늘 KRX 종가 ÷ 전 거래일 KRX 종가 - 1, ±1% 이내면 뺌
#   시장 -1% 쉼·19:41~50 1천만 조건 없음 — 대신 금액 = min(500만, 19:41~50 거래대금 10%), 30만 미만이면 안 삼 · 깊은 순으로 계좌 3천만까지
#   지정가 = min(매도 1호가, 19:50 가격 +0.5%, KRX 종가 -2.5%) 를 호가 단위로 내림 — 값이 튄 뒤 쫓아 사거나 되돌아온 걸 사지 않게
LIVE_AH, LIVE_DAY, LIVE_K, LIVE_CAP, LIVE_ACCT, LIVE_MIN, LIVE_N = -2.5, 1.0, 0.10, 5_000_000, 30_000_000, 300_000, 40


def tick_floor(p):
    t = 1 if p < 2000 else 5 if p < 5000 else 10 if p < 20000 else 50 if p < 50000 else 100 if p < 200000 else 500 if p < 500000 else 1000
    return int(p // t * t)


def prev_close(d):
    """전 거래일 KRX 종가 {종목: 값} — 그날 15:36 close 기록에서."""
    try: prv = max(x for x in M.trading_days("KR", 10) if x < d)
    except Exception: return {}
    return (jload(OUT / ("close_%s.json" % prv)) or {}).get("close") or {}


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
            "n_cand": len(cand), "picks": [], "big": [], "live": []}
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
            # 10-25 사용자 "다 매수는 되는 거지? 매도벽" — 계좌별 추천 설정(TUNED)이 이 종목에 넣을 금액을 19:50 매도 호가 10단계로 타고 올라가 산 평균 단가.
            #   10단계로 모자라면 None(= 매도벽 부족). 계좌 안 다른 종목과 나눠 쓰는 건 빼고 이 종목 몫만. ask10 = 매도 10단계 총액.
            x["ask10"] = round(sum(p_ * n_ for p_, n_ in A_)) if A_ else 0
            for acct, (th, mk, k, capm) in TUNED.items():
                if rel[s] > th: continue
                m_ = mult(rel[s], mk)
                amt = min(capm * 1e4 * m_, k * val * m_, DYN_CEIL * val)
                x["wa_" + acct] = round(amt)
                x["pw_" + acct] = walk(A_, amt) if (A_ and amt >= 30e4) else None
            seen[s] = x; time.sleep(0.12)
        x = seen[s]
        return x if x and x["v10"] >= liq else None

    # 실주문(T6) 먼저 — 그림자보다 앞에 골라야 19:51 매수 시각을 넘기지 않는다
    P0 = prev_close(d)
    for s in sorted([s for s in ah if ah[s] <= LIVE_AH], key=lambda s: ah[s]):
        if len(snap["live"]) >= LIVE_N: break
        dr = (C[s] / P0[s] - 1) * 100 if P0.get(s) else None          # 전 거래일 종가를 모르면 거르지 않는다(연구와 같게)
        if dr is not None and abs(dr) <= LIVE_DAY: continue
        x = take(s, 0)
        if not x: continue
        amt = min(LIVE_CAP, LIVE_K * x["v10"])
        if amt < LIVE_MIN: continue
        snap["live"].append(dict(x, dayr=None if dr is None else round(dr, 2), lamt=round(amt)))
    log("pick: 실주문 후보 %d(장후 %.1f%%↓ %d · 전 거래일 종가 %d)" % (len(snap["live"]), LIVE_AH, sum(1 for v in ah.values() if v <= LIVE_AH), len(P0)))
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
    if snap["live"]:                                   # 규칙 T6 — 그림자 기록은 위에서 그대로, 실주문은 11-05 조건(live)만
        try: live_buy(snap)
        except Exception as ex:
            log("T6 실매수 오류", repr(ex)[:300]); telegram("⚠ [%s] 매수 오류: %s" % (RNAME, repr(ex)[:200]))
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
    telegram("🧪 NXT 장후 1주 지정가 매수 시험 — %s\n%s 지정가 %s원 · 체결 %d주 @ %s원" % (
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
        x["bid_fill"] = bool(x.get("bid") and x["low"] is not None and x["low"] < x["bid"])      # 닿기만 해선 줄 뒤라 안 사질 수 있다 — 뚫고 내려가야 체결로 센다
        time.sleep(0.12)
    jsave(OUT / ("pick_%s.json" % d), snap)
    log("fill: %d종목" % len(done))
    publish("20:02 장후 체결 기록")


def open_picks():
    """아직 채점 안 된 고른 날들(오래된 순). 지나간 날만."""
    out = []
    for f in sorted(OUT.glob("pick_*.json")):
        d = f.stem[5:]
        if d >= today(): continue
        s = jload(f)
        if s and not s.get("reviewed"): out.append(d)
    return out


def next_td(day):
    """그 날 다음 거래일(YYYYMMDD) — 오늘까지의 거래일 달력으로. 없으면 None."""
    ds = sorted(set(M.trading_days("KR", 40)) | ({today()} if trading_today() else set()))
    return next((x for x in ds if x > day), None)


# ── 규칙 T6 [NXT 장후 빠진 종목] 실주문(2026-11-03 사용자 "이것도 규칙으로 추가해줘 · 조건별 그림자 테스트는 계속") ──
#   11-05~ snap["live"](위 LIVE_* 조건) → 19:51 지정가 min(매도 1호가, 19:50 +0.5%, KRX 종가 -2.5%) · 테스트 중엔 1주(배율 없음) → 19:59 미체결 취소
#   → 다음 거래일 08:50:30(NXT 장전 끝난 뒤) KRX 시가 단일가 시장가 매도 → 09:01:30 확인.
#   데이 원장(data/day/ledger.json)에 rid T6 — 매도를 못 냈으면 day_alert 이월 매도(08:52)가 시가에 판다.
RID, RNAME = "T6", "NXT 장후 빠진 종목"


def live_buy(snap):
    import day_alert as D
    import math, re
    if D.env().get("DAY_MODE", "notify") != "live" or (AT.OUT / "STOP").exists():
        log("T6: 실매수 꺼짐(DAY_MODE·STOP)"); return
    d = snap["date"]
    at = dt.datetime.now(KST).replace(hour=19, minute=51, second=0, microsecond=0)
    w = (at - dt.datetime.now(KST)).total_seconds()
    if w > 0: time.sleep(w)
    if dt.datetime.now(KST).strftime("%H%M") >= "1957":
        log("T6: 고르기가 늦어 매수 시간 지남"); telegram("⚠ [%s] 고르기 늦어 오늘 안 삼" % RNAME); return
    try: bp = AT.buying_power("KRW")
    except AT.TossErr: bp = None
    Lg = D._led()
    done = {o["t"] for o in Lg["orders"] if o.get("date") == d and o.get("side") == "BUY" and o.get("rid") == RID}
    try: nm = {k: v[0] for k, v in AT.names([x["t"] for x in snap["live"]]).items()}
    except Exception: nm = {}
    placed, skip = [], []
    left = LIVE_ACCT                                       # 깊은 순으로 계좌 3천만까지(실전 금액 모드)
    for x in snap["live"]:
        if x["t"] in done: continue
        name = nm.get(x["t"], x["t"])
        a, b = book(x["t"])
        if not a:
            skip.append((name, "매도 호가 없음")); continue
        lim = tick_floor(min(a, x["p50"] * 1.005, x["krx"] * (1 + LIVE_AH / 100)))
        if lim < 1:
            skip.append((name, "지정가 계산 실패")); continue
        if D.DAY_QTY: q = D.DAY_QTY
        else:
            amt = min(x.get("lamt") or 0, left)
            if amt < LIVE_MIN: skip.append((name, "계좌 한도 다 씀")); continue
            q = math.floor(amt / lim)
        if q < 1:
            skip.append((name, "1주가 너무 비쌈")); continue
        if bp is not None and q * lim > bp:
            q = math.floor(bp / lim)
            if q < 1: skip.append((name, "매수가능 부족")); continue
        cid = re.sub(r"[^A-Za-z0-9_-]", "", "da%s%s" % (d, x["t"]))[:36]
        o = dict(side="BUY", date=d, t=x["t"], name=name, qty=q, cid=cid, rid=RID, lim=lim, ask=a, pc=x.get("krx"), ah=x.get("ah"), rel=x.get("rel"), dayr=x.get("dayr"), at=AT.now().isoformat())
        try:
            ok = AT.submit(Lg, o, {"clientOrderId": cid, "symbol": x["t"], "side": "BUY", "orderType": "LIMIT", "timeInForce": "DAY",
                                   "price": str(lim), "quantity": str(q)}, D._led_save)
        except AT.TossErr as ex:
            skip.append((name, "주문 거부 " + str(ex.code or str(ex)[:80]))); continue
        if not ok:
            skip.append((name, "주문 결과 모름 — 확정 대기")); continue
        placed.append(o)
        left -= q * lim
        if bp is not None: bp -= q * lim
        time.sleep(0.3)
    end = dt.datetime.now(KST).replace(hour=19, minute=59, second=0, microsecond=0)
    while placed and dt.datetime.now(KST) < end:
        time.sleep(10)
        for o in placed:
            if o.get("status") in AT.DONE: continue
            try: AT.apply_detail(o, AT.detail(o["oid"], o["t"], o["qty"]))
            except Exception as ex: log("T6 체결 확인 실패", o["t"], repr(ex)[:80])
        if all(o.get("status") in AT.DONE for o in placed): break
    for o in placed:
        if o.get("status") in AT.DONE: continue
        try:
            AT.call("POST", "/api/v1/orders/%s/cancel" % o["oid"], acct=True, body={}); o["canceled"] = True
        except AT.TossErr as ex:
            if ex.code in ("already-filled", "already-canceled"): o["canceled"] = True
            log("T6 취소 안 됨(%s)" % ex.code, o["t"])
        time.sleep(0.3)
        try: AT.apply_detail(o, AT.detail(o["oid"], o["t"], o["qty"]))
        except Exception: o["status"] = None
    got = [o for o in placed if (o.get("fq") or 0) > 0 and (o.get("ap") or 0) > 0]
    for o in got:
        o["pos"] = D.day_pos(o); o["pf"] = o["fq"]
    D._led_save(Lg)
    if got:
        D.scalp_update(lambda P: (P.extend(dict(o["pos"]) for o in got) or True), "데이 [%s] 매수 %d건" % (RNAME, len(got)))
    try:                                                   # 11-04: 사이트 매수 대기엔 실제로 산 것만(안 산 후보는 19:59 뒤 숨김)
        f_ = OUT / ("pick_%s.json" % d); sn = jload(f_) or snap
        sn["bought"] = sorted({o["t"] for o in got}); jsave(f_, sn); publish("19:59 매수")
    except Exception as ex: log("T6 산 것 표시 실패", repr(ex)[:120])
    L = ["🌙 <b>[%s] 매수</b> %s/%s 19:51 · 시장 장후 %+.1f%%" % (RNAME, d[4:6], d[6:], snap.get("mkt") or 0)]
    L += ["✅ %s %d주 @ %s (장후 %+.1f%%)" % (o["name"], int(o["fq"]), f"{o['ap']:,.0f}", o.get("ah") or 0) for o in got]
    L += ["❌ %s 미체결" % o["name"] for o in placed if o not in got]
    if skip: L.append("못 낸 것: " + " · ".join("%s(%s)" % z for z in skip[:6]))
    telegram("\n".join(L))


def live_sell():
    """다음 거래일 08:50:30 — 직전 거래일 이전에 T6 로 사서 아직 안 판 몫을 KRX 시가 단일가(OPG) 시장가로."""
    import day_alert as D
    d = today()
    if (AT.OUT / "STOP").exists():
        log("STOP — T6 매도 안 함(이월 매도도 STOP 을 본다)"); return
    S = AT.session("KR")
    if not S or S["date"] != d: return
    at = dt.datetime.now(KST).replace(hour=8, minute=50, second=30, microsecond=0)
    w = (at - dt.datetime.now(KST)).total_seconds()
    if w > 0: time.sleep(w)
    Lg = D._led()
    sold = {}
    for o in Lg["orders"]:
        if o.get("side") == "SELL" and o.get("posId"): sold[o["posId"]] = sold.get(o["posId"], 0) + float(o.get("fq") or 0)
    sent = {o.get("posId") for o in Lg["orders"] if o.get("side") == "SELL" and o.get("date") == d and o.get("rid") == RID}
    buys = [o for o in Lg["orders"] if o.get("side") == "BUY" and o.get("rid") == RID and o.get("pos") and (o.get("fq") or 0) > 0
            and o.get("date", "") < d and o.get("date", "") >= "20261103"]
    sells = []
    for o in buys:
        pid = o["pos"]["id"]
        rem = int(float(o["fq"]) - sold.get(pid, 0))
        if rem < 1 or pid in sent: continue
        try: have = AT.sellable(o["t"])
        except Exception: have = None
        q = rem if have is None else int(min(rem, have))
        if q < 1: log("T6 매도가능 0 —", o["t"]); continue
        so = dict(side="SELL", date=d, t=o["t"], name=o["name"], qty=q, posId=pid, rid=RID, cid=("dax%s%s" % (d[2:], o["t"]))[:36], at=AT.now().isoformat())
        try:
            AT.submit(Lg, so, {"clientOrderId": so["cid"], "symbol": o["t"], "side": "SELL", "orderType": "MARKET", "quantity": str(q), "timeInForce": "OPG"}, D._led_save)
        except Exception as ex:
            so["err"] = getattr(ex, "code", None) or str(ex)[:100]
        if so.get("oid"): sells.append((so, o))
        else: telegram("🚨 [%s] %s 시가 매도 주문 실패(%s) — 이월 매도가 다시 낸다" % (RNAME, o["name"], so.get("err")))
        time.sleep(0.3)
    if not sells: return
    AT.sleep_until(S["start"] + dt.timedelta(seconds=90), "T6 시가 매도 확인")
    L2 = D._led(); R = []
    for so, o in sells:
        try: AT.apply_detail(so, AT.detail(so["oid"], so["t"], so["qty"]))
        except Exception as ex: log("T6 매도 확인 실패", so["t"], repr(ex)[:80]); continue
        me = next((z for z in L2["orders"] if z.get("cid") == so["cid"]), so)
        me.update({k: so[k] for k in ("fq", "ap", "status", "oid") if k in so})
        if (so.get("fq") or 0) > 0 and (so.get("ap") or 0) > 0:
            AT.settle_sell(L2, me, D.scalp_update, "데이 [%s] 시가 매도" % RNAME)
            if so.get("status") in AT.DONE: me["closed"] = True
            R.append((o["name"], o["ap"], so["ap"], (so["ap"] / o["ap"] - 1) * 100 - COST))
        else:
            telegram("🔒 [%s] %s 시가 미체결(%s) — 내일 이월 매도" % (RNAME, o["name"], so.get("status")))
    D._led_save(L2)
    if R:
        telegram("🌙 <b>[%s] 시가 매도</b> %d건 평균 <b>%+.2f%%</b> · 상승 %d/%d\n" % (RNAME, len(R), sum(r[3] for r in R) / len(R), sum(r[3] > 0 for r in R), len(R)) +
                 "\n".join("· %s %s → %s %+.2f%%" % (n, f"{a:,.0f}", f"{b:,.0f}", r) for n, a, b, r in R))


def do_sellopen():
    if not trading_today(): return
    try: live_sell()
    except Exception as ex:
        log("T6 매도 오류", repr(ex)[:300]); telegram("⚠ [%s] 시가 매도 오류: %s" % (RNAME, repr(ex)[:200]))
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
    """고른 날 하나하나를 **그 다음 거래일 시가**로 채점한다(2026-11-01 감사). 전엔 가장 최근 한 날만 오늘 시가로 채점해서
    월요일 작업이 빠지면 금요일 고름이 화요일 시가로 채점되고, 하루 실패하면 그 전 날은 영영 빠졌다."""
    if not trading_today(): return
    for pd_ in open_picks():
        d = next_td(pd_)
        if not d:
            log("review %s: 다음 거래일 못 찾음" % pd_); continue
        review_one(pd_, d)


def review_one(pd_, d):
    snap = jload(OUT / ("pick_%s.json" % pd_))
    if not snap or snap.get("reviewed"): return
    S = AT.session("KR") if d == today() else None
    late_open = bool(S) and S["start"].strftime("%H%M") != "0900"     # 수능일 — 09:12 엔 시가가 없다
    first, upto = (1001, "1006") if late_open or d in M.LATE_OPEN else (901, "0903")
    rows, opn = [], {}
    nopen = 0
    wall = lambda x, k: "호가없음" if not x.get("ask") else "벽부족"
    for grp in ("picks", "big"):
        for x in snap.get(grp) or []:
            if x["t"] not in opn:
                try:
                    B = bars(x["t"], d, upto)
                    opn[x["t"]] = next((r[1] for r in B if r[0] >= first and r[5] > 0), None)
                except Exception:
                    opn[x["t"]] = None
                time.sleep(0.12)
            o = opn[x["t"]]
            if not o: nopen += 1                               # 거래정지 등 — 행을 남긴다(빠지면 가장 나쁜 건만 사라진다)
            def r_(p): return round((o / p - 1) * 100 - COST, 3) if (p and o) else ""
            rows.append([pd_, d, grp, x["t"], x["krx"], x["p50"], x["ah"], x["rel"], x.get("mult"), x.get("v10"), x.get("cap05"), x.get("cap10"), x.get("ask"), x.get("bid"),
                         x.get("bid_fill"), x.get("vwap"), x.get("high"), o or "", r_(x.get("ask")), r_(x.get("bid")) if x.get("bid_fill") else "",
                         r_(x.get("vwap")), r_(x.get("high"))]
                        + [(r_(x.get("p%d" % sz)) if x.get("p%d" % sz) else (wall(x, sz) if o else "")) for sz in SIZES]
                        + sum(([x.get("amt%d" % cp), (r_(x.get("pd%d" % cp)) if x.get("pd%d" % cp) else (wall(x, cp) if (o and x.get("amt%d" % cp)) else ""))] for cp in DYN_CAPS), []) + [x.get("val10"), x.get("ask10")]
                        + sum(([x.get("wa_" + a), r_(x.get("pw_" + a)) if x.get("pw_" + a) else ((wall(x, a) if x.get("wa_" + a, 0) >= 30e4 else "") if o else "")] for a in TUNED), []))
    n_pick = len(snap.get("picks") or []) + len(snap.get("big") or [])
    if n_pick and nopen == n_pick:                         # 전부 시가가 없으면 아직 안 열린 것 — 채점 끝으로 치지 않는다(다음 실행이 다시 본다)
        log("review %s → %s: 시가가 하나도 없음 — 미룸" % (pd_, d))
        if d < today(): telegram("⚠ NXT 채점 못 함 %s → %s 시가 없음" % (pd_, d))
        return
    if nopen:
        telegram("ℹ NXT 채점 %s: 시가 없는 종목 %d건(수익 빈칸으로 남김)" % (pd_, nopen))
    f = OUT / "log.csv"; new = not f.exists()
    with open(f, "a", newline="", encoding="utf-8") as w:
        cw = csv.writer(w)
        if new: cw.writerow(["pick_day", "sell_day", "grp", "t", "krx_close", "p1950", "ah", "rel", "mult", "v1941_50", "cap05", "cap10", "ask", "bid", "bid_fill",
                             "vwap", "high", "open1", "r_ask", "r_bid", "r_vwap", "r_high"] + ["r_%d만" % sz for sz in SIZES]
                            + sum((["amt_cap%d만" % cp, "r_cap%d만" % cp] for cp in DYN_CAPS), []) + ["val1951_2000", "ask10"]
                            + sum((["amt_%s" % a, "r_wall_%s" % a] for a in TUNED), []))
        cw.writerows(rows)
    snap["reviewed"] = d; jsave(OUT / ("pick_%s.json" % pd_), snap)
    log("review %s → %s: %d종목" % (pd_, d, len(rows)))
    publish("다음 날 시가 채점")
    if d != today(): return
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


def _fl(v):
    try: return float(v)
    except (TypeError, ValueError): return None


def publish(stage):
    """10-25 사용자 "그림자 테스트 중인 것들 규칙 후보 페이지에 실시간으로" — Supabase '__nxt__' 에 요약을 올린다(factory.html 이 읽는다).
    단계마다(고름·체결 기록·채점·성적표) 다시 쓴다. 실패해도 그림자 기록은 그대로 간다."""
    try:
        fs = sorted(OUT.glob("pick_*.json"))
        snap = jload(fs[-1]) if fs else None
        S = None
        if snap:
            syms = sorted({x["t"] for g in ("picks", "big", "live") for x in (snap.get(g) or [])})
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
                        "o1": _fl(r.get("open1")), "r": _fl(r.get("r_ask")),
                        "rc": _fl(r.get("r_cap1000만")), "dr": x.get("dayr"), "la": x.get("lamt"), "krx": x.get("krx"), "p50": x.get("p50")}
            S = {"date": snap["date"], "mkt": snap.get("mkt"), "calm": snap.get("calm"), "n_nxt": snap.get("n_nxt"), "n_cand": snap.get("n_cand"),
                 "reviewed": snap.get("reviewed"), "bought": snap.get("bought"), "picks": [row("picks", x) for x in snap.get("picks") or []], "big": [row("big", x) for x in snap.get("big") or []],
                 "live": [row("live", x) for x in snap.get("live") or []]}
        cum, recent, days = {}, [], []
        f = OUT / "log.csv"
        if f.exists():
            rows = list(csv.DictReader(open(f, encoding="utf-8")))
            days = sorted({r["pick_day"] for r in rows})
            def fl(v):
                try: return float(v)
                except (TypeError, ValueError): return None
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
    def fl(v):
        try: return float(v)
        except (TypeError, ValueError): return None        # 빈칸·벽부족·호가없음 — 평균에서 빠지되 몇 건인지는 아래 표가 센다
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
    # 계좌별 추천 설정(TUNED) — 기록으로 다시 계산: 깊은 순 채우기 · 금액 = min(상한×배율, k×19:41~50 거래대금×배율, 10%) · 10분 평균가 + 시장충격(√모형)
    P_ = [r for r in rows if r["grp"] == "picks" and fl(r.get("r_vwap")) is not None and fl(r.get("v1941_50"))]
    if P_:
        md += ["## 계좌별 추천 설정 (기록으로 다시 계산 · 평균가+시장충격)", "", "| 계좌 | 설정 | 건수 | 건당 | 합계 |", "|---|---|---|---|---|"]
        for acct, (th, mk, k, capm) in TUNED.items():
            capw = {"3천만": 3e7, "5천만": 5e7, "1억": 1e8, "1.5억": 1.5e8, "2억": 2e8}[acct]
            tot, nn, ws, asum = 0.0, 0, 0.0, 0.0
            for day in days:
                Q = sorted([r for r in P_ if r["pick_day"] == day and fl(r["rel"]) <= th], key=lambda r: fl(r["rel"]))
                used = 0.0
                for r in Q:
                    rel = fl(r["rel"]); v = fl(r["v1941_50"]); a10 = fl(r.get("val1951_2000")) or 0
                    m = (3.0 if rel <= -5 else 2.0 if rel <= -3 else 1.0) if mk == "123" else (2.0 if rel <= -5 else 1.5 if rel <= -3 else 1.0)
                    amt = min(capm * 1e4 * m, k * v * m, DYN_CEIL * v, capw - used)
                    if amt < DYN_MIN * 1e4: continue
                    im = max(0.0, -0.25 + 2.40 * (amt / a10) ** 0.5) if a10 > 0 else 0.0
                    rr = fl(r["r_vwap"]) - im
                    tot += rr / 100 * amt; ws += rr * amt; asum += amt; used += amt; nn += 1
            md.append("| %s | 문턱 %.0f%%p · 배율 %s · k %d%% · 상한 %d만 | %d | %s | %+.0f만 |" % (
                acct, th, "1·2·3" if mk == "123" else "1·1.5·2", k * 100, capm, nn, ("%+.2f%%" % (ws / asum)) if asum else "—", tot / 1e4))
        # 매도벽 실측(10-25 사용자 "다 매수는 되는 거지?") — 19:50 매도 호가 10단계를 타고 그 계좌 금액을 다 샀을 때(종목 하나씩, 계좌 나눠 쓰기 전)
        md += ["", "## 매도벽 — 19:50 매도 호가 10단계로 계좌 금액을 다 살 수 있었나", "",
               "| 계좌 | 건 | 10단계로 다 산 건 | 벽 부족 | 다 산 건 수익(호가 타고 산 값 → 시가, 비용 뒤) |", "|---|---|---|---|---|"]
        for acct in TUNED:
            R_ = [r for r in rows if r["grp"] == "picks" and r.get("amt_" + acct) not in (None, "", "None") and (fl(r.get("amt_" + acct)) or 0) >= 30e4]
            ok_ = [fl(r["r_wall_" + acct]) for r in R_ if r.get("r_wall_" + acct) not in ("", "벽부족", None)]
            md.append("| %s | %d | %d | %d | %s |" % (acct, len(R_), len(ok_), sum(1 for r in R_ if r.get("r_wall_" + acct) == "벽부족"),
                                                  ("%+.2f%% 승률 %.0f%%" % (sum(ok_) / len(ok_), sum(1 for v in ok_ if v > 0) / len(ok_) * 100)) if ok_ else "—"))
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
