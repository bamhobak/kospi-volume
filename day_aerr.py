# -*- coding: utf-8 -*-
"""⛔ 2026-11-12 뺌(사용자 "a5 규칙은 다시 빼자") — 녹화 23일로 다시 재니 그림자 3일만 좋았고 100만 실금액이면 손해(research/a5_tighten_1112.out).
예약 작업 \BamhobakDay\AerrMorning·AerrClose 꺼 둠, 사이트 T7 칸 지움. 다시 쓰려면 둘 다 되살리기. 공장 그림자 F1659 는 계속 기록.

데이 규칙 T7 [예상 하회] — 2026-11-12 사용자 "f1659는 바로 규칙으로 넣어주고, 1주씩 사는 걸로 먼저, 돈 없더라도 가상 매수·매도".

근거: 규칙 공장 그림자 F1659(정답지: 장전 예상 갭 − 실제 갭 상위 10% · 시가 매수 → 종가 매도). 11-09~11 3일 292건 건당 +3.73%·승률 76%,
  같은 날 유니버스 평균(+0.67/+1.34/+3.13%)보다 매일 +2%p↑ · [갭하락] 후보와 겹침 4%. 뒤집은 판 F1660 은 시장과 같음. **과거 자료 없음(녹화 11-0x~)**.
  python day_aerr.py morning   08:59 — 09:00 시가 직후: 유니버스(데이 아침 snap 의 all) 중 a_err = (장전 호가 균형가[auction 마지막 녹화] − 지금가) ÷ 어제 KRX 종가
                                     상위 10% → 1주씩 시장가 매수(돈 모자라·반대 주문이면 가상) → 원장 rid T7 · 사이트 데이 보유. 매도는 15:24 데이 지킴이가 종가 단일가에.
  python day_aerr.py close     16:20 — 가상 몫을 KRX 종가(1분봉 마지막 봉)로 매도 기록 · 성적 한 줄 텔레그램 · data/day/aerr_log.csv
⚠ 연구는 '시가'에 샀다고 쟀지만 실전은 09:00:12 지금가로 고르고 그 직후 시장가로 산다 — 시가와 몇 초 차이가 난다.
"""
import csv, datetime as dt, json, sys, time
from pathlib import Path

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE)); sys.path.insert(0, str(BASE / "research" / "factory"))
OUT = BASE / "data" / "day"
LOG = OUT / "aerr.log"
if sys.stdout is None or sys.stderr is None:                             # pythonw(예약 작업)는 stdout 이 없다
    sys.stdout = sys.stderr = open(LOG, "a", encoding="utf-8", buffering=1)
import numpy as np, pandas as pd
import collect_m1 as M
import autotrade as AT
import day_alert as D

RID, RNAME = "T7", "예상 하회"
TOP = 0.10                     # a_err 상위 10%(F1659 와 같게)
DECIDE = 12                    # 시가 뒤 이만큼(초) 기다렸다가 지금가로 고른다
TIGHT_AERR, TIGHT_GAP = 3.0, -2.0   # 조인 판(11-12 사전 등록, research/reports/prereg_a5_1112.md) — 채점만, 고르기는 그대로


def tight(z):
    """조인 판에 드는가: a_err ≥ 3%p · 고를 때 가격이 어제 종가보다 2%↓."""
    try: return float(z["aerr"]) >= TIGHT_AERR and (float(z["p"]) / float(z["pc"]) - 1) * 100 <= TIGHT_GAP
    except (KeyError, TypeError, ValueError, ZeroDivisionError): return False


def log(*a):
    s = "%s %s" % (dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), " ".join(str(x) for x in a))
    print(s, flush=True)


def m1_close(day):
    f = BASE / "data" / "m1" / "KR" / "day" / ("%s.parquet" % day)
    if not f.exists(): return {}
    X = pd.read_parquet(f, columns=["t", "ts", "c", "v"]); X = X[X.v > 0].sort_values(["t", "ts"])
    return X.groupby("t").c.last().to_dict()


def last_prices(syms, today):
    out = {}
    for i in range(0, len(syms), 200):
        for x in M.get("/api/v1/prices", symbols=",".join(syms[i:i + 200])) or []:
            ts = x.get("timestamp") or ""
            if ts[:10].replace("-", "") == today and ts[11:19] >= "09:00:00": out[x["symbol"]] = float(x["lastPrice"])
    return out


