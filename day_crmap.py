# -*- coding: utf-8 -*-
"""데이 규칙 T8 [반대매매] — 2026-11-12 사용자 "1주 실주문 시험"(H0411, research/crmap_1112·2·3 · league/league.py).

규칙: 신용으로 산 물량을 매입 가격 칸별로 쌓아 두고(지도 모델: 신규 신용을 그날 종가 칸에, 상환은 비례로 뺌), 종가가 담보 선
      (칸 가격 × 0.6 × 1.4 = 평균 단가의 84%)을 깨는 칸을 '강제 물량'으로 센다. 그저께(D) 강제 물량 × 종가 ÷ 20일 거래대금 = F ≥ 1 이면
      오늘(D+2) 시가 단일가에 **어제 종가 × 0.99 지정가**로 산다 → 시가가 -1% 넘게 빠져 열려야만 체결(규칙 조건 그대로) → 종가 단일가에 판다.
      신용 자료는 3거래일 묵은 것(L=3)만 — 아침에 실제로 3거래일 늦게 들어온다.
근거: 날 바구니 +0.81/+0.90/+0.88%(옛날 10~15/학습/검증, t3~4) · 같은 날·같은 갭 대조 대비 +0.45/+0.63/+0.68 · 연 ~245건 ·
      이웃 문턱(F 0.5/1/2 × 갭 -1/-2/-4) 9칸 모두 3구간 플러스 · [갭하락]과 겹침 0.4%.
  python day_crmap.py morning   07:35 — 후보 계산(약 5분) → 08:45 1주 지정가(OPG) → 09:00 시가>지정가 즉시 취소 → 09:01 남은 것 취소
                                  매도는 15:24 데이 지킴이가 종가 단일가에(원장 rid T8, 사이트 데이 보유)
  python day_crmap.py close     16:25 — 돈 모자라 못 낸 몫은 '시가 ≤ 지정가면 사진 것'으로 가상 매수·종가 매도 · 성적 한 줄 · data/day/crmap_log.csv
  python day_crmap.py pick      후보만 계산해 보여 줌(주문 없음)
"""
import csv, datetime as dt, json, math, sys, time
from pathlib import Path

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE)); sys.path.insert(0, str(BASE / "research")); sys.path.insert(0, str(BASE / "research" / "factory")); sys.path.insert(0, str(BASE / "research" / "league"))
OUT = BASE / "data" / "day"
LOG = OUT / "crmap.log"
if sys.stdout is None or sys.stderr is None:                             # pythonw(예약 작업)는 stdout 이 없다
    sys.stdout = sys.stderr = open(LOG, "a", encoding="utf-8", buffering=1)
import numpy as np, pandas as pd

RID, RNAME = "T8", "반대매매"
K_RATIO, LAG, F_MIN, GAP = 1.4, 3, 1.0, -1.0
MAXN = 10                       # 하루 최대(F 큰 순) — 1주 시험
PLACE_AT = (8, 45)              # 장전 주문 시각(데이 아침 08:52~ 몰림 전)


def log(*a):
    print("%s %s" % (dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), " ".join(str(x) for x in a)), flush=True)


def m1_day(day):
    f = BASE / "data" / "m1" / "KR" / "day" / ("%s.parquet" % day)
    if not f.exists(): return None
    X = pd.read_parquet(f, columns=["t", "ts", "o", "c", "v"]); X = X[X.v > 0].sort_values(["t", "ts"])
    g = X.groupby("t")
    return pd.DataFrame({"o": g.o.first(), "c": g.c.last()})


def pick(today, prev=None):
    """오늘 매수 후보: 사건 날 D = 오늘의 2거래일 전. [(t, F, pc, lim)]"""
    import league as LGM
    import day_alert as D
    cal, tk, CL, NW, RD, RM, CC, amt20, base_ok, sp = LGM.load()
    cal = np.array(cal)
    cal_ok = cal[cal < today]
    last = cal_ok[-1]                                                    # 어제(매수 날 전 거래일)
    if prev and last != prev:
        raise RuntimeError("어제(%s) 종가 자료 없음 — 마지막 %s" % (prev, last))
    di = int(np.searchsorted(cal, last)) - 1                             # D = 어제의 전 거래일
    if di < 300: raise RuntimeError("자료 부족")
    # 신용 자료가 너무 묵었으면(지연 6거래일 넘음) 쉼
    import sqlite3
    c = sqlite3.connect(f"file:{BASE / 'data' / 'kis' / 'market.db'}?mode=ro", uri=True)
    cmax = c.execute("select max(date) from credit").fetchone()[0]; c.close()
    need = cal[di - LAG]
    lag_now = int((cal[:di + 1] > cmax).sum())
    ev = LGM.cohort_events(K_RATIO, LAG, di, cal, tk, CL, NW, RD, RM, CC, amt20, base_ok, sp)
    ev = [(i, t, f) for i, t, f in ev if i == di and f == f and f >= F_MIN]
    li = int(np.searchsorted(cal, last))
    rows = []
    for i, t, f in sorted(ev, key=lambda z: -z[2]):
        pc = float(CL[li, t])
        if not (pc == pc and pc >= 1000): continue
        p = pc * (1 + GAP / 100); tick = D.kr_tick(p)
        rows.append(dict(t=str(tk[t]), F=round(float(f), 2), pc=pc, lim=int(math.floor(p / tick) * tick), d=str(cal[di])))
    return rows, dict(D=str(cal[di]), prev=str(last), credit_max=cmax, credit_need=str(need), credit_lag=lag_now)


