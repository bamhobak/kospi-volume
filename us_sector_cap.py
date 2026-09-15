# -*- coding: utf-8 -*-
"""**'같은 업종 하나까지' 본검증** (2026-09-15).

us_n1_lab 18칸 중 유일하게 자산·낙폭 둘 다 과반을 이긴 칸: [상승장 신고가]에
**업종 상한 1** (자산승 19/30 · 낙폭승 16/30 · 노출 68% 그대로).
공짜로 얻은 개선처럼 보이는데 19/30 은 동전던지기와 크게 다르지 않다(p≈0.10).

그래서 관문을 더 세운다.
  ① 시드 100 — 30 으로는 못 가른다
  ② 학습(2016~22) / 검증(2023~26) 분리 — 한 구간에서만 나는 건 아닌가
  ③ **다른 규칙에도** 걸어 본다 — [상승장 신고가]에서만 되면 우연일 확률이 높고,
     여러 규칙에서 같은 방향이면 '업종 분산' 이라는 원리가 있는 것이다
  ④ 전 규칙 동시 적용 · 업종 상한 2

⚠ 사후 선택이다(18칸을 보고 고름). 통과해도 채택이 아니라 '유망' 이다.

    python us_sector_cap.py
"""
import pickle, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
from pathlib import Path

BASE = Path(__file__).parent
NS = 100
W = 108
NM = {"N1": "상승장 신고가", "N2": "낙폭과대", "N3": "저PBR 낙폭",
      "N4": "자사주 낙폭", "N5": "잔잔한 급등주"}
with open(BASE / "data" / "sector_drop_us_sig.pkl", "rb") as f: C = pickle.load(f)
S0, DS, ADI, PCT0 = C["S"], C["DS"], C["ADI"], C["PCT"]
TK = pd.read_csv(BASE / "data/us/tickers.csv")
SEC = dict(zip(TK.Symbol.astype(str), TK.Industry.astype(str)))
RID = ["N1", "N2", "N3", "N4", "N5"]


def sec(t): print("\n" + "=" * W + f"\n{t}\n" + "=" * W)


def sim(S, ds, seed=None, persec=None, cash_cap=1.0):
    rng = np.random.default_rng(seed) if seed is not None else None
    nav, held, cnt = 1.0, {}, {}
    byd = {d: g for d, g in S[S.date.isin(set(ds))].groupby("date")}
    peak, mdd, inv = 1.0, 0.0, []
    for d in ds:
        di = ADI[d]
        for k in [k for k, v in held.items() if v[0] <= di]:
            nav *= 1 + held.pop(k)[1] / 100; cnt[k[0]] = cnt.get(k[0], 0) - 1
        peak = max(peak, nav); mdd = min(mdd, nav / peak - 1)
        inv.append(sum(PCT0[k[0]] for k in held) / 100)
        g = byd.get(d)
        if g is None: continue
        g = (g.sample(frac=1, random_state=int(rng.integers(1 << 30))) if rng is not None
             else g.sort_values("amt20", ascending=False, na_position="last"))
        for r in g.itertuples():
            if cnt.get(r.rid, 0) >= r.mx: continue
            if persec and r.rid in persec:
                s_ = SEC.get(r.ticker, "?")
                if sum(1 for x in held if x[0] == r.rid and SEC.get(x[1], "?") == s_) >= persec[r.rid]:
                    continue
            k = (r.rid, r.ticker, d)
            if k in held: continue
            if sum(PCT0[x[0]] for x in held) / 100 + r.pct / 100 > cash_cap: continue
            held[k] = (di + int(r.hold), r.ret / 100 * r.pct); cnt[r.rid] = cnt.get(r.rid, 0) + 1
    for v in held.values(): nav *= 1 + v[1] / 100
    return nav, mdd * 100, float(np.mean(inv))


def pair(lbl, persec, ds, ns=NS):
    a = [sim(S0, ds, seed=k) for k in range(ns)]
    b = [sim(S0, ds, seed=k, persec=persec) for k in range(ns)]
    wn = sum(1 for x, y in zip(b, a) if x[0] > y[0])
    wm = sum(1 for x, y in zip(b, a) if x[1] > y[1])
    d0 = sim(S0, ds)[0]; d1 = sim(S0, ds, persec=persec)[0]
    print(f"  {lbl:<28}{d0:>8.2f}배{d1:>9.2f}배"
          f"{np.median([x[0] for x in a]):>10.2f}배{np.median([x[0] for x in b]):>9.2f}배"
          f"{wn:>6}/{ns}{wm:>6}/{ns}")
    return wn, wm


sec(f"① 시드 {NS} — [상승장 신고가]에 업종 상한 (기준 2016~)")
print(f"  {'구성':<28}{'기준(정책)':>11}{'적용(정책)':>11}{'기준 중앙':>11}{'적용 중앙':>11}{'자산승':>9}{'낙폭승':>9}")
pair("[상승장 신고가] 업종 1", {"N1": 1}, DS)
pair("[상승장 신고가] 업종 2", {"N1": 2}, DS)

sec("② 구간 분리 — 학습 2016~22 / 검증 2023~26")
TR = [d for d in DS if d <= "20221231"]
VA = [d for d in DS if d >= "20230101"]
print(f"  {'구간':<28}{'기준(정책)':>11}{'적용(정책)':>11}{'기준 중앙':>11}{'적용 중앙':>11}{'자산승':>9}{'낙폭승':>9}")
for lbl, ds in (("학습 2016~22", TR), ("검증 2023~26", VA)):
    pair(lbl, {"N1": 1}, ds, ns=50)

sec("③ 다른 규칙에도 — 원리가 있으면 여러 규칙에서 같은 방향이어야 한다")
print(f"  {'구성':<28}{'기준(정책)':>11}{'적용(정책)':>11}{'기준 중앙':>11}{'적용 중앙':>11}{'자산승':>9}{'낙폭승':>9}")
res = {}
for r in RID:
    res[r] = pair(f"[{NM[r]}] 업종 1", {r: 1}, DS, ns=50)
ok = sum(1 for r in RID if res[r][0] > 25)
print(f"\n  5규칙 중 자산 과반승 {ok}개 — 하나뿐이면 우연, 여럿이면 원리다")

sec("④ 전 규칙 동시 적용")
print(f"  {'구성':<28}{'기준(정책)':>11}{'적용(정책)':>11}{'기준 중앙':>11}{'적용 중앙':>11}{'자산승':>9}{'낙폭승':>9}")
pair("전 규칙 업종 1", {r: 1 for r in RID}, DS)
pair("전 규칙 업종 2", {r: 2 for r in RID}, DS)
