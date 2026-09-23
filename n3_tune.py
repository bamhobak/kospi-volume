# -*- coding: utf-8 -*-
"""미장 [저PBR 낙폭](N3) 조정안 — 2009~2015 과거 검증 실패의 원인과 고칠 방향 (2026-09-24).

2009~2015(폐지 포함) 평균 -4.20%·승률 43%(272건)로 실패했다. 2016~ 은 +12.06%.
실패가 2014~15 에 몰려 있다(-9.5% · -9.9%) — 원자재 폭락기다. 싸 보이는 에너지·광산주가 계속 빠지는
'가치 함정' 이 의심된다. 그래서 **이유가 있는 조정만** 몇 개 미리 정해 놓고 재본다(격자 탐색 금지 — 과적합).

판정: 두 기간(A 2009~15 · B 2016~) **모두** 원안보다 평균·승률이 나아지고, B 를 크게 깎지 않을 것.
잣대: 폐지 포함 패널(us_full_2007.pkl) · 신호 나면 다 산다 · 보유일은 원안 40일(보유 조정안만 다름).

    python n3_tune.py
"""
import sys, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
import FinanceDataReader as fdr

BASE = Path(__file__).parent
K = pd.read_pickle(BASE / "data" / "us_full_2007.pkl")
K = K.sort_values(["ticker", "date"]).reset_index(drop=True)
K["u"] = K.groupby(["date", "sic2"]).ret60.transform("median")      # 폐지 포함 전체로(us_surv_measure 와 같다)
K = K[K.rawclose >= 3].copy()
ud = sorted(K.date.unique()); ADI = {d: i for i, d in enumerate(ud)}
K["di"] = K.date.map(ADI).astype(np.int32)

IX = fdr.DataReader("US500", "2004-06-01"); IX = IX[IX.Close > 0].copy()
IX["date"] = IX.index.strftime("%Y%m%d"); IX["ma60"] = IX.Close.rolling(60).mean()
IX["r20"] = (IX.Close / IX.Close.shift(20) - 1) * 100
DN = K.date.map(dict(zip(IX.date, IX.Close < IX.ma60))).fillna(False)
SPR20 = K.date.map(dict(zip(IX.date, IX.r20)))

uni = (K.amt20 >= 2)
K["cap_q"] = K.marcap.where(uni).groupby(K.date).rank(pct=True)
ENERGY = {"10", "12", "13", "14", "29"}           # 금속광업·석탄·원유가스·비금속광물·석유정제

BASEC = (DN & (K.PBR > 0) & (K.PBR <= 0.8) & (K.ret20 <= -10) & (K.su1 >= 2) & (K.u <= -10) & uni).fillna(False)
V = {
    "원안": (BASEC, 40),
    "① 에너지·광산 빼기": (BASEC & ~K.sic2.isin(ENERGY), 40),
    "② 흑자 기업만(최근 순이익>0)": (BASEC & (K.ni_pos == 1), 40),
    "③ 부채비율 ≤200%": (BASEC & (K["부채비율"] <= 200), 40),
    "④ 시총 같은 날 상위 절반": (BASEC & (K.cap_q >= 0.5), 40),
    "⑤ PBR ≤0.6(더 싸게)": (BASEC & (K.PBR <= 0.6), 40),
    "⑥ 업종 60일 ≤-20%(더 깊은 업종 폭락)": (BASEC & (K.u <= -20), 40),
    "⑦ S&P 20일 ≤-5%(진짜 폭락장만)": (BASEC & (SPR20 <= -5), 40),
    "⑧ 보유 20일": (BASEC, 20),
    "②+④ 흑자·큰 종목": (BASEC & (K.ni_pos == 1) & (K.cap_q >= 0.5), 40),
    "①+② 에너지 빼고 흑자": (BASEC & ~K.sic2.isin(ENERGY) & (K.ni_pos == 1), 40),
}


def dedup(cond, h):
    Z = K[cond.values].dropna(subset=[f"n{h}"])
    Z = Z[Z.buy > 0].sort_values("di")
    keep, last = [], {}
    for t, i, ix in zip(Z.ticker.values, Z.di.values, Z.index):
        if last.get(t, -10 ** 9) >= i:
            continue
        last[t] = i + h
        keep.append(ix)
    Z = Z.loc[keep].copy()
    Z["r"] = Z[f"n{h}"].astype(float)
    return Z[Z.date >= "20090101"]


def st(z):
    r = z.r
    if len(r) < 5:
        return None
    ys = z.groupby(z.date.str[:4]).r.agg(["size", "mean"])
    ys = ys[ys["size"] >= 5]
    return dict(n=len(r), avg=r.mean(), win=(r > 0).mean() * 100, trim=r[r <= r.quantile(0.95)].mean(),
                worst=r.min(), ypos=f"{(ys['mean'] > 0).sum()}/{len(ys)}", dead=(z.grp == "폐지").mean() * 100)


# ── 진단: 원안 거래를 업종별로 ────────────────────────────────────────
Z0 = dedup(*V["원안"])
Z0["기간"] = np.where(Z0.date <= "20151231", "A 2009~15", "B 2016~")
print("## 진단 — 원안 거래, 업종(SIC 2자리)별 (건수 10↑)\n")
g = Z0.groupby(["sic2", "기간"]).r.agg(["size", "mean"]).unstack()
g = g[(g[("size", "A 2009~15")].fillna(0) + g[("size", "B 2016~")].fillna(0)) >= 10]
print("| SIC | A 건수 | A 평균 | B 건수 | B 평균 |\n|---|---|---|---|---|")
for s, r in g.sort_values(("size", "A 2009~15"), ascending=False).iterrows():
    tag = " (에너지·광산)" if s in ENERGY else ""
    print(f"| {s}{tag} | {r[('size','A 2009~15')]:.0f} | {r[('mean','A 2009~15')]:+.1f}% | "
          f"{r[('size','B 2016~')]:.0f} | {r[('mean','B 2016~')]:+.1f}% |")

