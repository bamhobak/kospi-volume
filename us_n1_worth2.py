# -*- coding: utf-8 -*-
"""**[상승장 신고가]가 제 몫을 하나** (2026-09-15).

물음: "승률 55% · PF 1.15 · 건당 +1.79% 면 메리트가 별로 없는데, 월 57건이나 나고
       비중은 10/4(최대 40)라 미장 노출의 40%를 이 규칙이 쓴다."

맞는 문제 제기다. 다만 **총기여가 낮다고 빼면 안 된다** — 빼면 그 자리가 다른 규칙에
가는지, 아니면 그냥 비는지가 계좌를 가른다. 그래서 계좌로 잰다.

  ① 규칙별 성격 — 이 규칙만 상승장 게이트(usUp60)다. 빼면 상승장에 살 게 남나?
  ② 계좌 — 그대로 / 제외 / 비중 절반 / 자리 절반 · 랜덤 30시드 짝비교
  ③ 경로분포 — 낙폭 꼬리와 언더워터가 어떻게 바뀌나
  ④ 노출을 맞춘 비교 — 뺀 만큼 나머지를 키우면 어떤가

    python us_n1_worth2.py
"""
import pickle, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
from pathlib import Path
from verdict import block_paths

BASE = Path(__file__).parent
NS = 30
W = 104
NM = {"N1": "상승장 신고가", "N2": "낙폭과대", "N3": "저PBR 낙폭",
      "N4": "자사주 낙폭", "N5": "잔잔한 급등주"}
with open(BASE / "data" / "sector_drop_us_sig.pkl", "rb") as f: C = pickle.load(f)
S0, DS, ADI, PCT0 = C["S"], C["DS"], C["ADI"], C["PCT"]


def sec(t): print("\n" + "=" * W + f"\n{t}\n" + "=" * W)


def sim(S, PCT, ds, scale=1.0, seed=None, cash_cap=1.0, curve=False):
    rng = np.random.default_rng(seed) if seed is not None else None
    nav, held, cnt = 1.0, {}, {}
    byd = {d: g for d, g in S[S.date.isin(set(ds))].groupby("date")}
    peak, mdd, inv, cv, log = 1.0, 0.0, [], [], []
    for d in ds:
        di = ADI[d]
        for k in [k for k, v in held.items() if v[0] <= di]:
            nav *= 1 + held.pop(k)[1] / 100; cnt[k[0]] = cnt.get(k[0], 0) - 1
        peak = max(peak, nav); mdd = min(mdd, nav / peak - 1)
        inv.append(sum(PCT[k[0]] * scale for k in held) / 100)
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
            log.append((r.rid, r.ret, r.pct * scale))
    for v in held.values(): nav *= 1 + v[1] / 100
    return (nav, mdd * 100, float(np.mean(inv)), pd.DataFrame(log, columns=["rid", "ret", "amt"]),
            pd.DataFrame(cv, columns=["date", "nav"]) if curve else None)


sec("① 규칙별 성격 — 이 규칙만 상승장 게이트다")
print(f"  {'규칙':<16}{'신호':>8}{'비중':>6}{'자리':>5}{'최대노출':>9}{'평균%':>9}{'중앙%':>9}{'승률':>7}")
for r in ["N1", "N2", "N3", "N4", "N5"]:
    z = S0[S0.rid == r]
    print(f"  {NM[r]:<16}{len(z):>8,}{PCT0[r]:>6}{int(z.mx.iloc[0]):>5}"
          f"{PCT0[r]*int(z.mx.iloc[0]):>8}%{z.ret.mean():>+9.2f}{z.ret.median():>+9.2f}{(z.ret>0).mean():>7.0%}")
tot = sum(PCT0[r] * int(S0[S0.rid == r].mx.iloc[0]) for r in PCT0)
n1 = PCT0["N1"] * int(S0[S0.rid == "N1"].mx.iloc[0])
print(f"\n  미장 최대 노출 {tot}% 중 [상승장 신고가]가 {n1}% ({n1/tot:.0%})")
base, _, _, L0, _ = sim(S0, PCT0, DS)
print(f"\n  {'규칙':<16}{'체결':>7}{'평균%':>9}{'승률':>7}{'총기여(계좌%p)':>16}")
for r in ["N1", "N2", "N3", "N4", "N5"]:
    z = L0[L0.rid == r]
    if not len(z): continue
    print(f"  {NM[r]:<16}{len(z):>7,}{z.ret.mean():>+9.2f}{(z.ret>0).mean():>7.0%}"
          f"{(z.amt*z.ret/100).sum()*100:>15.1f}")