def morning():
    today = AT.now().strftime("%Y%m%d")
    S = AT.session("KR")
    if not S or S["date"] != today:
        log("국장 휴장 — 건너뜀"); return
    f = OUT / ("snap_%s.json" % today)
    for _ in range(40):                                                 # 데이 아침(08:52~54)이 snap 을 남길 때까지
        if f.exists(): break
        time.sleep(15)
    if not f.exists():
        log("데이 아침 snap 없음 — 유니버스를 몰라 건너뜀"); D.telegram("⚠ [%s] 유니버스 없음 — 오늘 안 삼" % RNAME); return
    snap = json.loads(f.read_text(encoding="utf-8"))
    uni = sorted((snap.get("all") or {}).keys())
    pc = m1_close(snap.get("prev"))
    import auction as AU
    F = AU.features(today)
    if F is None or F.empty or F.eq59.notna().sum() < 300:
        log("장전 호가 녹화 없음·부족 — 건너뜀"); D.telegram("⚠ [%s] 장전 호가 녹화 부족 — 오늘 안 삼" % RNAME); return
    eq = F.set_index("ticker").eq59.to_dict()
    AT.sleep_until(S["start"] + dt.timedelta(seconds=DECIDE), "시가 뒤 %d초" % DECIDE)
    px = last_prices(uni, today)
    rows = []
    for t in uni:
        p0, e, p = pc.get(t), eq.get(t), px.get(t)
        if not (p0 and e and p) or p0 < 1000 or e != e: continue
        if abs(p / p0 - 1) >= 0.29: continue                            # 상·하한가 근처는 뺀다
        rows.append((t, (e - p) / p0 * 100, p, e, p0))
    if len(rows) < 300:
        log("값 있는 종목 %d — 너무 적어 건너뜀" % len(rows)); D.telegram("⚠ [%s] 시가 값 %d종목뿐 — 오늘 안 삼" % (RNAME, len(rows))); return
    R = pd.DataFrame(rows, columns=["t", "aerr", "p", "eq", "pc"])
    R["q"] = R.aerr.rank(pct=True)
    P = R[R.q >= 1 - TOP].sort_values("aerr", ascending=False)
    nm = {k: v[0] for k, v in AT.names(list(P.t)).items()}
    log("고름 %d/%d종목 · a_err 문턱 %+.2f%%p" % (len(P), len(R), P.aerr.min()))
    live = D.env().get("DAY_MODE", "notify") == "live" and not (AT.OUT / "STOP").exists()
    try: bp = AT.buying_power("KRW") if live else 0.0
    except AT.TossErr: bp = None
    Lg = D._led(); placed, paper = [], []
    for r in P.itertuples():
        q = D.DAY_QTY or 1
        name = nm.get(r.t, r.t)
        rec = dict(t=r.t, name=name, aerr=round(r.aerr, 3), p=r.p, eq=r.eq, pc=r.pc, qty=q)
        if not live or (bp is not None and bp < r.p * q * 1.02):
            paper.append(dict(rec, why="돈 모자람" if live else "실매수 꺼짐")); continue
        cid = "da7%s%s" % (today, r.t)
        o = dict(side="BUY", date=today, t=r.t, name=name, qty=q, cid=cid, rid=RID, pc=r.pc, p=r.p, aerr=round(r.aerr, 3), at=AT.now().isoformat())
        body = {"clientOrderId": cid, "symbol": r.t, "side": "BUY", "orderType": "MARKET", "timeInForce": "DAY", "quantity": str(q)}
        try:
            ok = AT.submit(Lg, o, body, D._led_save)
        except AT.TossErr as ex:
            if ex.code in ("insufficient-buying-power", "opposite-pending-order-exists"):
                paper.append(dict(rec, why=ex.code)); continue
            log("주문 거부", r.t, ex.code); continue
        if not ok:
            log("주문 결과 모름", r.t); continue
        placed.append(o)
        if bp is not None: bp -= r.p * q
        time.sleep(0.3)
    AT.wait_fills(placed)
    got = [o for o in placed if (o.get("fq") or 0) > 0 and (o.get("ap") or 0) > 0]
    for o in got: o["pos"] = D.day_pos(o); o["pf"] = o["fq"]
    D._led_save(Lg)
    if got: D.scalp_update(lambda X: (X.extend(dict(o["pos"]) for o in got) or True), "데이 [%s] 매수 %d건" % (RNAME, len(got)))
    base = int(time.time() * 1000)

    def add(X):
        have = {(x.get("code"), str(x.get("date"))) for x in X if x.get("paper") and (x.get("filters") or [None])[0] == RID}
        n = 0
        for i, z in enumerate(paper):
            if (z["t"], today) in have: continue
            X.append({"id": base + 300 + i, "code": z["t"], "name": z["name"], "date": today, "price": z["p"], "qty": z["qty"],
                      "filters": [RID], "auto": True, "day": True, "paper": True}); n += 1
        return n > 0
    if paper: D.scalp_update(add, "데이 [%s] 가상 매수 %d건" % (RNAME, len(paper)))
    (OUT / ("aerr_%s.json" % today)).write_text(json.dumps({"date": today, "n_uni": len(R), "cut": round(float(P.aerr.min()), 3),
        "open": {r.t: r.p for r in R.itertuples()},                     # 고를 때 전 종목 지금가 — 같은 날 시장 평균(대조) 채점용
        "real": [dict(t=o["t"], name=o["name"], fq=o.get("fq"), ap=o.get("ap"), aerr=o.get("aerr"), p=o.get("p"), pc=o.get("pc")) for o in got], "paper": paper}, ensure_ascii=False), encoding="utf-8")
    log("실매수 %d · 미체결 %d · 가상 %d" % (len(got), len(placed) - len(got), len(paper)))
    nt = sum(tight(dict(aerr=r.aerr, p=r.p, pc=r.pc)) for r in P.itertuples())
    D.telegram("🔻 <b>[%s]</b> %s/%s %d종목 · 실매수 %d · 가상 %d · 조임 %d" % (RNAME, today[4:6], today[6:], len(P), len(got), len(paper), nt))


