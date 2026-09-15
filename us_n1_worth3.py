# -*- coding: utf-8 -*-
"""**'누적 기여' 는 비중이 큰 쪽에 유리한 눈금이다** (2026-09-15).

지적: "[상승장 신고가]가 누적 기여 2위인 건 네가 비중을 10으로 크게 줘서 그런 것 아니냐."
맞다. 기여 = 비중 × 수익률 × 건수 라서 비중이 2배면 기여도 2배가 된다.
**점유한 노출로 나눠야** 공정하고, 가장 공정한 것은 **같은 노출에서 단독으로 돌려 보는 것**이다.

  ① 규칙별 **실측 점유 노출** — 시뮬을 돌며 매일 그 규칙이 깔고 있던 비중을 적는다
  ② **노출 1%당 기여** — 자본 효율
  ③ **단독 계좌** — 규칙 하나만으로 돌리고 배율로 노출을 같게 맞춰 견준다. 여기가 결론이다

    python us_n1_worth3.py
"""
import pickle, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
from pathlib import Path
from verdict import block_paths

BASE = Path(__file__).parent
NS = 30
W = 108
NM = {"N1": "상승장 신고가", "N2": "낙폭과대", "N3": "저PBR 낙폭",
      "N4": "자사주 낙폭", "N5": "잔잔한 급등주"}
with open(BASE / "data" / "sector_drop_us_sig.pkl", "rb") as f: C = pickle.load(f)
S0, DS, ADI, PCT0 = C["S"], C["DS"], C["ADI"], C["PCT"]
RID = ["N1", "N2", "N3", "N4", "N5"]


def sec(t): print("\n" + "=" * W + f"\n{t}\n" + "=" * W)


def sim(S, PCT, ds, scale=1.0, seed=None, cash_cap=1.0, curve=False, byrule=False):
    rng = np.random.default_rng(seed) if seed is not None else None
    nav, held, cnt = 1.0, {}, {}
    byd = {d: g for d, g in S[S.date.isin(set(ds))].groupby("date")}
    peak, mdd, inv, cv, log = 1.0, 0.0, [], [], []
    expo_r = {r: 0.0 for r in PCT}                 # 규칙별 '점유 노출 × 일수' 누적
    for d in ds:
        di = ADI[d]
        for k in [k for k, v in held.items() if v[0] <= di]:
            nav *= 1 + held.pop(k)[1] / 100; cnt[k[0]] = cnt.get(k[0], 0) - 1
        peak = max(peak, nav); mdd = min(mdd, nav / peak - 1)
        inv.append(sum(PCT[k[0]] * scale for k in held) / 100)
        if byrule:
            for k in held: expo_r[k[0]] += PCT[k[0]] * scale
        if curve: cv.append((d, nav))
        g = byd.get(d)
        if g is None: continue
        g = (g.sample(frac=1, random_state=int(rng.integers(1 << 30))) if rng is not None
             else g.sort_values("amt20", ascending=False, na_position="last"))
        for r in g.itertuples():
            if cnt.get(r.rid, 0) >= r.mx: continue
            k = (r.rid, r.ticker, d)
            if k in held: continue
            if sum(PCT[x[0]] * scale for x in held) / 100 + r.pct * scale / 100 > cash_cap: continue
            held[k] = (di + int(r.hold), r.ret * r.pct * scale / 100)
            cnt[r.rid] = cnt.get(r.rid, 0) + 1
            log.append((r.rid, r.ret, r.pct * scale / 100))     # amt 는 '계좌 대비 비율'
    for v in held.values(): nav *= 1 + v[1] / 100
    return dict(nav=nav, mdd=mdd * 100, expo=float(np.mean(inv)),
                L=pd.DataFrame(log, columns=["rid", "ret", "amt"]),
                cv=pd.DataFrame(cv, columns=["date", "nav"]) if curve else None,
                expo_r={r: v / len(ds) for r, v in expo_r.items()})


R = sim(S0, PCT0, DS, byrule=True)
sec("① 규칙별 실측 점유 노출 — 매일 그 규칙이 깔고 있던 비중의 평균")
print(f"  {'규칙':<16}{'비중':>5}{'자리':>5}{'체결':>7}{'평균%':>9}{'승률':>7}"
      f"{'점유 노출':>11}{'노출 몫':>9}{'기여%p':>10}{'노출1%당':>10}")
tot_e = sum(R["expo_r"].values())
rows = []
for r in RID:
    z = R["L"][R["L"].rid == r]
    e = R["expo_r"][r]
    con = (z.amt * z.ret / 100).sum() * 100
    rows.append((r, e, con))
    print(f"  {NM[r]:<16}{PCT0[r]:>5}{int(S0[S0.rid==r].mx.iloc[0]):>5}{len(z):>7,}"
          f"{z.ret.mean():>+9.2f}{(z.ret>0).mean():>7.0%}{e:>10.1f}%{e/tot_e:>8.0%}"
          f"{con:>+10.1f}{con/max(e,0.01):>10.2f}")
print(f"\n  ※ '노출1%당' = 기여 ÷ 점유 노출. 비중이 큰 규칙이 유리해지는 눈금을 지운 값이다.")

sec("② 단독 계좌 — 규칙 하나만으로 돌리고 **노출을 같게 맞춰** 견준다 (가장 공정한 비교)")
TGT = 20.0
print(f"  각 규칙만으로 계좌를 돌린 뒤, 배율을 조절해 평균 노출을 {TGT:.0f}% 로 맞춘다.")
print(f"  같은 돈을 이 규칙 하나에만 썼다면 어떻게 됐나 — 비중 설정이 만드는 착시가 사라진다.\n")
print(f"  {'규칙':<16}{'배율':>7}{'노출':>7}{'자산':>10}{'낙폭':>9}"
      f"{'30시드 중앙':>12}{'낙폭 하위1%':>12}{'언더워터 하위5%':>15}")
solo = {}
for r in RID:
    S = S0[S0.rid == r].reset_index(drop=True)
    P = {r: PCT0[r]}
    lo, hi = 0.05, 20.0
    for _ in range(18):
        mid = (lo + hi) / 2
        if sim(S, P, DS, scale=mid)["expo"] * 100 < TGT: lo = mid
        else: hi = mid
    sc = (lo + hi) / 2
    a = sim(S, P, DS, scale=sc, curve=True)
    m = a["cv"].assign(ym=a["cv"].date.str[:6]).groupby("ym").nav.last().pct_change().dropna() * 100
    Pt = block_paths(m, n_paths=5000, mean_block=3)
    s30 = [sim(S, P, DS, scale=sc, seed=k)["nav"] for k in range(NS)]
    solo[r] = (sc, a, Pt)
    print(f"  {NM[r]:<16}{sc:>7.2f}{a['expo']*100:>6.0f}%{a['nav']:>9.2f}배{a['mdd']:>8.1f}%"
          f"{np.median(s30):>11.2f}배{np.percentile(Pt.mdd,1):>11.1f}%{np.percentile(Pt.under,95)/12:>13.1f}년")

sec("③ 그래서 — 같은 노출을 줬을 때 순위")
order = sorted(RID, key=lambda r: -solo[r][1]["nav"])
print(f"  {'순위':<5}{'규칙':<16}{'자산(노출 20%)':>16}{'낙폭':>9}{'낙폭 하위1%':>13}")
for i, r in enumerate(order, 1):
    a, Pt = solo[r][1], solo[r][2]
    print(f"  {i:<5}{NM[r]:<16}{a['nav']:>15.2f}배{a['mdd']:>8.1f}%{np.percentile(Pt.mdd,1):>12.1f}%")
