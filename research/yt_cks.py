# -*- coding: utf-8 -*-
"""유튜브 '볼린저밴드와 비슷하게 생긴 강력한 지표 CKS'(코인 콜로세움 ML9Y2AWbrW4 · 2026-10-16 사용자 링크) 실측 — H0348.

CKS = Chande Kroll Stop(p=10, x=1, q=9): 지지 = 최고(최근 10 고가 − ATR10, 9) · 저항 = 최저(최근 10 저가 + ATR10, 9).
상태: 종가가 두 선 위 → 초록(상승) · 두 선 아래 → 빨강(하락) · 사이는 그대로.
영상 전략(롱만): 초록 상태에서 캔들이 20일 돈치안 중앙선 아래로 꼬리를 찍고 중앙선 위 마감 → 매수(다음 시가)
                 빨강 상태에서 중앙선 위로 꼬리를 찍고 아래 마감 → 매도(다음 시가).
비교: B 돈치안 중앙선 눌림만(CKS 상태 무시) · C CKS 상태만(초록 전환 매수 · 빨강 전환 매도).
대상: 비트코인·지수 4개(계좌 곡선 vs 보유) · 국장 kr_scan 2005~ · 미장 us_scan_full 2011~ 종목(첫 매수 유니버스 = 거래대금 상위 40%).
잣대(종목): 거래당 비용 뒤 평균·중앙·승률·보유일 · 돈-날 연환산(손익 ÷ 보유일 × 250) vs 그 기간 유니버스 보유 연환산.
비용: BTC 0.1%×2 · 지수 0.1 · 국장 0.33 · 미장 0.25. 구간 옛날 ~15 · 학습 16~22 · 검증 23~.
    python research/yt_cks.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np, pandas as pd
from numba import njit
import FinanceDataReader as fdr

OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))


@njit(cache=True)
def signals(o, h, l, c, mode):
    """mode 0 영상(CKS+돈치안) · 1 돈치안만 · 2 CKS 상태만. 반환 (진입 idx, 청산 idx) 목록 — 다음날 시가 체결."""
    n = len(c)
    tr = np.empty(n); tr[0] = h[0] - l[0]
    for i in range(1, n): tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
    atr = np.empty(n); atr[0] = tr[0]
    for i in range(1, n): atr[i] = atr[i - 1] + (tr[i] - atr[i - 1]) / 10.0
    fhs = np.full(n, np.nan); fls = np.full(n, np.nan)
    for i in range(9, n):
        fhs[i] = h[i - 9:i + 1].max() - atr[i]; fls[i] = l[i - 9:i + 1].min() + atr[i]
    sup = np.full(n, np.nan); res = np.full(n, np.nan)
    for i in range(17, n):
        sup[i] = fhs[i - 8:i + 1].max(); res[i] = fls[i - 8:i + 1].min()
    mid = np.full(n, np.nan)
    for i in range(19, n): mid[i] = (h[i - 19:i + 1].max() + l[i - 19:i + 1].min()) / 2
    st = 0; pos = -1; out = []
    for i in range(20, n - 1):
        a, b = max(sup[i], res[i]), min(sup[i], res[i])
        prev = st
        if c[i] > a: st = 1
        elif c[i] < b: st = -1
        buy_px = l[i] < mid[i] and c[i] > mid[i]
        sell_px = h[i] > mid[i] and c[i] < mid[i]
        if mode == 0:
            ent = st == 1 and buy_px; ex = st == -1 and sell_px
        elif mode == 1:
            ent = buy_px; ex = sell_px
        else:
            ent = st == 1 and prev != 1; ex = st == -1 and prev != -1
        if pos < 0 and ent: pos = i + 1
        elif pos >= 0 and ex:
            out.append((pos, i + 1)); pos = -1
    if pos >= 0: out.append((pos, n - 1))
    return out


MODES = [(0, "영상(CKS 초록+중앙선 눌림)"), (1, "중앙선 눌림만"), (2, "CKS 추세 전환만")]


def curve(X, cost):
    o, h, l, c = (X[k].to_numpy(np.float64) for k in ("Open", "High", "Low", "Close"))
    res = {}
    for m, nm in MODES:
        eq = np.ones(len(c)); r = np.zeros(len(c))
        last = len(c) - 1
        for a, b in signals(o, h, l, c, m):
            # a 시가 매수 → b 시가 매도(b 가 마지막 날이면 종가). 날마다 수익을 그날에 붙인다.
            if b <= a: continue
            r[a] += c[a] / o[a] - 1
            for k in range(a + 1, b): r[k] += c[k] / c[k - 1] - 1
            r[b] += (c[b] if b == last else o[b]) / c[b - 1] - 1
            r[a] -= cost / 100; r[b] -= cost / 100
        res[nm] = pd.Series(r, index=X.index)
    res["보유"] = X.Close.pct_change().fillna(0)
    return res


def stat(r):
    eq = (1 + r).cumprod(); yrs = len(r) / (365 if r.index.dayofweek.max() == 6 else 252)
    return eq.iloc[-1], eq.iloc[-1] ** (1 / max(yrs, 1e-9)) - 1, (eq / eq.cummax() - 1).min()


def assets():
    P("## 비트코인·지수 — 계좌 곡선(전부 넣었다 뺐다) vs 보유")
    for nm, code, since, cost in (("비트코인", "BTC/USD", "2015-01-01", 0.1), ("코스피", "KS11", "2000-01-01", 0.1), ("코스닥", "KQ11", "2000-01-01", 0.1),
                                  ("S&P500", "US500", "2000-01-01", 0.1), ("나스닥", "IXIC", "2000-01-01", 0.1)):
        X = fdr.DataReader(code, since)[["Open", "High", "Low", "Close"]].dropna()
        X = X[(X.Close > 0) & (X.Open > 0)]
        R = curve(X, cost)
        pers = [("영상 기간 2024-01-11~", "2024-01-11", "2099")] if nm == "비트코인" else []
        pers += [("~2015", "2000", "2015-12-31"), ("2016~22", "2016", "2022-12-31"), ("2023~", "2023", "2099")]
        P("\n### %s" % nm)
        P("| 판 | %s |" % " | ".join("%s 배수·낙폭" % p for p, _, _ in pers)); P("|---|%s" % "---|" * len(pers))
        for k, r in R.items():
            cs = []
            for _, a, b in pers:
                s = r[(r.index >= a) & (r.index <= b)]
                if len(s) < 100: cs.append("-"); continue
                m, cg, dd = stat(s); cs.append("%.2f배 · %.0f%%" % (m, dd * 100))
            P("| %s | %s |" % (k, " | ".join(cs)))


def stocks(mk):
    import run_spec as RS
    A, uni, _ = RS.load_market(mk)
    A["uni"] = uni.values
    A = A.sort_values(["ticker", "date"]).reset_index(drop=True)
    A = A[A.date >= ("20050101" if mk == "KR" else "20110101")].reset_index(drop=True)
    cost = 0.33 if mk == "KR" else 0.25
    r1 = A.groupby("ticker").close.pct_change() * 100
    ur = r1[A.uni & r1.abs().lt(35)].groupby(A.date[A.uni & r1.abs().lt(35)]).mean()
    rows = []
    for tk, idx in A.groupby("ticker", sort=False).indices.items():
        sub = A.iloc[idx]
        o, h, l, c = (sub[k].to_numpy(np.float64) for k in ("open", "high", "low", "close"))
        if len(c) < 60 or np.isnan(o).any(): continue
        u = sub.uni.to_numpy(); d = sub.date.to_numpy()
        for m, nm in MODES:
            for a, b in signals(o, h, l, c, m):
                if not u[a - 1]: continue
                px_out = o[b] if b < len(c) - 1 else c[b]
                ret = (px_out / o[a] - 1) * 100 - cost
                if abs(ret) > 300: continue
                rows.append((nm, d[a], ret, b - a))
    E = pd.DataFrame(rows, columns=["k", "date", "r", "days"])
    E["per"] = np.where(E.date <= "20151231", "옛날", np.where(E.date <= "20221231", "학습", "검증"))
    PER = [("옛날", "20050101", "20151231"), ("학습", "20160101", "20221231"), ("검증", "20230101", "20991231")]
    uy = {p: ur[(ur.index >= a) & (ur.index <= b)].mean() * 250 for p, a, b in PER}
    P("\n## %s 종목 — 거래당(비용 %.2f 뒤) · 돈-날 연환산 vs 유니버스 보유 연환산(옛날 %+.1f · 학습 %+.1f · 검증 %+.1f)" % (mk, cost, uy["옛날"], uy["학습"], uy["검증"]))
    P("| 판 | 구간 | 건수 | 평균 · 중앙 | 승률 | 보유일 | 돈-날 연환산 |"); P("|---|---|---|---|---|---|---|")
    for (k, p), Z in E.groupby(["k", "per"], sort=False):
        P("| %s | %s | %d | %+.2f · %+.2f | %.0f%% | %.0f | %+.1f%% |" % (k, p, len(Z), Z.r.mean(), Z.r.median(), (Z.r > 0).mean() * 100, Z.days.mean(), Z.r.sum() / max(Z.days.sum(), 1) * 250))


def main():
    assets()
    stocks("KR"); stocks("US")
    (Path(__file__).resolve().parent / "cache" / "yt_cks.out").write_text("\n".join(OUT), encoding="utf-8")


if __name__ == "__main__":
    main()
