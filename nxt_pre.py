# -*- coding: utf-8 -*-
"""데이 규칙 [장전 되돌림](T5) — 2026-11-03 사용자 "바로 그림자 하지말고 규칙 추가해줘".

연구: research/newdata_pmrev*_1103.py · reports/newdata_1103.md (토스 장전 1분봉 2025-04~2026-10 전체 369일, 비용 0.23 뒤 날 바구니)
  08:40 NXT 장전가가 어제 통합 종가(20:00) 대비 시장(NXT 종목 중앙)보다 **3%p↓** & 장전 누적 거래대금(08:01~08:40) **10.19억↓**
  → 08:41~45 매수 → **KRX 시가 단일가에 판다**(그날 종가까지 들면 -1.0~-1.1).
  매도호가 근사 학습 2025 +1.88 · 검증 2026 +1.95(t 7.6/10.4, 검증 달 10/10) · 100만 √충격 넣으면 +1.06/+1.21 · 하루 2.8건.
  얇음 경계는 신호 시각까지 아는 누적 거래대금으로(매수 5분 거래대금으로 가르면 미래 정보 — pmrev5 에서 바꿈, 오히려 더 나음).
  얇지 않은 종목은 0 근처라 안 산다. 종목당 100만원 안팎이 한계(5분 거래대금 중앙 약 1,900만).

  python nxt_pre.py morning   08:00 — NXT 종목·어제 통합 종가 → 08:40 고르기 → 08:41 매도 1호가 지정가 → 08:46 미체결 취소
                                     → 08:50:30 KRX 시가(OPG) 시장가 매도 → 09:01:30 결과 텔레그램 · 사이트(__nxtpre__ · 데이 보유)
  python nxt_pre.py review    16:30 — 후보(-2%p↓ 전부) 08:41~45 VWAP·KRX 시가로 채점 → data/nxtpre/log.csv
원장은 데이 원장(data/day/ledger.json)에 rid='T5' 로 같이 쓴다 — 09:03·15:24 주문 확정, 15:24 종가 지킴이, 다음 날 이월 매도가 안전망이 된다.
"""
import csv, datetime as dt, json, math, re, sys, time
from pathlib import Path

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))
OUT = BASE / "data" / "nxtpre"; OUT.mkdir(parents=True, exist_ok=True)
LOG = OUT / "run.log"
if sys.stdout is not None:
    try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass
import collect_m1 as M
import autotrade as AT
import day_alert as D

