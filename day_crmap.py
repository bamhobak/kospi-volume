# -*- coding: utf-8 -*-
"""스윙 규칙 P9 [반대매매] — 2026-11-12 사용자 "1주 실주문 시험" → "C로 바꾸고 데이에서 스윙으로" → "갭 -3%·7일로 · 우선순위대로"
(research H0411·H0415 · crmap_1112~8).

규칙: 신용으로 산 물량을 매입 가격 칸별로 쌓아 두고(지도 모델: 신규 신용을 그날 종가 칸에, 상환은 비례로 뺌), 종가가 담보 선
      (칸 가격 × 0.6 × 1.4 = 평균 단가의 84%)을 깨는 칸을 '강제 물량'으로 센다. 그저께(D) 강제 물량 × 종가 ÷ 20일 거래대금 = F ≥ 0.3 이면
      오늘(D+2) 시가 단일가에 **어제 종가 × 0.97 지정가**로 산다 → 시가가 -3% 넘게 빠져 열려야만 체결(규칙 조건 그대로) →
      **7거래일째 종가**에 판다(매도는 자동매매 sell — 사이트 스윙 보유 · 원장 rid P9 · index.html P9 hold 7).
      신용 자료는 3거래일 묵은 것(L=3)만 — 아침에 실제로 3거래일 늦게 들어온다.
근거: 2016~ 연 144건 · 건당 +3.45%(체결 손해 뒤) · 연 손익 2016~22 +659만 / 2023~ +899만(종목당 200만·하루 5천만) · 플러스 해 10/11.
우선순위: 하루 기대 0.49% — 국장 스윙(08:51)·데이 [갭하락](08:52~) 주문이 다 나간 뒤 08:57 에 남은 돈으로(사용자 '우선순위대로').
금액: 1주 시험(지금). 시험 통과 뒤 실금액 = 종목당 200만과 20일 평균 시가 거래대금 10% 중 작은 값(research/crmap_fill_1112).
  python day_crmap.py morning   07:35 — 후보 계산(약 5분) → 08:57 1주 지정가(OPG) → 09:00 시가>지정가 즉시 취소 → 09:01 남은 것 취소 → 스윙 보유에 기록
  python day_crmap.py close     16:25 — 규칙상 사진 후보(시가 ≤ 지정가) 전부를 data/day/crmap_hits.csv 에 적음(돈·체결과 무관한 채점용)
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

RID, RNAME = "P9", "반대매매"
K_RATIO, LAG, F_MIN, GAP = 1.4, 3, 0.3, -3.0
MAXN = 25                       # 하루 최대(F 큰 순) — 실금액 때 200만 × 25 = 5천만
PLACE_AT = (8, 57)              # 우선순위 꼴찌 — 스윙 08:51·데이 08:52~ 주문 뒤 남은 돈으로
QTY = 1                         # 1주 시험


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
        AT.telegram("⚠ [%s] 신용 자료 %d거래일 묵음 — 오늘 안 삼" % (RNAME, info["credit_lag"])); return
    rows = rows[:MAXN]
    nm = {k: v[0] for k, v in AT.names([r["t"] for r in rows]).items()} if rows else {}
    for r in rows: r["name"] = nm.get(r["t"], r["t"])
    J = dict(date=today, info=info, cand=rows, real=[], skip=[])
    f = OUT / ("crmap_%s.json" % today)
    f.write_text(json.dumps(J, ensure_ascii=False), encoding="utf-8")
    if not rows:
        log("오늘 후보 없음"); return
    live = D.env().get("DAY_MODE", "notify") == "live" and not (AT.OUT / "STOP").exists()
    if not live:
        log("실매수 꺼짐(DAY_MODE·STOP) — 후보만 기록"); return
    AT.sleep_until(S["start"].replace(hour=PLACE_AT[0], minute=PLACE_AT[1], second=0), "장전 주문(스윙·데이 뒤)")
    try: bp = AT.buying_power("KRW")
    except AT.TossErr: bp = None
    Lg = AT.led(); placed = []
    for r in rows:
        q = QTY
        if bp is not None and bp < r["lim"] * q * 1.02:
            J["skip"].append(dict(r, why="돈 모자람")); continue
        cid = "sp9%s%s" % (today, r["t"])
        o = dict(side="BUY", date=today, t=r["t"], name=r["name"], qty=q, cid=cid, rid=RID, mk="KR", pc=r["pc"], lim=r["lim"], F=r["F"], at=AT.now().isoformat())
        body = {"clientOrderId": cid, "symbol": r["t"], "side": "BUY", "orderType": "LIMIT", "timeInForce": "OPG", "price": str(r["lim"]), "quantity": str(q)}
        try:
            ok = AT.submit(Lg, o, body)
        except AT.TossErr as ex:
            J["skip"].append(dict(r, why=ex.code or str(ex)[:60])); log("주문 거부", r["t"], ex.code); continue
        if not ok:
            log("주문 결과 모름", r["t"]); continue
        placed.append(o)
        if bp is not None: bp -= r["lim"] * q
        time.sleep(0.4)
    AT.led_save(Lg)
    f.write_text(json.dumps(J, ensure_ascii=False), encoding="utf-8")
    log("주문 %d · 못 낸 것 %d" % (len(placed), len(J["skip"])))
    if not placed:
        if J["skip"]: AT.telegram("💥 <b>[%s]</b> %s/%s 후보 %d · 주문 못 냄(%s)" % (RNAME, today[4:6], today[6:], len(rows), J["skip"][0]["why"]))
        return
    AT.sleep_until(S["start"], "시가 단일가")
    D.open_guard(placed, today)                                          # 시가 > 지정가면 바로 취소(OPG 지정가는 장중까지 살아 있다)
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
    got = []
    for o in placed:
        if (o.get("fq") or 0) > 0 and (o.get("ap") or 0) > 0:
            o["pos"] = {"id": AT.new_id(), "code": o["t"], "name": o["name"], "date": today, "price": o["ap"],
                        "qty": int(o["fq"]) if o["fq"] == int(o["fq"]) else o["fq"], "filters": [RID], "fx": None, "auto": True, "oid": o["oid"]}
            o["pf"] = o["fq"]; got.append(o)
    AT.led_save(Lg)
    if got: AT.site_update(lambda P: (P.extend(dict(o["pos"]) for o in got) or True), "[%s] 매수 %d건" % (RNAME, len(got)))
    J["real"] = [dict(t=o["t"], name=o["name"], fq=o.get("fq"), ap=o.get("ap"), lim=o["lim"], F=o["F"]) for o in got]
    f.write_text(json.dumps(J, ensure_ascii=False), encoding="utf-8")
    L = ["💥 <b>[%s] 매수</b> %s/%s 시가 · 후보 %d · 지정가(어제 종가 -3%%) %d · 사짐 %d · 7거래일째 종가 매도" % (RNAME, today[4:6], today[6:], len(rows), len(placed), len(got))]
    L += ["✅ %s %d주 @ %s원 (어제 종가 대비 %+.1f%%)" % (o["name"], int(o["fq"]), f"{o['ap']:,.0f}", (o["ap"] / o["pc"] - 1) * 100) for o in got]
    AT.telegram("\n".join(L))


def close():
    """규칙상 사진 후보(시가 ≤ 지정가) 전부를 기록 — 7일 뒤 채점용(돈·체결과 무관)."""
    today = dt.datetime.now().strftime("%Y%m%d")
    f = OUT / ("crmap_%s.json" % today)
    if not f.exists():
        log("오늘 기록 없음 — 건너뜀"); return
    J = json.loads(f.read_text(encoding="utf-8"))
    if not J.get("cand"): return
    oc = m1_day(today)
    if oc is None or len(oc) < 500:
        log("오늘 1분봉 부족 — 건너뜀"); return
    real = {z["t"] for z in J.get("real") or []}
    rows = [dict(date=today, t=z["t"], name=z.get("name", z["t"]), F=z["F"], pc=z["pc"], lim=z["lim"], open=float(oc.o[z["t"]]), close=float(oc.c[z["t"]]),
                 hit=int(oc.o[z["t"]] <= z["lim"]), real=int(z["t"] in real)) for z in J["cand"] if z["t"] in oc.index]
    lf = OUT / "crmap_hits.csv"; new = not lf.exists()
    with open(lf, "a", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["date", "t", "name", "F", "pc", "lim", "open", "close", "hit", "real"])
        if new: w.writeheader()
        for r in rows: w.writerow(r)
    log("후보 %d · 규칙상 사짐 %d · 실매수 %d" % (len(rows), sum(r["hit"] for r in rows), len(real)))


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
            import autotrade as AT; AT.telegram("⚠ [%s] 오류: %s" % (RNAME, str(ex)[:200]))
        except Exception: pass
        raise