def morning():
    import autotrade as AT
    import day_alert as D
    today = AT.now().strftime("%Y%m%d")
    S = AT.session("KR")
    if not S or S["date"] != today:
        log("국장 휴장 — 건너뜀"); return
    rows, info = pick(today, S.get("prev"))
    log("후보 %d (사건 날 %s · 신용 끝 %s · 지연 %d거래일)" % (len(rows), info["D"], info["credit_max"], info["credit_lag"]))
    if info["credit_lag"] > 6:
        D.telegram("⚠ [%s] 신용 자료 %d거래일 묵음 — 오늘 안 삼" % (RNAME, info["credit_lag"])); return
    rows = rows[:MAXN]
    nm = {k: v[0] for k, v in AT.names([r["t"] for r in rows]).items()} if rows else {}
    for r in rows: r["name"] = nm.get(r["t"], r["t"])
    J = dict(date=today, info=info, cand=rows, real=[], paper=[])
    f = OUT / ("crmap_%s.json" % today)
    f.write_text(json.dumps(J, ensure_ascii=False), encoding="utf-8")
    if not rows:
        log("오늘 후보 없음"); return
    live = D.env().get("DAY_MODE", "notify") == "live" and not (AT.OUT / "STOP").exists()
    AT.sleep_until(S["start"].replace(hour=PLACE_AT[0], minute=PLACE_AT[1], second=0), "장전 주문")
    try: bp = AT.buying_power("KRW") if live else 0.0
    except AT.TossErr: bp = None
    Lg = D._led(); placed = []
    for r in rows:
        q = 1
        if not live or (bp is not None and bp < r["lim"] * q * 1.02):
            J["paper"].append(dict(r, why="돈 모자람" if live else "실매수 꺼짐")); continue
        cid = "da8%s%s" % (today, r["t"])
        o = dict(side="BUY", date=today, t=r["t"], name=r["name"], qty=q, cid=cid, rid=RID, pc=r["pc"], lim=r["lim"], F=r["F"], at=AT.now().isoformat())
        body = {"clientOrderId": cid, "symbol": r["t"], "side": "BUY", "orderType": "LIMIT", "timeInForce": "OPG", "price": str(r["lim"]), "quantity": str(q)}
        try:
            ok = AT.submit(Lg, o, body, D._led_save)
        except AT.TossErr as ex:
            if ex.code in ("insufficient-buying-power", "opposite-pending-order-exists"):
                J["paper"].append(dict(r, why=ex.code)); continue
            log("주문 거부", r["t"], ex.code); continue
        if not ok:
            log("주문 결과 모름", r["t"]); continue
        placed.append(o)
        if bp is not None: bp -= r["lim"] * q
        time.sleep(0.4)
    f.write_text(json.dumps(J, ensure_ascii=False), encoding="utf-8")
    log("주문 %d · 가상 %d" % (len(placed), len(J["paper"])))
    if placed:
        AT.sleep_until(S["start"], "시가 단일가")
        D.open_guard(placed, today)
        AT.sleep_until(S["start"] + dt.timedelta(seconds=65), "시가 체결 확인")
        D.cancel_left(placed)
        AT.wait_fills([o for o in placed if not o.get("canceled")])
        for o in placed:
            if not o.get("canceled"): continue
            try:
                ex_ = ((AT.detail(o["oid"]) or {}).get("execution") or {})
                o["fq"] = float(ex_.get("filledQuantity") or 0); o["ap"] = float(ex_.get("averageFilledPrice") or 0); o["status"] = "CANCELED"
            except Exception:
                o["fq"], o["ap"], o["status"] = 0.0, 0.0, None
        got = [o for o in placed if (o.get("fq") or 0) > 0 and (o.get("ap") or 0) > 0]
        for o in got: o["pos"] = D.day_pos(o); o["pf"] = o["fq"]
        D._led_save(Lg)
        if got: D.scalp_update(lambda X: (X.extend(dict(o["pos"]) for o in got) or True), "데이 [%s] 매수 %d건" % (RNAME, len(got)))
        J["real"] = [dict(t=o["t"], name=o["name"], fq=o.get("fq"), ap=o.get("ap"), lim=o["lim"], F=o["F"]) for o in got]
        f.write_text(json.dumps(J, ensure_ascii=False), encoding="utf-8")
        D.telegram("💥 <b>[%s]</b> %s/%s 후보 %d · 1주 지정가 %d · 시가에 사짐 %d%s" % (
            RNAME, today[4:6], today[6:], len(rows), len(placed), len(got), (" · 가상 %d" % len(J["paper"])) if J["paper"] else ""))
    elif J["paper"]:
        D.telegram("💥 <b>[%s]</b> %s/%s 후보 %d · 가상 %d(실매수 안 함)" % (RNAME, today[4:6], today[6:], len(rows), len(J["paper"])))