KST = M.KST
RID = "T5"
RNAME = "장전 되돌림"
REL = -3.0                 # 시장(NXT 종목 장전 중앙) 대비 %p 이하
CUM_MAX = 1_019_060_000    # 08:01~08:40 장전 누적 거래대금 상한(원) — 학습 2025 신호(-3%p↓) 하위 1/3 경계(pmrev5)
RANK_MAX = 4               # 2026-11-10 사용자 승인(처음 5 → 같은 날 '4로 해줘'): 그날 NXT 전 종목 중 시장 대비 가장 많이 빠진 순위 4 안만 산다(두꺼운 종목도 순위에 넣어 센다)
#   연구(pmrev5 369일, research/reports 없음 — 기억 review-1110): 순위 1 +3.13% · 2~3 +1.66 · 4~6 +0.49 · 7~10 +0.49 · 11↑ +0.1(붐비는 날이든 아니든 순위가 가른다).
#   낱 순위: 1위 +3.13 · 2위 +2.00 · 3위 +1.24 · 4위 +0.63 · 5위 +0.48(금액으론 연 -2만) · 6위 +0.28. 지금 649건 +1.08 → 순위 4 안 292건 +2.06(승 66%).
#   계단×100만 연 +422 → +424만·필요 자금 최대 2,549→600만·최악의 날 -53→-14만. 되돌리려면 999.
CROWD_MAX = 10             # 2026-11-12 사용자 '넣어줘': 그날 규칙 신호(-3%p·얇음)가 10개↑ 면 쉰다 — 업종·시장째 빠지는 날은 안 되돌아온다.
#   research/t5_recheck_1112.py: 과거 242 신호 날 중 10개↑ 8일 날 바구니 +0.01 · 순위 4 안 돈 연 +259→+262만 · 실전 뒤 손해 날(11-06 47·11-09 10·11-10 13) 전부 그런 날. 되돌리려면 9999.
PRE_MAX = 30.0             # |어제 종가 대비| 30% 넘는 값은 버린다(연구와 같게)
FRESH = (8, 35)            # 신호가 = 08:35 이후 체결만(연구: 5분 안 체결)
SIG_AT, BUY_AT, BUY_END, SELL_AT = (8, 40, 1), (8, 41, 0), (8, 46, 0), (8, 50, 30)
WATCH_REL = -2.0           # 채점·호가 기록은 -2%p↓ 까지 넓게(규칙은 -3)
PER = 1_000_000            # 실전 기준금액(D.DAY_QTY 가 None 일 때) × 깊이 배율
# 2026-11-03 사용자 '응 바꿔줘' — 깊이 계단: 시장 대비 -3~-4%p 1배 · -4~-5 2배 · -5↓ 3배(테스트 중엔 1~3주)
#   √충격·5분 거래대금 10%까지 체결로 연 환산 학/검: 고정 100만 +150/+307만 · 계단 100만 +263/+578만(하루 최대 2,549만·최악의 날 -53만) · 고정 500만 +262/+590(-139만)
STEPS = ((-5.0, 3), (-4.0, 2))


def mult(rel):
    return next((m for c, m in STEPS if rel <= c), 1)
COST = 0.23


# 11-06 지정가 상한(사용자 "둘 다 고쳐줘") — 매도 1호가가 08:40 신호가보다 튀어 있으면 그대로 샀다(11-05 토비스 10,670 → 10,890, +2.06%).
#   지정가 = min(매도 1호가, 08:40 가격 +0.5%) 를 호가 단위로 내림. A4(nxt_shadow.LIVE_*)와 같은 장치.
LIM_UP = 0.5