def close():
    today = AT.now().strftime("%Y%m%d")
    f = OUT / ("aerr_%s.json" % today)
    if not f.exists():
        log("오늘 기록 없음 — 건너뜀"); return
    J = json.loads(f.read_text(encoding="utf-8"))
    cl = m1_close(today)
    if len(cl) < 500:
        log("오늘 1분봉 종가 부족(%d) — 건너뜀" % len(cl)); return
    upd = {}

    def mark(X):
        for x in X:
            if x.get("paper") and (x.get("filters") or [None])[0] == RID and str(x.get("date")) == today and not x.get("sell") and cl.get(x.get("code")):
                x["sell"] = cl[x["code"]]; x["sellDate"] = today; upd[x["id"]] = x
        return bool(upd)
    D.scalp_update(mark, "데이 [%s] 가상 매도(종가) %d건" % (RNAME, len(J.get("paper") or [])))
    rp = [(float(x["sell"]) / float(x["price"]) - 1) * 100 - D.COST for x in upd.values()]
    rr = [(cl[z["t"]] / z["ap"] - 1) * 100 - D.COST for z in J.get("real") or [] if cl.get(z["t"]) and z.get("ap")]
    allr = rr + rp
    if not allr: return
    rt = [(cl[z["t"]] / float(z.get("ap") or z["p"]) - 1) * 100 - D.COST for z in (J.get("real") or []) + (J.get("paper") or [])
          if tight(z) and cl.get(z["t"]) and (z.get("ap") or z.get("p"))]
    line = "🔻 [%s] 결과 %s/%s %d건 %+.2f%% · 상승 %d/%d (실매수 %d건 %s · 가상 %d건 %s) · 조임 %d건 %s" % (
        RNAME, today[4:6], today[6:], len(allr), np.mean(allr), sum(r > 0 for r in allr), len(allr),
        len(rr), ("%+.2f%%" % np.mean(rr)) if rr else "-", len(rp), ("%+.2f%%" % np.mean(rp)) if rp else "-",
        len(rt), ("%+.2f%%" % np.mean(rt)) if rt else "-")
    D.telegram(line); log(line)
    lf = OUT / "aerr_log.csv"; new = not lf.exists()
    with open(lf, "a", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        if new: w.writerow(["날짜", "건수", "평균(비용 뒤)", "승률", "실매수 건수", "실매수 평균", "가상 건수", "가상 평균", "조임 건수", "조임 평균", "시장 평균"])
        mk = [(cl[t] / px - 1) * 100 - D.COST for t, px in (J.get("open") or {}).items() if cl.get(t) and px]
        w.writerow([today, len(allr), round(float(np.mean(allr)), 3), round(sum(r > 0 for r in allr) / len(allr) * 100), len(rr),
                    round(float(np.mean(rr)), 3) if rr else "", len(rp), round(float(np.mean(rp)), 3) if rp else "",
                    len(rt), round(float(np.mean(rt)), 3) if rt else "", round(float(np.mean(mk)), 3) if mk else ""])


if __name__ == "__main__":
    a = sys.argv[1:]
    try:
        if a[:1] == ["morning"]: morning()
        elif a[:1] == ["close"]: close()
        else: print("사용법: python day_aerr.py morning | close")
    except Exception as ex:
        log("실패:", repr(ex)[:400]); D.telegram("⚠ [%s] 오류: %s" % (RNAME, str(ex)[:200])); raise
