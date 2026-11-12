# -*- coding: utf-8 -*-
"""2026-11-13 사용자 "지금 거래한것들 실제 금액거래였다면 얼마 수익이었어?"
데이 실전 왕복(data/audit/live.csv · 1주 시험)을 지금 실전 금액 설정으로 바꿔 원화 손익.
 [갭하락]·덤: 30만(DAY_BASE) × 깊이 배율(예상 시장 대비 크기, 1~3, -10%p↓ 3) × 거래대금 배율(snap lm, 없으면 a20 ÷ 그날 후보 중앙, 0.3~3)
 [장전 되돌림]: 100만(PER) × 계단(-5↓ 3 · -4↓ 2 · 그 밖 1)
 [장후 낙폭]: 그날 pick 의 lamt = min(500만, 10분 거래대금 10%)
 체결 손해(사고+파는 합) = 0.143 + 1.321√p %, 체결률 1/(1+3p), p = 금액 ÷ 20일 평균 거래대금(KRX 1분봉 합, 있는 날만) × 100 — impact_fit realized.
 1주 실전 수익률(비용 0.23% 뺀 값)에서 손해를 더 빼고, 체결된 몫만 손익.
"""
import json, sys, glob
from pathlib import Path
import numpy as np, pandas as pd
B = Path(r"C:\vscode\kospi-volume"); sys.stdout.reconfigure(encoding="utf-8")
A = pd.read_csv(B / "data/audit/live.csv", encoding="utf-8-sig", dtype={"t": str}); A["buy_day"] = A.buy_day.astype(str)
OK = pd.read_csv(B / "research/reports/recheck_day_1113.csv", encoding="utf-8-sig", dtype={"t": str, "buy_day": str})
A = A.merge(OK[["rid", "t", "buy_day", "ok"]].drop_duplicates(["rid", "t", "buy_day"]), on=["rid", "t", "buy_day"], how="left")
# 20일 평균 거래대금(원) — KRX 1분봉 일 파일
DV = {}
for f in sorted(glob.glob(str(B / "data/m1/KR/day/*.parquet"))):
    d = Path(f).stem
    if d < "20260901": continue
    x = pd.read_parquet(f, columns=["t", "c", "v"]); DV[d] = (x.c * x.v).groupby(x.t).sum()
DAYS = sorted(DV)
def amt20(t, d):
    ds = [z for z in DAYS if z < d][-20:]
    v = [DV[z].get(t) for z in ds if t in DV[z].index]
    return float(np.mean(v)) if len(v) >= 5 else None
def snapj(p):
    p = Path(p); return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
rows = []
for r in A.itertuples():
    amt, note = None, ""
    if r.rid in ("T1", "T2", "T3"):
        s = snapj(B / ("data/day/snap_%s.json" % r.buy_day)); C = {x["t"]: x for x in (s or {}).get("cand") or []}
        x = C.get(r.t)
        if x:
            rel = float(x["rel"]); m = 3.0 if rel <= -10 else min(3.0, max(1.0, -rel))
            lm = x.get("lm")
            if lm is None:
                a = [c.get("a20") for c in C.values() if c.get("a20")]
                lm = min(3.0, max(0.3, x["a20"] / float(np.median(a)))) if x.get("a20") and a else 1.0
            amt = 300_000 * m * float(lm)
    elif r.rid == "T5":
        s = snapj(B / ("data/nxtpre/snap_%s.json" % r.buy_day)); x = {c["t"]: c for c in (s or {}).get("cand") or []}.get(r.t)
        if x:
            rel = float(x["rel"]); amt = 1_000_000 * (3 if rel <= -5 else 2 if rel <= -4 else 1)
    elif r.rid == "T6":
        s = snapj(B / ("data/nxt/pick_%s.json" % r.buy_day))
        left, got = 30_000_000, {}                         # live_buy 와 같게 — 깊은 순으로 계좌 3천만까지(낸 주문이 한도를 먹는다)
        for c in (s or {}).get("live") or []:
            a = min(float(c.get("lamt") or 0), left)
            if a < 300_000: got[c["t"]] = 0.0; continue
            got[c["t"]] = a; left -= a
        if r.t in got: amt = got[r.t] or None
        if r.t in got and not got[r.t]: amt, note = 0.0, "계좌 3천만 한도로 안 삼"
    if amt == 0.0:
        rows.append(dict(rid=r.rid, t=r.t, name=r.name, d=r.buy_day, ok=False, amt=0.0, p=0.0, fill=0.0, inv=0.0, live=float(r.live), loss=0.0, ret=0.0, pnl=0.0, pnl0=0.0, note=note)); continue
    if amt is None: amt, note = {"T5": 1_000_000, "T6": 1_000_000}.get(r.rid, 300_000), "금액 기록 없음→기본"
    a20 = amt20(r.t, r.buy_day)
    p = amt / a20 * 100 if a20 else 1.0
    loss = 0.143 + 1.321 * np.sqrt(p); fill = 1 / (1 + 3 * p)
    ret = float(r.live) - loss
    rows.append(dict(rid=r.rid, t=r.t, name=r.name, d=r.buy_day, ok=bool(r.ok) if r.ok == r.ok else True, amt=amt, p=p, fill=fill,
                     inv=amt * fill, live=float(r.live), loss=loss, ret=ret, pnl=amt * fill * ret / 100, pnl0=amt * float(r.live) / 100, note=note))