def close():
    import autotrade as AT
    import day_alert as D
    today = AT.now().strftime("%Y%m%d")
    f = OUT / ("crmap_%s.json" % today)
    if not f.exists():
        log("오늘 기록 없음 — 건너뜀"); return
    J = json.loads(f.read_text(encoding="utf-8"))
    if not J.get("cand"): return
    oc = m1_day(today)
    if oc is None or len(oc) < 500:
        log("오늘 1분봉 부족 — 건너뜀"); return
    # 가상: 시가 ≤ 지정가면 시가에 사진 것
    pp = []
    for z in J.get("paper") or []:
        if z["t"] in oc.index and oc.o[z["t"]] <= z["lim"]:
            pp.append(dict(z, buy=float(oc.o[z["t"]]), sell=float(oc.c[z["t"]])))
    if pp:
        base = int(time.time() * 1000)

        def add(X):
            have = {(x.get("code"), str(x.get("date"))) for x in X if x.get("paper") and (x.get("filters") or [None])[0] == RID}
            n = 0
            for i, z in enumerate(pp):
                if (z["t"], today) in have: continue
                X.append({"id": base + 800 + i, "code": z["t"], "name": z.get("name", z["t"]), "date": today, "price": z["buy"], "qty": 1,
                          "filters": [RID], "auto": True, "day": True, "paper": True, "sell": z["sell"], "sellDate": today}); n += 1
            return n > 0
        D.scalp_update(add, "데이 [%s] 가상 %d건(시가 매수·종가 매도)" % (RNAME, len(pp)))
    rr = [(oc.c[z["t"]] / z["ap"] - 1) * 100 - D.COST for z in J.get("real") or [] if z["t"] in oc.index and z.get("ap")]
    rp = [(z["sell"] / z["buy"] - 1) * 100 - D.COST for z in pp]
    hit = [z for z in J["cand"] if z["t"] in oc.index and oc.o[z["t"]] <= z["lim"]]           # 규칙상 사지는 후보 전부(돈·체결과 무관)
    rh = [(oc.c[z["t"]] / oc.o[z["t"]] - 1) * 100 - D.COST for z in hit]
    mk = float(((oc.c / oc.o - 1) * 100 - D.COST).clip(-30, 30).mean())
    line = "💥 [%s] 결과 %s/%s 후보 %d · 시가 -1%%↓로 열림 %d %s · 실매수 %d %s · 가상 %d %s · 시장 %+.2f%%" % (
        RNAME, today[4:6], today[6:], len(J["cand"]), len(hit), ("%+.2f%%" % np.mean(rh)) if rh else "-",
        len(rr), ("%+.2f%%" % np.mean(rr)) if rr else "-", len(rp), ("%+.2f%%" % np.mean(rp)) if rp else "-", mk)
    if hit: D.telegram(line)
    log(line)
    lf = OUT / "crmap_log.csv"; new = not lf.exists()
    with open(lf, "a", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        if new: w.writerow(["날짜", "후보", "사지는 후보", "사지는 후보 평균", "실매수", "실매수 평균", "가상", "가상 평균", "시장 평균"])
        w.writerow([today, len(J["cand"]), len(hit), round(float(np.mean(rh)), 3) if rh else "", len(rr), round(float(np.mean(rr)), 3) if rr else "",
                    len(rp), round(float(np.mean(rp)), 3) if rp else "", round(mk, 3)])


if __name__ == "__main__":
    a = sys.argv[1:]
    try:
        if a[:1] == ["morning"]: morning()
        elif a[:1] == ["close"]: close()
        elif a[:1] == ["pick"]:
            import autotrade as AT
            d = a[1] if len(a) > 1 else AT.now().strftime("%Y%m%d")
            rows, info = pick(d); print(info)
            for r in rows[:30]: print(r)
            print("후보", len(rows))
        else: print("사용법: python day_crmap.py morning | close | pick [YYYYMMDD]")
    except Exception as ex:
        log("실패:", repr(ex)[:400])
        try:
            import day_alert as D; D.telegram("⚠ [%s] 오류: %s" % (RNAME, str(ex)[:200]))
        except Exception: pass
        raise
