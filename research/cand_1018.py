# -*- coding: utf-8 -*-
"""후보 둘 다지기 (2026-10-18 사용자).
 ① H0352 미장 폭락 다음날 소형주 과잉 갭 — 나스닥 전날 하락폭 × 그 종목 갭 깊이 × 잔차 문턱 격자:
    날 수(연)·건수·건당·날 바구니·플러스 해·학습/검증 → 날짜는 늘고 성적은 덜 떨어지는 지점
 ② H0360 지수 덮개 — 언제 사고 언제 파나 · 코스피200 60일선 타이밍 단독 성적(연 매매 횟수·승률·건당·보유일·연 수익)
    체결: (가) 판정한 날 종가 (나) 다음날 시가 · 계좌 덮개 50%도 (나)로 다시
    python research/cand_1018.py
"""
import sys, os
from pathlib import Path
BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "research" / "factory")); sys.path.insert(0, str(BASE / "research"))
import numpy as np, pandas as pd
import FinanceDataReader as fdr

OUT = []
def P(s=""):
    OUT.append(s); print(s, flush=True)


def part1():
    import lab, feats as FT
    H = lab.hist()[["date", "ticker", "oc", "gap", "q_tr_res", "liq"]].copy(); H["oc"] -= FT.COST
    X = fdr.DataReader("IXIC", "2005-01-01"); X = X[X.Close > 0]
    us = X.Close.pct_change() * 100; us.index = us.index.strftime("%Y%m%d"); ud = us.index.values
    H["us"] = H.date.map({d: (us.iloc[np.searchsorted(ud, d) - 1] if np.searchsorted(ud, d) > 0 else np.nan) for d in H.date.unique()})
    H = H[H.date >= "20160101"]
    yrs = H.date.str[:4].nunique()
    P("## ① 미장 폭락 다음날 소형주 과잉 갭 — 격자 (2016~, 작은 1/3, 비용 뒤)")
    P("| 나스닥 전날 | 종목 갭 | 잔차 | 연 날 수 | 하루 건수 | 건당 학습/검증 | 날 바구니 학습/검증 | 날 승률 | 플러스 해 | 최악의 날 |")
    P("|---|---|---|---|---|---|---|---|---|---|")
    rows = []
    for usc in (-1.0, -1.5, -2.0, -2.5, -3.0):
        for gc in (0, -1, -2, -3, -5):
            for rq in (0.1, 0.2):
                m = (H.us <= usc) & (H.gap < gc if gc == 0 else H.gap <= gc) & (H.q_tr_res <= rq) & (H.liq <= 1 / 3)
                Z = H.loc[m, ["date", "oc"]]
                if len(Z) < 30: continue
                B = Z.groupby("date").oc.agg(["mean", "size"])
                tr = Z.date <= "20221231"; btr = B.index <= "20221231"
                py = B.groupby(B.index.str[:4])["mean"].mean()
                rows.append((usc, gc, rq, len(B) / yrs, B["size"].mean(), Z.oc[tr].mean(), Z.oc[~tr].mean(), B["mean"][btr].mean(), B["mean"][~btr].mean(),
                             (B["mean"] > 0).mean() * 100, (py > 0).sum(), len(py), B["mean"].min()))
    for r in rows:
        P("| %+.1f%%↓ | %s | 하위 %d%% | %.1f | %.0f | %+.2f / %+.2f | %+.2f / %+.2f | %.0f%% | %d/%d | %+.1f |" % (
            r[0], "갭<0" if r[1] == 0 else "%d%%↓" % r[1], r[2] * 100, r[3], r[4], r[5], r[6], r[7], r[8], r[9], r[10], r[11], r[12]))
    R = pd.DataFrame(rows, columns=["us", "gap", "rq", "dpy", "npd", "tr", "va", "btr", "bva", "dwin", "ypos", "ny", "worst"])
    R.to_pickle(BASE / "research" / "cache" / "cand_1018_grid.pkl")


def episodes(X, exec_):
    """60일선 타이밍 매매 목록. exec_ = 'close'(판정한 날 종가) / 'open'(다음날 시가)."""
    c, o = X.Close.values, X.Open.values
    on = (X.Close > X.Close.rolling(60).mean()).values
    d = X.index.strftime("%Y%m%d").values
    tr = []; inpos = False
    for i in range(60, len(c) - 1):
        if not inpos and on[i]:
            ent_i, ent = (i, c[i]) if exec_ == "close" else (i + 1, o[i + 1] if o[i + 1] > 0 else c[i])
            inpos = True
        elif inpos and not on[i]:
            ex_i, ex = (i, c[i]) if exec_ == "close" else (i + 1, o[i + 1] if o[i + 1] > 0 else c[i])
            tr.append((d[ent_i], d[ex_i], ex_i - ent_i, (ex / ent - 1) * 100 - 0.1)); inpos = False
    return pd.DataFrame(tr, columns=["buy", "sell", "days", "r"])