def tick_floor(p):
    t = 1 if p < 2000 else 5 if p < 5000 else 10 if p < 20000 else 50 if p < 50000 else 100 if p < 200000 else 500 if p < 500000 else 1000
    return int(p // t * t)


def log(*a):
    s = time.strftime("%Y-%m-%d %H:%M:%S ") + " ".join(str(x) for x in a)
    try:
        with open(LOG, "a", encoding="utf-8") as f: f.write(s + "\n")
    except Exception: pass
    if sys.stdout is not None:
        try: print(s, flush=True)
        except Exception: pass


def at(h, m, s=0):
    return AT.now().replace(hour=h, minute=m, second=s, microsecond=0)


def jsave(p, d): p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def jload(p, d=None):
    try: return json.loads(p.read_text(encoding="utf-8"))
    except Exception: return d


def publish(snap):
    try: D.supa_set("__nxtpre__", snap)
    except Exception as ex: log("사이트 기록 실패:", repr(ex)[:150])


def nxt_names():
    """오늘 NXT 거래되는 국장 보통주 {종목: 이름}."""
    U = M.universe("KR"); out = {}
    for i in range(0, len(U), 100):
        for x in M.get("/api/v1/stocks", symbols=",".join(U[i:i + 100])) or []:
            k = x.get("koreanMarketDetail") or {}
            if k.get("nxtSupported") and not k.get("nxtTradingSuspended") and not k.get("krxTradingSuspended") and not k.get("liquidationTrading"):
                out[x["symbol"]] = x.get("name") or x["symbol"]
    return out


def yclose(syms, today, prev):
    """어제 통합 종가(토스 일봉 종가 = NXT 20:00 까지 마지막 체결) — 날짜가 직전 거래일인 것만."""
    from concurrent.futures import ThreadPoolExecutor

    def one(s):
        c = (M.get("/api/v1/candles", symbol=s, interval="1d", count=3) or {}).get("candles") or []
        b = sorted([x for x in c if x["timestamp"][:10].replace("-", "") < today], key=lambda x: x["timestamp"])
        if b and b[-1]["timestamp"][:10].replace("-", "") == prev: return s, float(b[-1]["closePrice"])
        return s, None
    with ThreadPoolExecutor(2) as ex:
        return {s: v for s, v in ex.map(one, syms) if v}


def pm_bars(s, today, upto="0841"):
    """오늘 장전 1분봉(봉 끝 시각 hm ≤ upto) [(hm, o, h, l, c, v)]."""
    b = "%s-%s-%sT%s:%s:00.000+09:00" % (today[:4], today[4:6], today[6:], upto[:2], upto[2:])
    c = (M.get("/api/v1/candles", symbol=s, interval="1m", count=60, before=b) or {}).get("candles") or []
    out = []
    for x in c:
        ts = x["timestamp"]
        if ts[:10].replace("-", "") != today: continue
        hm = ts[11:13] + ts[14:16]
        if "0801" <= hm <= upto:
            out.append((hm, float(x["openPrice"]), float(x["highPrice"]), float(x["lowPrice"]), float(x["closePrice"]), float(x["volume"])))
    return sorted(out)


def book(s):
    r = M.get("/api/v1/orderbook", symbol=s) or {}
    lv = lambda k: [(float(x["price"]), float(x["volume"])) for x in (r.get(k) or [])]
    return lv("asks"), lv("bids")


def book_rec(syms, tag, rows):
    for s in syms:
        try: a, b = book(s)
        except Exception: continue
        rows += [(tag, s, "A", i, p, v) for i, (p, v) in enumerate(a)] + [(tag, s, "B", i, p, v) for i, (p, v) in enumerate(b)]


def save_books(today, rows):
    if not rows: return
    import pandas as pd
    f = OUT / ("book_%s.parquet" % today)
    X = pd.DataFrame(rows, columns=["tag", "ticker", "side", "lvl", "price", "vol"])
    if f.exists(): X = pd.concat([pd.read_parquet(f), X], ignore_index=True)
    X.to_parquet(f, index=False)


def morning():
    S = AT.session("KR")
    today = AT.now().strftime("%Y%m%d")
    if not S or S["date"] != today:
        log("국장 휴장 — 건너뜀"); return
    if S["start"].strftime("%H%M") != "0900":
        log("늦은 개장(%s) — 장전 시장이 달라 건너뜀" % S["start"].strftime("%H:%M")); return
    prev = S["prev"]
    t0 = time.time()
    NM = nxt_names()
    YC = yclose(sorted(NM), today, prev)
    log("NXT 종목 %d · 어제(%s) 통합 종가 %d · %.0f초" % (len(NM), prev, len(YC), time.time() - t0))
    if len(YC) < 200:
        D.telegram("⚠ [%s] 어제 종가 %d종목뿐 — 오늘 쉼" % (RNAME, len(YC))); return
    AT.sleep_until(at(*SIG_AT), "신호 08:40")
    syms = sorted(YC); px = {}
    fresh = at(*FRESH)
    for i in range(0, len(syms), 200):
        for x in M.get("/api/v1/prices", symbols=",".join(syms[i:i + 200])) or []:
            ts = x.get("timestamp") or ""
            if ts[:10].replace("-", "") != today: continue
            try:
                if AT.ts(ts) < fresh: continue
            except ValueError: continue
            p = float(x["lastPrice"]); pre = (p / YC[x["symbol"]] - 1) * 100
            if abs(pre) < PRE_MAX: px[x["symbol"]] = (p, pre)
    if len(px) < 100:
        D.telegram("⚠ [%s] 08:40 장전 체결 종목 %d개뿐 — 오늘 쉼" % (RNAME, len(px))); return
    pres = sorted(v[1] for v in px.values())
    mpre = pres[len(pres) // 2]
    rk = {s: i + 1 for i, s in enumerate(sorted(px, key=lambda s: px[s][1]))}      # 그날 순위(1 = 가장 많이 빠짐) — 전 종목 기준
    watch = sorted([s for s, v in px.items() if v[1] - mpre <= WATCH_REL], key=lambda s: px[s][1] - mpre)
    C = []
    for s in watch:
        rel = px[s][1] - mpre
        x = dict(t=s, name=NM.get(s, s), yc=YC[s], p=px[s][0], pre=round(px[s][1], 2), rel=round(rel, 2), rank=rk[s])
        if rel <= REL:
            try:
                B = pm_bars(s, today, "0840")
                x["cum"] = round(sum(r[4] * r[5] for r in B)); x["nbar"] = sum(1 for r in B if r[5] > 0)
            except Exception as ex:
                log("장전 봉 못 받음", s, repr(ex)[:80])
        x["pick0"] = bool(rel <= REL and x.get("cum") is not None and x["cum"] <= CUM_MAX)      # 11-10 전 규칙(비교용으로 남긴다)
        x["pick"] = bool(x["pick0"] and rk[s] <= RANK_MAX)
        C.append(x)
    nsig = sum(1 for x in C if x["pick0"])
    crowd = nsig >= CROWD_MAX
    if crowd:                                                               # 붐비는 날 — 아무것도 안 산다(가상도 없음)
        for x in C: x["pick"] = False
    P = [x for x in C if x["pick"]]
    snap = dict(date=today, made=AT.now().strftime("%H:%M:%S"), rule=RNAME, rid=RID, n_nxt=len(YC), n_fresh=len(px), mpre=round(mpre, 2),
                rel=REL, cum_max=CUM_MAX, rank_max=RANK_MAX, crowd_max=CROWD_MAX, nsig=nsig, crowd=crowd, cand=C)
    jsave(OUT / ("snap_%s.json" % today), snap); publish(snap)
    log("08:40 시장 장전 %+.2f%% · 체결 %d종목 · -2%%p↓ %d · -3%%p↓ %d · 옛 규칙이면 %d · 고른 것(순위 %d 안) %d" % (
        mpre, len(px), len(C), sum(1 for x in C if x["rel"] <= REL), sum(1 for x in C if x["pick0"]), RANK_MAX, len(P)))
    if crowd:
        log("신호 %d개(%d↑) — 붐비는 날, 오늘 쉼" % (nsig, CROWD_MAX))
        D.telegram("🌄 [%s] 신호 %d개 — 붐비는 날, 쉼" % (RNAME, nsig))
    rows = []
    live = D.env().get("DAY_MODE", "notify") == "live"
    if not P:
        AT.sleep_until(at(*BUY_AT)); book_rec([x["t"] for x in C][:40], "0841", rows); save_books(today, rows)
        return
    if not live or (AT.OUT / "STOP").exists():
        D.telegram("🌄 <b>[%s]</b> %s — %d종목 (%s, 주문 없음)\n" % (RNAME, today[4:], len(P), "STOP" if live else "알림만") +
                   "\n".join("· %s %+.1f%%p · 장전 %s억" % (x["name"], x["rel"], "%.1f" % (x["cum"] / 1e8)) for x in P[:10]))
        return
    AT.sleep_until(at(*BUY_AT), "매수 08:41")
    try: bp = AT.buying_power("KRW")
    except AT.TossErr: bp = None
    Lg = D._led()
    done = {o["t"] for o in Lg["orders"] if o.get("date") == today and o.get("side") == "BUY" and o.get("rid") == RID}
    placed, skip = [], []
    for x in P:
        if x["t"] in done: continue
        try: a, b = book(x["t"])
        except Exception: a, b = [], []
        rows += [("0841", x["t"], "A", i, p_, v_) for i, (p_, v_) in enumerate(a)] + [("0841", x["t"], "B", i, p_, v_) for i, (p_, v_) in enumerate(b)]
        if not a:
            skip.append((x["name"], "매도 호가 없음")); continue
        x["ask"] = int(a[0][0]); x["ask_vol"] = a[0][1]
        lim = tick_floor(min(a[0][0], x["p"] * (1 + LIM_UP / 100))); x["lim"] = lim
        k = mult(x["rel"]); x["mult"] = k
        if D.DAY_QTY: q = D.DAY_QTY * k
        else:
            q = math.floor(PER * k / lim)
            if q < 1 and lim <= PER * 2: q = 1
        if q < 1:
            skip.append((x["name"], "1주가 너무 비쌈")); continue
        if bp is not None and q * lim > bp:
            q = math.floor(bp / lim)
            if q < 1: skip.append((x["name"], "매수가능 부족")); continue
        cid = re.sub(r"[^A-Za-z0-9_-]", "", "dn%s%s" % (today, x["t"]))[:36]
        o = dict(side="BUY", date=today, t=x["t"], name=x["name"], qty=q, cid=cid, rid=RID, lim=lim, ask=x["ask"], p40=x["p"], pc=x["yc"], rel=x["rel"], at=AT.now().isoformat())
        body = {"clientOrderId": cid, "symbol": x["t"], "side": "BUY", "orderType": "LIMIT", "timeInForce": "DAY", "price": str(lim), "quantity": str(q)}
        try:
            ok = AT.submit(Lg, o, body, D._led_save)
        except AT.TossErr as ex:
            skip.append((x["name"], "주문 거부 " + str(ex.code or str(ex)[:80]))); continue
        if not ok:
            skip.append((x["name"], "주문 결과 모름 — 확정 대기")); continue
        placed.append(o); x["qty"] = q
        if bp is not None: bp -= q * lim
        time.sleep(0.3)
    # 체결 기다림 — 08:46 까지(연구 매수 구간 08:41~45)
    while placed and AT.now() < at(*BUY_END):
        time.sleep(10)
        for o in placed:
            if o.get("status") in AT.DONE: continue
            try: AT.apply_detail(o, AT.detail(o["oid"], o["t"], o["qty"]))
            except Exception as ex: log("체결 확인 실패", o["t"], repr(ex)[:80])
        if all(o.get("status") in AT.DONE for o in placed): break
    for o in placed:
        if o.get("status") in AT.DONE: continue
        try:
            AT.call("POST", "/api/v1/orders/%s/cancel" % o["oid"], acct=True, body={}); o["canceled"] = True
        except AT.TossErr as ex:
            if ex.code in ("already-filled", "already-canceled"): o["canceled"] = True
            log("취소 안 됨(%s)" % ex.code, o["t"])
        time.sleep(0.3)
        try: AT.apply_detail(o, AT.detail(o["oid"], o["t"], o["qty"]))
        except Exception: o["status"] = None             # 모름 — 09:03 day_sync 가 맺는다
    got = [o for o in placed if (o.get("fq") or 0) > 0 and (o.get("ap") or 0) > 0]
    for o in got:
        o["pos"] = D.day_pos(o); o["pf"] = o["fq"]
    D._led_save(Lg)
    if got:
        D.scalp_update(lambda Pp: (Pp.extend(dict(o["pos"]) for o in got) or True), "데이 [%s] 매수 %d건" % (RNAME, len(got)))
    for x in C:
        o = next((z for z in placed if z["t"] == x["t"]), None)
        if o: x.update(fq=o.get("fq") or 0, ap=o.get("ap") or 0, st=o.get("status"))
    snap["skip"] = skip; jsave(OUT / ("snap_%s.json" % today), snap); publish(snap)
    L = ["🌄 <b>[%s] 매수</b> %s/%s 08:41 · 시장 장전 %+.1f%%" % (RNAME, today[4:6], today[6:], mpre)]
    L += ["✅ %s %d주 @ %s (%+.1f%%p)" % (o["name"], int(o["fq"]), f"{o['ap']:,.0f}", o["rel"]) for o in got]
    L += ["❌ %s 미체결" % o["name"] for o in placed if o not in got]
    if skip: L.append("못 낸 것: " + " · ".join("%s(%s)" % z for z in skip[:6]))
    D.telegram("\n".join(L))
    # 호가 기록 — 그림자 없이 바로 규칙이 됐으니 실제 매도 1호가 체결가를 같이 쌓는다(사용자 2번)
    try:
        AT.sleep_until(at(8, 45, 0)); book_rec([x["t"] for x in C][:40], "0845", rows)
    except Exception as ex: log("호가 기록 실패:", repr(ex)[:120])
    save_books(today, rows)
    if not got: return
    # KRX 시가 단일가 매도 — NXT 장전이 끝난(08:50) 뒤에 낸다
    AT.sleep_until(at(*SELL_AT), "시가 매도 주문")
    Lg = D._led(); sells = []
    for o in got:
        me = next((z for z in Lg["orders"] if z.get("cid") == o["cid"] and z.get("side") == "BUY"), o)
        q = int(o["fq"])
        try: have = AT.sellable(o["t"])
        except Exception: have = None
        if have is not None: q = int(min(q, have))
        if q < 1:
            D.telegram("⚠ [%s] %s 매도가능 0 — 손으로 확인" % (RNAME, o["name"])); continue
        so = dict(side="SELL", date=today, t=o["t"], name=o["name"], qty=q, posId=me["pos"]["id"], rid=RID,
                  cid=("dno%s%s" % (today[2:], o["t"]))[:36], at=AT.now().isoformat())
        try:
            AT.submit(Lg, so, {"clientOrderId": so["cid"], "symbol": o["t"], "side": "SELL", "orderType": "MARKET", "quantity": str(q), "timeInForce": "OPG"}, D._led_save)
        except Exception as ex:
            so["err"] = getattr(ex, "code", None) or str(ex)[:100]
        if so.get("oid"): sells.append((so, o))
        else: D.telegram("🚨 [%s] %s 시가 매도 주문 실패(%s) — 15:24 지킴이가 종가에 판다" % (RNAME, o["name"], so.get("err")))
        time.sleep(0.3)
    AT.sleep_until(S["start"] + dt.timedelta(seconds=90), "시가 매도 체결 확인")
    L2 = D._led(); R = []
    for so, o in sells:
        try: AT.apply_detail(so, AT.detail(so["oid"], so["t"], so["qty"]))
        except Exception as ex: log("매도 확인 실패", so["t"], repr(ex)[:80]); continue
        me = next((z for z in L2["orders"] if z.get("cid") == so["cid"]), so)
        me.update({k: so[k] for k in ("fq", "ap", "status", "oid") if k in so})
        if (so.get("fq") or 0) > 0 and (so.get("ap") or 0) > 0:
            AT.settle_sell(L2, me, D.scalp_update, "데이 [%s] 시가 매도" % RNAME)
            r = (so["ap"] / o["ap"] - 1) * 100 - COST; R.append(r)
            for x in C:
                if x["t"] == o["t"]: x.update(sell=so["ap"], ret=round(r, 3))
        else:
            D.telegram("🔒 [%s] %s 시가 미체결(%s) — 지킴이·이월이 판다" % (RNAME, o["name"], so.get("status")))
    D._led_save(L2)
    jsave(OUT / ("snap_%s.json" % today), snap); publish(snap)
    if R:
        D.telegram("🌄 <b>[%s] 시가 매도</b> %d건 평균 <b>%+.2f%%</b> · 상승 %d/%d\n" % (RNAME, len(R), sum(R) / len(R), sum(r > 0 for r in R), len(R)) +
                   "\n".join("· %s %s → %s %+.2f%%" % (x["name"], f"{x['ap']:,.0f}", f"{x['sell']:,.0f}", x["ret"]) for x in C if x.get("ret") is not None))


def review():
    today = AT.now().strftime("%Y%m%d")
    snap = jload(OUT / ("snap_%s.json" % today))
    if not snap:
        log("오늘 기록 없음 — 건너뜀"); return
    lf = OUT / "log.csv"
    if lf.exists() and ("\n" + today + ",") in lf.read_text(encoding="utf-8-sig"):
        log("오늘 채점 이미 있음"); return
    mf = BASE / "data" / "m1" / "KR" / "day" / ("%s.parquet" % today)
    opens = {}
    if mf.exists():
        import pandas as pd
        X = pd.read_parquet(mf, columns=["t", "ts", "o", "v"])
        X = X[X.v > 0].sort_values(["t", "ts"])
        opens = X.groupby("t").o.first().astype(float).to_dict()
    rows = []
    for x in snap.get("cand") or []:
        o_ = opens.get(x["t"])
        if o_ is None:
            try: o_ = D.krx_open(x["t"], today, late=True)
            except Exception: o_ = None
        try: B = [r for r in pm_bars(x["t"], today, "0850") if "0841" <= r[0] <= "0845"]
        except Exception: B = []
        v = sum(r[5] for r in B); vw = sum(r[4] * r[5] for r in B) / v if v else None
        hi = max((r[2] for r in B if r[5] > 0), default=None)
        f_ = lambda p: round((o_ / p - 1) * 100 - COST, 3) if (o_ and p) else ""
        rows.append([today, x["t"], x["name"], x["pre"], x["rel"], x.get("cum", ""), int(bool(x.get("pick"))), x.get("ask", ""), x.get("qty", ""),
                     x.get("fq", ""), x.get("ap", ""), x.get("sell", ""), x.get("ret", ""), o_ or "", round(vw, 2) if vw else "", hi or "",
                     f_(vw), f_(x.get("ask")), round(v * (vw or 0))])
        x.update(open=o_, vw=vw, r_vw=f_(vw))
        time.sleep(0.1)
    new = not lf.exists()
    with open(lf, "a", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        if new: w.writerow(["날짜", "종목", "이름", "어제 대비", "시장 대비", "장전 누적 거래대금", "고름", "매도1호가", "주문 주수", "체결 주수", "매수가",
                            "매도가", "실제 수익(비용 뒤)", "KRX 시가", "08:41~45 VWAP", "그 사이 최고가", "VWAP 기준 수익", "1호가 기준 수익", "08:41~45 거래대금"])
        w.writerows(rows)
    snap["reviewed"] = True; jsave(OUT / ("snap_%s.json" % today), snap); publish(snap)
    pk = [x for x in snap.get("cand") or [] if x.get("pick")]
    rv = [x["r_vw"] for x in pk if x.get("r_vw") != ""]
    ra = [x["ret"] for x in pk if x.get("ret") is not None]
    wide = [x["r_vw"] for x in snap.get("cand") or [] if not x.get("pick") and x.get("r_vw") != ""]
    avg = lambda L: sum(L) / len(L) if L else float("nan")
    D.telegram("📊 [%s] %s/%s 고른 %d · VWAP 기준 %+.2f%% · 실제 %s · 안 고른 -2%%p↓ %d개 %+.2f%%" % (
        RNAME, today[4:6], today[6:], len(pk), avg(rv), ("%+.2f%%(%d건)" % (avg(ra), len(ra))) if ra else "-", len(wide), avg(wide)))
    log("채점 %d줄" % len(rows))


if __name__ == "__main__":
    a = sys.argv[1:]
    try:
        if a[:1] == ["morning"]: morning()
        elif a[:1] == ["review"]: review()
        else: log("사용법: python nxt_pre.py morning | review")
    except (Exception, SystemExit) as ex:
        log("실패:", repr(ex)[:500])
        D.telegram("⚠ [%s] 실패: %s" % (RNAME, str(ex)[:300])); raise