R = pd.DataFrame(rows)
R.to_csv(B / "research/reports/money_day_1113.csv", index=False, encoding="utf-8-sig")
RN = {"T1": "갭하락", "T2": "갭하락+", "T3": "갭하락++", "T5": "장전 되돌림", "T6": "장후 낙폭"}
def table(X, title):
    print("\n### " + title, "· 한도로 안 산 것", int((X.amt == 0).sum()), "건(%s)" % ",".join(X[X.amt == 0].d.unique()))
    X = X[X.amt > 0]
    print("| 규칙 | 건수 | 한 건 평균 금액 | 체결 손해 평균 | 손해 전 손익 | 손해 뒤 손익 | 넣은 돈 대비 | 하루 최대 투입 |")
    tot = [0, 0, 0]
    for rid, g in X.groupby("rid"):
        mx = g.groupby("d").inv.sum().max()
        print("| [%s] | %d | %s만 | %.2f%% | %+.0f만 | **%+.0f만** | %+.2f%% | %s만 |" % (RN[rid], len(g), round(g.amt.mean() / 1e4), g.loss.mean(), g.pnl0.sum() / 1e4,
              g.pnl.sum() / 1e4, g.pnl.sum() / g.inv.sum() * 100, round(mx / 1e4)))
        tot[0] += g.pnl0.sum(); tot[1] += g.pnl.sum(); tot[2] += len(g)
    dd = X.groupby("d").inv.sum()
    print("| 합계 | %d | | | %+.0f만 | **%+.0f만** | | %s만 |" % (tot[2], tot[0] / 1e4, tot[1] / 1e4, round(dd.max() / 1e4)))
    # 날짜별 누적
    c = X.groupby("d").pnl.sum().cumsum() / 1e4
    print("누적(만):", " ".join("%s %+.0f" % (k[4:], v) for k, v in c.items()))
    print("최악의 날 %+.0f만 (%s) · 최고의 날 %+.0f만 (%s)" % (X.groupby("d").pnl.sum().min() / 1e4, X.groupby("d").pnl.sum().idxmin(),
          X.groupby("d").pnl.sum().max() / 1e4, X.groupby("d").pnl.sum().idxmax()))
table(R, "실제로 산 것 전부 (10-07~11-12)")
table(R[R.ok | (R.amt == 0)], "지금 규칙으로 남는 것만")
print("\n금액 기록 없음:", R.note.ne("").sum(), "· 20일 거래대금 못 구함:", int((R.p == 1.0).sum()))
print("T6 날별", R[R.rid == "T6"].groupby("d").agg(n=("pnl", "size"), amt=("amt", "sum"), pnl=("pnl", "sum")).round(0).to_dict("index"))