print("\n## 조정안 — A 2009~2015 / B 2016~ (폐지 포함 · 신호 나면 다 산다)\n")
print("| 안 | A 건수 | A 평균 | A 승률 | A 상위5%뺀 | B 건수 | B 평균 | B 승률 | B 상위5%뺀 | 양수 해(A+B) |")
print("|---|---|---|---|---|---|---|---|---|---|")
for nm, (c, h) in V.items():
    Z = dedup(c, h)
    a = st(Z[Z.date <= "20151231"]); b = st(Z[Z.date > "20151231"])
    if not a or not b:
        print(f"| {nm} | 건수 부족 |"); continue
    ya = Z.groupby(Z.date.str[:4]).r.agg(["size", "mean"]); ya = ya[ya["size"] >= 5]
    print(f"| {nm} | {a['n']} | {a['avg']:+.2f}% | {a['win']:.0f}% | {a['trim']:+.2f}% | "
          f"{b['n']} | {b['avg']:+.2f}% | {b['win']:.0f}% | {b['trim']:+.2f}% | {(ya['mean']>0).sum()}/{len(ya)} |")

# ── 후속(미리 정한 6칸): 보유 20·40·60 × 부채비율 조건 유무 ────────────────────
print("\n## 후속 — 보유 20·40·60일 × 부채비율 ≤200% (6칸만)\n")
print("| 안 | A 건수 | A 평균 | A 승률 | B 건수 | B 평균 | B 승률 | A 연도별(2009~15) |")
print("|---|---|---|---|---|---|---|---|")
DEBT = BASEC & (K["부채비율"] <= 200)
for nm, c in (("원안 조건", BASEC), ("+부채비율≤200", DEBT)):
    for h in (20, 40, 60):              # 패널 선도수익은 5·10·20·40·60일뿐이라 30 대신 60
        Z = dedup(c, h)
        a = st(Z[Z.date <= "20151231"]); b = st(Z[Z.date > "20151231"])
        za = Z[Z.date <= "20151231"]
        yr = " ".join(f"{y[2:]}:{g.mean():+.0f}" for y, g in za.groupby(za.date.str[:4]).r)
        print(f"| {nm} · 보유 {h}일 | {a['n']} | {a['avg']:+.2f}% | {a['win']:.0f}% | {b['n']} | {b['avg']:+.2f}% | {b['win']:.0f}% | {yr} |")

# ── 보유 40 vs 60 — 한 해에 기댄 착시인가 ─────────────────────────────
print("\n## 보유 40일 vs 60일 — 연도별 (원안 조건)\n")
print("| 연도 | 40일 건수 | 40일 평균 | 60일 건수 | 60일 평균 | 60일 중앙 |")
print("|---|---|---|---|---|---|")
Z4, Z6 = dedup(BASEC, 40), dedup(BASEC, 60)
for y in sorted(set(Z4.date.str[:4]) | set(Z6.date.str[:4])):
    a = Z4[Z4.date.str[:4] == y].r; b = Z6[Z6.date.str[:4] == y].r
    print(f"| {y} | {len(a)} | {a.mean():+.1f}% | {len(b)} | {b.mean():+.1f}% | {b.median():+.1f}% |")
print()
for nm, Z in (("40일", Z4), ("60일", Z6)):
    for per, lo, hi in (("A 2009~15", "20090101", "20151231"), ("B 2016~", "20160101", "20991231")):
        z = Z[(Z.date >= lo) & (Z.date <= hi)]
        r = z.r; ys = z.groupby(z.date.str[:4]).r.sum()
        top = ys.max() / ys.sum() * 100 if ys.sum() > 0 else float("nan")
        print(f"- {nm} {per}: 중앙 {r.median():+.2f}% · 상위5% 뺀 {r[r <= r.quantile(.95)].mean():+.2f}% · "
              f"수익 중 가장 큰 해 몫 {top:.0f}% · 2020 빼면 {z[z.date.str[:4] != '2020'].r.mean():+.2f}%")

# ── 시가총액 큰 종목만 (2026-09-24 사용자 요청) — 같은 날 순위로 자른다(금액 문턱은 물가 착시 [[us-cap-axis]]) ──
print("\n## 시가총액 큰 종목만 — 같은 날 미장 전체(거래대금 $2M↑) 대비 시총 순위\n")
print("| 안 | A 건수 | A 평균 | A 승률 | A 상위5%뺀 | B 건수 | B 평균 | B 승률 | B 상위5%뺀 | 시총 모름 |")
print("|---|---|---|---|---|---|---|---|---|---|")
for nm, c in (("원안", BASEC), ("시총 상위 50%", BASEC & (K.cap_q >= 0.5)),
              ("시총 상위 30%", BASEC & (K.cap_q >= 0.7)), ("시총 상위 10%", BASEC & (K.cap_q >= 0.9))):
    Z = dedup(c, 40)
    a = st(Z[Z.date <= "20151231"]); b = st(Z[Z.date > "20151231"])
    miss = Z.cap_q.isna().mean() * 100
    fa = lambda d, k, fmt: (fmt % d[k]) if d else "—"
    print(f"| {nm} | {a['n'] if a else 0} | {fa(a,'avg','%+.2f%%')} | {fa(a,'win','%.0f%%')} | {fa(a,'trim','%+.2f%%')} | "
          f"{b['n'] if b else 0} | {fa(b,'avg','%+.2f%%')} | {fa(b,'win','%.0f%%')} | {fa(b,'trim','%+.2f%%')} | {miss:.0f}% |")
