# -*- coding: utf-8 -*-
"""미장 규칙 보유기간 점검 — 규칙 **각각 단독**으로, 두 기간 모두에서 (2026-09-24).

[저PBR 낙폭](N3)은 이 시험으로 40→60일을 찾았다(n3_tune.py). 같은 시험을 나머지 규칙에도 댄다.
잣대: 폐지 포함 패널(us_full_2007.pkl) · us_surv_measure.py 의 규칙 정의 · 신호 나면 다 산다 · 한 종목 보유 중 재신호 무시.
기간: A 2009~2015(판정에 안 쓴 과거) · B 2016~.
판정(미리 정함): 다른 보유가 **A·B 둘 다** 평균과 승률에서 지금 보유를 이길 때만 '손볼 후보'.
[실적 서프라이즈](N6)는 폐지 종목 실적 자료가 없어 A 를 못 잰다 — B(생존 종목)만 참고로.

    python hold_sweep_us.py
"""
import sys, io, contextlib, warnings
warnings.filterwarnings("ignore")
sys.argv = [sys.argv[0], "--panel", "us_full_2007.pkl", "--since", "20090101"]
_buf = io.StringIO()
with contextlib.redirect_stdout(_buf):
    import us_surv_measure as M
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd

K = M.K
C = M.rules(pd.Series(True, index=K.index), "u_all")
NAME = M.NAME
NOW = dict(M.HOLD)
TRY = {"N1": (20, 40, 60), "N2": (10, 20, 40), "N3": (20, 40, 60), "N4": (20, 40, 60), "N5": (20, 40, 60)}


def dedup(cond, h):
    Z = K[cond].dropna(subset=[f"n{h}"])
    Z = Z[Z.buy > 0].sort_values("di")
    keep, last = [], {}
    for t, i, ix in zip(Z.ticker.values, Z.di.values, Z.index):
        if last.get(t, -10 ** 9) >= i:
            continue
        last[t] = i + h
        keep.append(ix)
    Z = Z.loc[keep]
    Z = Z[Z.date >= "20090101"].copy()
    Z["r"] = Z[f"n{h}"].astype(float)
    return Z


def st(z):
    r = z.r
    if len(r) < 5:
        return None
    ys = z.groupby(z.date.str[:4]).r.agg(["size", "mean"]); ys = ys[ys["size"] >= 5]
    return dict(n=len(r), avg=r.mean(), med=r.median(), win=(r > 0).mean() * 100,
                trim=r[r <= r.quantile(0.95)].mean(), yp=f"{(ys['mean'] > 0).sum()}/{len(ys)}")


f = lambda s: "—" if s is None else f"{s['n']:,}건 · 평균 {s['avg']:+.2f} · 중앙 {s['med']:+.2f} · 승률 {s['win']:.0f}% · 상위5%뺀 {s['trim']:+.2f} · 양수해 {s['yp']}"
print("\n## 미장 — 보유기간별 건당 성적 (폐지 포함, 규칙 단독)\n")
print("| 규칙 | 보유 | A 2009~15 | B 2016~ |")
print("|---|---|---|---|")
VERD = {}
for rid in ("N1", "N2", "N3", "N4", "N5"):
    R = {}
    for h in TRY[rid]:
        Z = dedup(C[rid], h)
        R[h] = (st(Z[Z.date <= "20151231"]), st(Z[Z.date >= "20160101"]))
        tag = " **(지금)**" if h == NOW[rid] else ""
        print(f"| [{NAME[rid]}] | {h}일{tag} | {f(R[h][0])} | {f(R[h][1])} |")
    a0, b0 = R[NOW[rid]]
    better = [h for h in TRY[rid] if h != NOW[rid] and all(
        x is not None and y is not None and x["avg"] > y["avg"] and x["win"] > y["win"]
        for x, y in ((R[h][0], a0), (R[h][1], b0)))]
    VERD[rid] = better
print("\n## 판정 — 두 기간 모두 평균·승률이 나은 보유\n")
for rid, b in VERD.items():
    print(f"- [{NAME[rid]}] 지금 {NOW[rid]}일 → " + (f"**후보 {b}일**" if b else "그대로"))
