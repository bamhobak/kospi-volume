# -*- coding: utf-8 -*-
"""ideas5/12 후속 (2026-10-18): D 미장 폭락 다음날 소형주 과잉 갭 — 해마다·하루 건수·시가 갭 깊이 · 12 초대형주 상대강도(날짜 버그 고친 판)."""
import sys
from pathlib import Path
BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "research" / "factory")); sys.path.insert(0, str(BASE / "research"))
import numpy as np, pandas as pd
import FinanceDataReader as fdr

OUT = []
def P(s=""):
    OUT.append(s); print(s, flush=True)


def d_followup():
    import lab, feats as FT
    H = lab.hist()[["date", "ticker", "oc", "gap", "q_tr_res", "liq", "t1"]].copy(); H["oc"] -= FT.COST
    X = fdr.DataReader("IXIC", "2005-01-01"); X = X[X.Close > 0]
    us = X.Close.pct_change() * 100; us.index = us.index.strftime("%Y%m%d")
    ud = us.index.values
    H["us"] = H.date.map({d: (us.iloc[np.searchsorted(ud, d) - 1] if np.searchsorted(ud, d) > 0 else np.nan) for d in H.date.unique()})
    base = (H.gap < 0) & (H.q_tr_res <= 0.1) & (H.liq <= 1 / 3)
    for thr in (-3, -2):
        Z = H[base & (H.us <= thr)]
        B = Z.groupby("date").agg(b=("oc", "mean"), n=("oc", "size"), us=("us", "first"))
        P("\n### D 나스닥 %d%%↓ 다음날 · 갭↓ · 잔차 하위10%% · 작은 종목 — 해마다(날 바구니)" % thr)
        P("| 해 | 날 수 | 건수 | 날 바구니 평균 | 날 승률 | 건당 평균 |"); P("|---|---|---|---|---|---|")
        for y, q in B.groupby(B.index.str[:4]):
            zz = Z[Z.date.str[:4] == y]
            P("| %s | %d | %d | %+.2f | %.0f%% | %+.2f |" % (y, len(q), len(zz), q.b.mean(), (q.b > 0).mean() * 100, zz.oc.mean()))
        P("하루 평균 %.1f건 · 최악의 날 %+.2f · 가장 좋은 날 %+.2f" % (B.n.mean(), B.b.min(), B.b.max()))
        # 갭 깊이별
        Z = Z.assign(gb=pd.cut(Z.gap, [-100, -8, -5, -3, 0], labels=["-8%↓", "-5~-8", "-3~-5", "-3~0"]))
        P("갭 깊이별 건당: " + " · ".join("%s %+.2f(%d)" % (k, q.oc.mean(), len(q)) for k, q in Z.groupby("gb", observed=True)))
        # 비교: 같은 날 갭↓ 작은 종목 아무거나(잔차 무관)
        W = H[(H.gap < 0) & (H.liq <= 1 / 3) & (H.us <= thr)]
        P("대조(같은 날 갭↓ 작은 종목 잔차 무관): 건당 %+.2f · 날 바구니 %+.2f" % (W.oc.mean(), W.groupby("date").oc.mean().mean()))


def p12():
    import run_spec as RS
    K, uni, _ = RS.load_market("KR")
    Kp = K[K.mk == "KOSPI"].sort_values(["ticker", "date"]).copy()
    Kp["cap"] = np.where(Kp.marcap > 1e9, Kp.marcap / 1e8, Kp.marcap)
    Kp["r60"] = (Kp.close / Kp.groupby("ticker").close.shift(60) - 1) * 100
    days = np.array(sorted(Kp.date.unique())); md = pd.Series(days).groupby(pd.Series(days).str[:6]).min().values
    px = Kp.pivot(index="date", columns="ticker", values="close")
    X = fdr.DataReader("KS200", "2004-01-01"); X = X[X.Close > 0]
    xd = X.index.strftime("%Y%m%d").values; xc = X.Close.values
    def ix(d): k = np.searchsorted(xd, d, side="right") - 1; return xc[k] if k >= 0 else np.nan
    P("\n### 12 초대형주 상대강도 — 매달 첫 거래일 코스피 시총 상위 20 중 60일 수익 상위 N 동일가중(회전 비용 0.14%/월 근사)")
    P("| 판 | 전체 연·낙폭 | 2005~15 연 | 2016~22 연 | 2023~ 연 | 2025~26 빼고 연 |"); P("|---|---|---|---|---|---|")
    def cg(s):
        s = pd.Series(s); v = (1 + s / 100).prod(); return (v ** (12 / max(len(s), 1)) - 1) * 100
    rows = {}
    for n in (3, 5, 20):
        rs, ixs, ds = [], [], []
        for a, b in zip(md[:-1], md[1:]):
            S = Kp[Kp.date == a].dropna(subset=["r60"]).nlargest(20, "cap")
            pick = S.nlargest(n, "r60").ticker
            r = (px.loc[b, pick] / px.loc[a, pick] - 1).mean() * 100 - (0.14 if n < 20 else 0.02)
            rs.append(r); ixs.append((ix(b) / ix(a) - 1) * 100); ds.append(a)
        R = pd.DataFrame({"d": ds, "r": rs, "ix": ixs}).dropna()
        rows[n] = R
    for nm, col, n in (("시총 20 중 상위 3", "r", 3), ("시총 20 중 상위 5", "r", 5), ("시총 상위 20 전부(비교)", "r", 20), ("코스피200", "ix", 3)):
        R = rows[n]; s = R[col]
        eq = (1 + s / 100).cumprod(); dd = ((eq / eq.cummax()) - 1).min() * 100
        m1 = R.d < "201601"; m2 = (R.d >= "201601") & (R.d < "202301"); m3 = R.d >= "202301"; nb = R.d < "202501"
        P("| %s | %+.1f%% · %.0f%% | %+.1f%% | %+.1f%% | %+.1f%% | %+.1f%% |" % (nm, cg(s), dd, cg(s[m1]), cg(s[m2]), cg(s[m3]), cg(s[nb])))
    R = rows[5]; R["y"] = R.d.str[:4]
    t = R.groupby("y").apply(lambda q: pd.Series({"a": cg(q.r) / 12 * len(q), "b": cg(q.ix) / 12 * len(q)}))
    P("상위 5 vs 코스피200 해마다 이긴 해: %d/%d" % ((R.groupby("y").r.apply(lambda s: (1 + s / 100).prod()) > R.groupby("y").ix.apply(lambda s: (1 + s / 100).prod())).sum(), R.y.nunique()))


if __name__ == "__main__":
    d_followup(); p12()
    (BASE / "research" / "cache" / "ideas_followup_1018.out").write_text("\n".join(OUT), encoding="utf-8")
