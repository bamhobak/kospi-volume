# -*- coding: utf-8 -*-
"""T1 예상가 오차 — 실측 오차 모양으로 다시 (2026-10-11).

gap_noise.py 는 오차를 모든 종목에 서로 무관하게(라플라스) 넣어 너무 비관적이었다(예상 꼬리에 오차만 큰 종목이 몰림).
데이 스냅샷 3일치(10-06~08, 980종목/일)를 실제 09:01 시가와 맞대 보니 오차는 실제 갭과 음의 상관(-0.3, 큰 갭을 덜 크게 예상)
→ 예상(시장 대비) = a + s × 실제(시장 대비) + 잔차(실측 잔차를 유동성 아래/위로 나눠 다시 뽑기) 로 흉내 낸다.
그리고 C(지정가): 예상으로 고른 후보에 '조건 문턱 가격' 지정가를 넣어, 실제 시가가 문턱 아래일 때만 체결.
    python research/gap_noise2.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / "factory"))
import numpy as np, pandas as pd
import lab, feats as FT, common as C

E = pd.read_pickle(C.CACHE / "gap_err_3d.pkl")
fit = {}
for k, g in E.groupby("tiny"):
    s, a = np.polyfit(g.rr, g.rx, 1)
    fit[k] = (a, s, (g.rx - (a + s * g.rr)).values)
    print("오차 모형 %s: 예상 = %+.2f + %.2f × 실제 + 잔차(평균절대 %.2f, 중앙 %.2f, n %d)" % (
        "유동성 아래" if k else "유동성 위", a, s, np.abs(fit[k][2]).mean(), np.median(np.abs(fit[k][2])), len(g)))

U = lab.hist()
U = U[U.oc.notna() & U.gap.notna()][["ticker", "date", "gap", "q_vm", "liq", "oc", "rgap"]].reset_index(drop=True)
U["ret"] = U.oc.astype(float).clip(-60, 60) - FT.COST
TR, VA = lab.TR, lab.VA
dcode = pd.factorize(U.date)[0]
tiny = (U.liq <= 1 / 3).values


def pick(rel, thr=-2.0):
    q = pd.Series(rel).groupby(dcode).rank(pct=True).values
    return (q <= 0.10) & (U.q_vm.values <= 0.30) & tiny & (rel <= thr)


def st(m):
    out = []
    for a, b in (TR, VA):
        s = lab.stats(U[m & (U.date >= a) & (U.date <= b)])
        out.append((s["n"], s["mean"], s["win"], s["t"]) if s else (0, np.nan, np.nan, np.nan))
    return out


real = U.rgap.values
base = pick(real)
print("\n오차 없음(연구 T1)                     | 학습 %5d %+5.2f %4.1f%% t%4.1f | 검증 %5d %+5.2f %4.1f%% t%4.1f" % tuple(x for o in st(base) for x in o))
rng = np.random.default_rng(11)


def sim():
    x = np.empty(len(U))
    for k in (False, True):
        a, s, res = fit[k]
        m = tiny == k
        x[m] = a + s * real[m] + rng.choice(res, m.sum())
    return x


variants = [("예상으로 고름 · 시장가(지금)", -2.0, None), ("예상 -2.5 로 고름 · 시장가", -2.5, None),
            ("C 예상 -2 로 고름 · 지정가 = 문턱 -2", -2.0, -2.0), ("C 예상 -1.5 로 고름 · 지정가 = 문턱 -2", -1.5, -2.0),
            ("C 예상 -1 로 고름 · 지정가 = 문턱 -2", -1.0, -2.0), ("C 예상 -2 로 고름 · 지정가 = 문턱 -1.5", -2.0, -1.5)]
for nm, thr, lim in variants:
    R = []
    for k in range(20):
        x = sim()
        m = pick(x, thr)
        if lim is not None: m = m & (real <= lim)                    # 실제 시가(시장 대비)가 문턱 아래일 때만 체결
        R.append([v for o in st(m) for v in o] + [(m & base).sum() / max(base.sum(), 1) * 100])
    mu = np.array(R).mean(0); R = np.array(R)
    print("%-38s | 학습 %5d %+5.2f %4.1f%% t%4.1f | 검증 %5d %+5.2f %4.1f%% t%4.1f | 연구 T1 중 잡은 비율 %.0f%% · 검증 평균 범위 %+.2f~%+.2f" % (
        nm, *mu[:8], mu[8], R[:, 5].min(), R[:, 5].max()), flush=True)
