# -*- coding: utf-8 -*-
"""종목 공포탐욕 문턱 — 규칙 단위 게이트를 통과한 둘을 계좌로 판정한다.

규칙 단위(stock_fg_test.py ③)에서 학습·검증 CI>0 & 중앙>0 & 2026 승 & 기준선 대비 양쪽 개선을
통과한 것은 [업종붕괴 이탈] 점수≤20 · [저PBR 낙폭] 점수≤20 둘뿐이다.
[업종붕괴 이탈] 은 예전에 조이기 20개가 규칙 단위로는 좋아 보였다가 계좌에서 전량 기각된 전례가
있다(자리제한 착시). 그래서 같은 시드로 짝지어 계좌를 재고, 비중 ×0.5/×1.5 로 착시를 거른다.
덤으로 (a) 걸러진 신호들의 성적 — 진짜 패자를 걸렀는지 (b) 2020-03 쏠림이 더 심해지는지 본다.
"""
import io, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
BASE = Path(__file__).parent; SEEDS = 12
src = (BASE/"portfolio.py").read_text(encoding="utf-8"); ns = {"__file__": str(BASE/"portfolio.py")}
real = sys.stdout; sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
exec(compile(src.split("# 신호를 한 표로 모은다")[0], "portfolio.py", "exec"), ns)
sys.stdout = real
KP, KQ, RULES = ns["KP"], ns["KQ"], ns["RULES"]
for mk, K in (("kp", KP), ("kq", KQ)):
    F = pd.read_pickle(BASE/"data"/f"stock_fg_{mk}.pkl")[["ticker","date","fg"]]
    K["fg"] = K.merge(F, on=["ticker","date"], how="left").fg.values
adates = sorted(set(KP.date) | set(KQ.date)); ADI = {d: i for i, d in enumerate(adates)}
rel = (BASE/"rules_relation.py").read_text(encoding="utf-8")
exec(rel[rel.index("def build(R):"):rel.index("S = build(RULES)")], globals())
exec(rel[rel.index("def sim(S, ds, seed):"):rel.index("ds = [d for d in adates")].replace(
     "return dict(nav=Cv.iloc[-1], mdd=dd.min(), byrid=byrid)",
     "return dict(nav=Cv.iloc[-1], mdd=dd.min(), byrid=byrid, curve=Cv)"), globals())
NAME = {"P4":"업종붕괴 이탈","D2":"저PBR 낙폭"}

# (a) 걸러진 신호의 정체 — 규칙 단위 실거래 기준
def trades(K, cond, hold, stop):
    g = K.groupby("ticker", sort=False)
    if stop:
        low = pd.concat([g.low.shift(-i) for i in range(hold)], axis=1).min(axis=1)
        r = np.where((low <= K.buy*(1-stop)).fillna(False), -stop*100-K.cost, K[f"n{hold}"])
    else: r = K[f"n{hold}"].values
    m = cond.fillna(False); X = K[m].copy(); X["_r"] = r[m.values]; X = X.dropna(subset=["_r"])
    di = {x:i for i,x in enumerate(sorted(K.date.unique()))}
    X["di"] = X.date.map(di); X = X.sort_values("di"); keep, last = [], {}
    for t,i,ix in zip(X.ticker.values, X.di.values, X.index):
        if last.get(t,-10**9) >= i: continue
        last[t] = i+hold; keep.append(ix)
    return X.loc[keep]
print("(a) 점수≤20 이 걸러낸 신호들 — 기준선 실거래 중 점수>20 인 것 (2016~)")
for rid in ("P4","D2"):
    K, hold, stop, pct, mx, cond = RULES[rid]
    Z = trades(K, cond, hold, stop); Z = Z[Z.date >= "20160101"]
    out = Z[Z.fg > 20]; keep = Z[Z.fg <= 20]
    print(f"  [{NAME[rid]}] 전체 {len(Z)}건 → 남김 {len(keep)}건(평균 {keep._r.mean():+.1f}%) · 걸러냄 {len(out)}건"
          f"(평균 {out._r.mean():+.1f}% · 중앙 {out._r.median():+.1f}% · 승률 {(out._r>0).mean()*100:.0f}% · 최악 {out._r.min():+.1f}%)")
    y = lambda z: z.date.str[:6].eq("202003").mean()*100
    print(f"      2020-03 비중: 기준선 {y(Z):.0f}% → 문턱 후 {y(keep):.0f}%")

# (b) 계좌 짝 비교
def variant(patch, scale=1.0):
    R = {}
    for rid, (K,h,st,pct,mx,c) in RULES.items():
        c2 = (c & (K.fg <= 20)) if rid in patch else c
        R[rid] = (K,h,st,min(pct*scale, 100.0/mx),mx,c2)
    return build(R)
VAR = [("현행", ()), ("업종붕괴 ≤20", ("P4",)), ("저PBR ≤20", ("D2",)), ("둘 다", ("P4","D2"))]
PER = [("학습 2016~22","20160101","20221231"), ("검증 2023~26","20230101","20991231"), ("기준 2016~","20160101","20991231")]
print("\n(b) 계좌 — 같은 시드 12개 짝 비교 (자산 배수 중앙값 / 최대낙폭 / 현행보다 나은 시드 수)")
print(f"  {'안':<14}" + "".join(f"{p[0]:>26}" for p in PER))
BASE_N = {}; CURVES = {}
for nm, patch in VAR:
    S = variant(patch); row = ""
    for pn, lo, hi in PER:
        ds = [d for d in adates if lo <= d <= hi]
        R = [sim(S, ds, k) for k in range(SEEDS)]
        nav = [r["nav"] for r in R]; mdd = np.median([r["mdd"] for r in R])
        if nm == "현행": BASE_N[pn] = nav; w = "기준"
        else: w = f"{sum(a>b for a,b in zip(nav, BASE_N[pn]))}/{SEEDS}"
        row += f"{np.median(nav):>10.2f}배{mdd:>7.0f}%{w:>8}"
        if pn == "기준 2016~": CURVES[nm] = (ds, R)
    print(f"  {nm:<14}{row}")
print("\n  연도별 계좌 수익률(중앙값) — 기준 2016~")
print(f"  {'해':<6}" + "".join(f"{nm:>14}" for nm, _ in VAR))
for y in [str(v) for v in range(2016, 2027)]:
    row = f"  {y:<6}"
    for nm, _ in VAR:
        ds, R = CURVES[nm]; yrs = np.array([d[:4] for d in ds]); idx = np.where(yrs == y)[0]
        i0, i1 = max(idx[0]-1, 0), idx[-1]
        row += f"{np.median([(r['curve'].to_numpy()[i1]/r['curve'].to_numpy()[i0]-1)*100 for r in R]):>+13.1f}%"
    print(row)
print("\n(c) 비중 배율을 바꿔도 순서가 유지되나 (기준 2016~ · 둘 다 적용안)")
for sc in (0.5, 1.5):
    ds = [d for d in adates if d >= "20160101"]
    A = [sim(variant((), sc), ds, k)["nav"] for k in range(SEEDS)]
    B = [sim(variant(("P4","D2"), sc), ds, k)["nav"] for k in range(SEEDS)]
    print(f"  x{sc}: 현행 {np.median(A):.2f}배 → 둘 다 {np.median(B):.2f}배 · 나은 시드 {sum(b>a for a,b in zip(A,B))}/{SEEDS}")