def part2():
    P("\n## ② 지수 덮개 — 코스피200 60일선 타이밍 단독")
    X = fdr.DataReader("KS200", "2004-01-01"); X = X[(X.Close > 0)]
    X.loc[X.Open <= 0, "Open"] = np.nan; X["Open"] = X.Open.fillna(X.Close.shift(1))
    for ex_nm, ex in (("판정한 날 종가에 사고팜", "close"), ("다음날 시가에 사고팜", "open")):
        T = episodes(X, ex); T["y"] = T.buy.str[:4]
        yrs = (pd.Timestamp(X.index[-1]) - pd.Timestamp(X.index[60])).days / 365.25
        tot = (1 + T.r / 100).prod()
        hold_days = T.days.sum(); all_days = len(X) - 60
        P("\n### %s (왕복 비용 0.1%%)" % ex_nm)
        P("매매 %d번(연 %.1f번) · 승률 %.0f%% · 건당 평균 %+.2f%% · 중앙 %+.2f%% · 이긴 건 평균 %+.2f%% · 진 건 평균 %+.2f%% · 평균 보유 %.0f거래일 · 들고 있는 비율 %.0f%%" % (
            len(T), len(T) / yrs, (T.r > 0).mean() * 100, T.r.mean(), T.r.median(), T.r[T.r > 0].mean(), T.r[T.r <= 0].mean(), T.days.mean(), hold_days / all_days * 100))
        bh = X.Close.iloc[-1] / X.Close.iloc[60]
        P("타이밍만 했을 때 누적 %.2f배(연 %+.1f%%) vs 그냥 보유 %.2f배(연 %+.1f%%)" % (tot, (tot ** (1 / yrs) - 1) * 100, bh, (bh ** (1 / yrs) - 1) * 100))
        P("| 해 | 매매 수 | 승률 | 그해 타이밍 수익 | 그해 지수 |"); P("|---|---|---|---|---|")
        Xy = X.Close.groupby(X.index.year).agg(lambda s: s.iloc[-1] / s.iloc[0] - 1) * 100
        for y, q in T.groupby("y"):
            P("| %s | %d | %.0f%% | %+.1f%% | %+.1f%% |" % (y, len(q), (q.r > 0).mean() * 100, ((1 + q.r / 100).prod() - 1) * 100, Xy.get(int(y), np.nan)))
    # 계좌: 다음날 시가 체결판
    import ideas5_1018 as I5
    ns = I5.portfolio_ns()
    C = ns["simulate"](1.0, 1.0, quiet=True)[0]
    X["date"] = X.index.strftime("%Y%m%d")
    sig = (X.Close > X.Close.rolling(60).mean())
    on = sig.shift(1).fillna(False).values          # 오늘 들고 있나(어제 판정 → 오늘 시가에 들어감)
    prev = np.r_[False, on[:-1]]
    c, o = X.Close.values, X.Open.values; pc = np.r_[np.nan, c[:-1]]
    r = np.where(on & ~prev, c / o - 1, np.where(on & prev, c / pc - 1, np.where(~on & prev, o / pc - 1, 0.0)))
    X["r_open"] = np.nan_to_num(r)
    X["sw"] = (on != prev).astype(float)
    C = C.merge(X[["date", "r_open", "sw"]], on="date", how="left").fillna(0)
    C["ra"] = C.nav.pct_change().fillna(0); C["cash"] = (1 - C.expo.shift(1).fillna(0)).clip(0, 1)
    P("\n### 계좌에 얹으면(다음날 시가 체결 · 현금의 50% · 비중은 매일 남는 현금에 맞춤)")
    P("| 판 | 최종 | 연 | 최대 낙폭 | 수익 난 해 |"); P("|---|---|---|---|---|")
    for nm, w in (("지금", 0.0), ("덮개 50%", 0.5), ("덮개 30%", 0.3)):
        rr = C.ra + C.cash * w * C.r_open - C.sw * C.cash * w * 0.001
        nav = (1 + rr).cumprod(); yrs = len(nav) / 252
        yr = pd.Series(nav.values, index=C.date.str[:4].values).groupby(level=0).agg(lambda v: v.iloc[-1] / v.iloc[0] - 1)
        P("| %s | %.2f배 | %+.1f%% | %.1f%% | %d/%d |" % (nm, nav.iloc[-1], (nav.iloc[-1] ** (1 / yrs) - 1) * 100, ((nav / nav.cummax()) - 1).min() * 100, (yr > 0).sum(), len(yr)))
    P("평균 현금 비율 %.0f%% (계좌가 규칙 종목에 쓰지 않고 놀리는 몫)" % (C.cash.mean() * 100))


if __name__ == "__main__":
    part1(); part2()
    (BASE / "research" / "cache" / "cand_1018.out").write_text("\n".join(OUT), encoding="utf-8")