sec("② 계좌 — 그대로 / 제외 / 비중 줄이기 / 자리 줄이기")
CFG = [("지금 그대로", None, None, None),
       ("[상승장 신고가] 제외", "drop", None, None),
       ("비중 10→7", "pct", 7, None),
       ("비중 10→5", "pct", 5, None),
       ("비중 10→3", "pct", 3, None),
       ("자리 4→2", "mx", None, 2),
       ("자리 4→6", "mx", None, 6),
       ("비중 5 · 자리 6", "both", 5, 6)]


def make(kind, pct, mx):
    S, P = S0.copy(), dict(PCT0)
    if kind == "drop":
        return S[S.rid != "N1"].reset_index(drop=True), {k: v for k, v in P.items() if k != "N1"}
    if kind in ("pct", "both"):
        S.loc[S.rid == "N1", "pct"] = pct; P["N1"] = pct
    if kind in ("mx", "both"):
        S.loc[S.rid == "N1", "mx"] = mx
    return S, P


print(f"  {'구성':<22}{'노출':>7}{'자산':>10}{'낙폭':>9}   랜덤 30시드 {'중앙':>9}{'최악':>9}{'자산승':>8}{'낙폭승':>8}")
b30 = [sim(S0, PCT0, DS, seed=k)[:2] for k in range(NS)]
KEEP = {}
for lbl, kind, pct, mx in CFG:
    S, P = (S0, PCT0) if kind is None else make(kind, pct, mx)
    KEEP[lbl] = (S, P)
    nav, mdd, ex, _, _ = sim(S, P, DS)
    r30 = [sim(S, P, DS, seed=k)[:2] for k in range(NS)]
    wn = sum(1 for a, b in zip(r30, b30) if a[0] > b[0])
    wm = sum(1 for a, b in zip(r30, b30) if a[1] > b[1])
    print(f"  {lbl:<22}{ex*100:>6.0f}%{nav:>9.2f}배{mdd:>8.1f}%"
          f"              {np.median([x[0] for x in r30]):>8.2f}배{min(x[0] for x in r30):>8.2f}배"
          f"{wn:>6}/30{wm:>6}/30")

sec("③ 경로분포 — 5,000경로")
print(f"  {'구성':<22}{'낙폭중앙':>10}{'하위5%':>9}{'하위1%':>9}{'언더워터 중앙/하위5%':>22}{'자산중앙':>10}{'자산하위5%':>12}")
for lbl in ("지금 그대로", "[상승장 신고가] 제외", "비중 10→5", "자리 4→2"):
    S, P = KEEP[lbl]
    _, _, _, _, cv = sim(S, P, DS, curve=True)
    m = cv.assign(ym=cv.date.str[:6]).groupby("ym").nav.last().pct_change().dropna() * 100
    Pt = block_paths(m, n_paths=5000, mean_block=3)
    print(f"  {lbl:<22}{Pt.mdd.median():>9.1f}%{np.percentile(Pt.mdd,5):>8.1f}%"
          f"{np.percentile(Pt.mdd,1):>8.1f}%{Pt.under.median()/12:>12.1f}년"
          f"{np.percentile(Pt.under,95)/12:>9.1f}년{Pt.nav.median():>9.2f}배{np.percentile(Pt.nav,5):>11.2f}배")

sec("④ 노출을 맞춰 견주기 — 뺀 만큼 나머지를 키우면")
tgt = sim(S0, PCT0, DS)[2] * 100
print(f"  기준 노출 {tgt:.0f}% 에 맞춘다")
print(f"  {'구성':<22}{'배율':>7}{'노출':>7}{'중앙':>10}{'자산승':>8}{'낙폭승':>8}")
for lbl in ("지금 그대로", "[상승장 신고가] 제외", "비중 10→5", "자리 4→2"):
    S, P = KEEP[lbl]
    lo, hi = 0.5, 4.0
    for _ in range(14):
        mid = (lo + hi) / 2
        if sim(S, P, DS, scale=mid)[2] * 100 < tgt: lo = mid
        else: hi = mid
    sc = (lo + hi) / 2
    r30 = [sim(S, P, DS, scale=sc, seed=k)[:3] for k in range(NS)]
    wn = sum(1 for a, b in zip(r30, b30) if a[0] > b[0])
    wm = sum(1 for a, b in zip(r30, b30) if a[1] > b[1])
    print(f"  {lbl:<22}{sc:>7.2f}{np.mean([x[2] for x in r30])*100:>6.0f}%"
          f"{np.median([x[0] for x in r30]):>9.2f}배{wn:>6}/30{wm:>6}/30")
