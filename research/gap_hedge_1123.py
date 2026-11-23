# -*- coding: utf-8 -*-
"""2026-11-23 사용자 "재줘" — [갭하락] 헤지를 인버스 ETF 로 긴 기간 확인 (H0432 이어서).
선물 1년치(fut_rel_1123.py)에서 '09:00 선물 매도·15:20 환매'가 흔들림 25%↓·최악의 날 절반이었다 → 주식 계좌로 되는 인버스 ETF 시가 매수·종가 매도로 2016~ 확인.
  거래: data/y1_hist.pkl 넓은 판 · 시장 대비 갭 ≤ -1.5 (말한 그대로) · 변형 -1.0·-2.0 · 날 바구니 = 그날 신호 같은 금액, 시가→종가 − 0.23
  헤지: 그날 산 금액 × 배율만큼 인버스 ETF 를 시가에 사서 종가에 판다(ETF 는 거래세 없음 — 왕복 0.05% 로 잡음, 실제 시가·종가를 쓰므로 시가 괴리는 값에 들어 있음)
        KODEX 인버스(114800, 코스피200) · KODEX 코스닥150선물인버스(251340, 2016-08 상장) · 둘 반반  ×  배율 0.3·0.5·0.87·1.0  = 12칸(미리 정함)
  기간: 학습 2016-08-11~2022 · 검증 2023~2026-11-04. 배율·ETF 는 학습만 보고 고르고 검증은 그 한 칸으로 본다(나머지 칸은 참고).
    python research/memguard.py research/gap_hedge_1123.py → research/reports/gap_hedge_1123.md"""
import sys, glob
from pathlib import Path
import numpy as np, pandas as pd
sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(BASE))
OUT = []; P = lambda s="": (OUT.append(str(s)), print(s, flush=True))
CK, EC = 0.23, 0.05
ETF = {"114800": "코스피200 인버스", "251340": "코스닥150 인버스"}
T0, TV = "20160811", "20230101"
NC = [0]


def load_etf():
    cf = ROOT / "cache" / "inv_etf_1123.parquet"
    if cf.exists(): return pd.read_parquet(cf)
    rows = []
    try:
        import FinanceDataReader as fdr
        for t in ETF:
            d = fdr.DataReader(t, "2015-01-01")
            d = d[(d.Open > 0) & (d.Close > 0)]
            rows.append(pd.DataFrame({"t": t, "date": d.index.strftime("%Y%m%d"), "o": d.Open.values, "c": d.Close.values, "v": d.Volume.values}))
    except Exception as ex:
        print("fdr 실패 → pykrx:", repr(ex)[:150]); rows = []
        from pykrx import stock
        import time
        for t in ETF:
            d = stock.get_market_ohlcv("20150101", pd.Timestamp.now().strftime("%Y%m%d"), t); time.sleep(2)
            d = d[(d["시가"] > 0) & (d["종가"] > 0)]
            rows.append(pd.DataFrame({"t": t, "date": d.index.strftime("%Y%m%d"), "o": d["시가"].values, "c": d["종가"].values, "v": d["거래량"].values}))
    E = pd.concat(rows, ignore_index=True); E.to_parquet(cf, index=False)
    return E


E = load_etf(); E["oc"] = (E.c / E.o - 1) * 100
X = E.pivot(index="date", columns="t", values="oc")
P("# [갭하락] 인버스 ETF 헤지 — 긴 기간 (2026-11-23 · H0432)\n")
for t, nm in ETF.items():
    z = X[t].dropna(); P("- %s(%s): %s~%s · %d일 · 시가→종가 평균 %+.3f%% · 편차 %.2f" % (nm, t, z.index.min(), z.index.max(), len(z), z.mean(), z.std()))
U = pd.read_pickle(BASE / "data" / "y1_hist.pkl")
U = U[(U.liq <= 2 / 3) & (U.q_gap <= 0.40) & (U.q_vm.fillna(1) <= 0.30) & (U.rgap <= 3.0)].dropna(subset=["oc", "amt20"])


def basket(th):
    B = U[U.rgap <= th].groupby("date").oc.agg(n="size", r="mean"); B["r"] -= CK
    return B.join(X, how="inner").dropna(subset=list(ETF)).loc[T0:]


def stat(r):
    r = pd.Series(r).dropna(); cs = r.cumsum(); dd = (cs - cs.cummax()).min()
    return dict(n=len(r), mean=r.mean(), sd=r.std(), sr=r.mean() / r.std() if r.std() > 0 else np.nan, win=(r > 0).mean() * 100, worst=r.min(), q5=r.quantile(0.05),
                tot=r.sum(), dd=dd)


def line(lab, s):
    return "| %s | %d | %+.2f | %.2f | %.2f | %d%% | %+.2f | %+.2f | %+.0f | %.0f |" % (lab, s["n"], s["mean"], s["sd"], s["sr"], s["win"], s["worst"], s["q5"], s["tot"], s["dd"])


HEAD = "| 판 | 날 | 날 평균 | 편차 | 평균÷편차 | 플러스 날 | 최악의 날 | 하위 5% 날 | 합(%p) | 가장 깊은 낙폭(%p) |\n|---|---|---|---|---|---|---|---|---|---|"
HEDGES = [("114800", ETF["114800"]), ("251340", ETF["251340"]), ("mix", "둘 반반")]
BETAS = (0.3, 0.5, 0.87, 1.0)


def hedged(D, col, b):
    h = (D["114800"] + D["251340"]) / 2 if col == "mix" else D[col]
    return D.r + b * (h - EC)


D = basket(-1.5); TR, VA = D.loc[:"20221231"], D.loc[TV:]
P("\n## 말한 그대로 (시장 대비 갭 ≤ -1.5) — %s~%s · %d일" % (D.index.min(), D.index.max(), len(D)))
for nm, Z in (("학습 2016-08~2022", TR), ("검증 2023~", VA)):
    for t, en in ETF.items():
        z = Z.dropna(subset=["r", t]); b = np.polyfit(z[t], z.r, 1)
        P("- %s: 날 성적 × %s 시가→종가 상관 %+.2f · ETF 1%%당 %+.2f%%p" % (nm, en, np.corrcoef(z[t], z.r)[0, 1], b[0]))
P("\n### 학습 (2016-08-11~2022-12) — 12칸\n"); P(HEAD); P(line("헤지 없음", stat(TR.r)))
best, bk = None, None
for col, en in HEDGES:
    for b in BETAS:
        s = stat(hedged(TR, col, b)); NC[0] += 1; P(line("%s %.2f배" % (en, b), s))
        if best is None or s["sr"] > best["sr"]: best, bk = s, (col, en, b)
P("\n학습에서 평균÷편차가 가장 높은 칸 = **%s %.2f배** → 검증은 이 칸으로 본다." % (bk[1], bk[2]))
P("\n### 검증 (2023-01~2026-11-04)\n"); P(HEAD); P(line("헤지 없음", stat(VA.r))); P(line("**고른 칸: %s %.2f배**" % (bk[1], bk[2]), stat(hedged(VA, bk[0], bk[2]))))
P("\n참고(검증의 나머지 칸 — 고르는 데 쓰지 않음):\n"); P(HEAD)
for col, en in HEDGES:
    for b in BETAS: P(line("%s %.2f배" % (en, b), stat(hedged(VA, col, b))))
P("\n### 해마다 (고른 칸 · 헤지 없음 → 헤지)\n"); P("| 해 | 날 | 날 평균 | 편차 | 최악의 날 | 합(%p) | 가장 깊은 낙폭(%p) | 헤지 ETF 그해 시가→종가 평균 |"); P("|---|---|---|---|---|---|---|---|")
H = hedged(D, bk[0], bk[2]); hh = (D["114800"] + D["251340"]) / 2 if bk[0] == "mix" else D[bk[0]]
better = 0; yrs = sorted({d[:4] for d in D.index})
for y in yrs:
    a, b = stat(D.r[D.index.str[:4] == y]), stat(H[H.index.str[:4] == y])
    better += (b["sd"] < a["sd"]) + 0
    P("| %s | %d | %+.2f → %+.2f | %.2f → %.2f | %+.2f → %+.2f | %+.0f → %+.0f | %.0f → %.0f | %+.3f |" % (y, a["n"], a["mean"], b["mean"], a["sd"], b["sd"], a["worst"], b["worst"], a["tot"], b["tot"], a["dd"], b["dd"],
      hh[hh.index.str[:4] == y].mean()))
P("\n편차가 준 해 %d / %d · 최악의 날이 덜 나쁜 해 %d / %d · 합이 는 해 %d / %d" % (
    better, len(yrs), sum(stat(H[H.index.str[:4] == y])["worst"] > stat(D.r[D.index.str[:4] == y])["worst"] for y in yrs), len(yrs),
    sum(H[H.index.str[:4] == y].sum() > D.r[D.index.str[:4] == y].sum() for y in yrs), len(yrs)))
P("\n### 가장 나빴던 날 15개(헤지 없음 기준)\n"); P("| 날 | 신호 수 | 규칙 | 코스피200 인버스 | 코스닥150 인버스 | 고른 칸 헤지 뒤 |"); P("|---|---|---|---|---|---|")
for d, r in D.sort_values("r").head(15).iterrows(): P("| %s | %d | %+.2f | %+.2f | %+.2f | %+.2f |" % (d, r.n, r.r, r["114800"], r["251340"], H[d]))
w = D.sort_values("r").head(50); P("\n가장 나빴던 50일 평균: 규칙 %+.2f → 헤지 뒤 %+.2f · 가장 좋았던 50일 평균: 규칙 %+.2f → 헤지 뒤 %+.2f" % (w.r.mean(), H[w.index].mean(), D.sort_values("r").tail(50).r.mean(), H[D.sort_values("r").tail(50).index].mean()))
P("\n## 변형 (같은 칸: %s %.2f배)\n" % (bk[1], bk[2])); P("| 판 | 구간 | 날 | 날 평균 | 편차 | 최악의 날 | 하위 5% | 합 | 낙폭 |"); P("|---|---|---|---|---|---|---|---|---|")
for th in (-1.0, -2.0):
    Dv = basket(th); Hv = hedged(Dv, bk[0], bk[2])
    for nm, sl in (("학습", slice(None, "20221231")), ("검증", slice(TV, None))):
        a, b = stat(Dv.r.loc[sl]), stat(Hv.loc[sl]); NC[0] += 1
        P("| 시장 대비 갭 ≤ %.1f | %s | %d | %+.2f → %+.2f | %.2f → %.2f | %+.2f → %+.2f | %+.2f → %+.2f | %+.0f → %+.0f | %.0f → %.0f |" % (th, nm, a["n"], a["mean"], b["mean"], a["sd"], b["sd"], a["worst"], b["worst"], a["q5"], b["q5"], a["tot"], b["tot"], a["dd"], b["dd"]))
# 신호가 많은 날만 헤지 / ETF 비용 두 배
for lab, r in (("신호 5개↑ 날만 헤지", np.where(D.n >= 5, H, D.r)), ("ETF 왕복 비용 0.10%", H - bk[2] * 0.05)):
    r = pd.Series(r, index=D.index); NC[0] += 1
    for nm, sl in (("학습", slice(None, "20221231")), ("검증", slice(TV, None))):
        a, b = stat(D.r.loc[sl]), stat(r.loc[sl])
        P("| %s | %s | %d | %+.2f → %+.2f | %.2f → %.2f | %+.2f → %+.2f | %+.2f → %+.2f | %+.0f → %+.0f | %.0f → %.0f |" % (lab, nm, a["n"], a["mean"], b["mean"], a["sd"], b["sd"], a["worst"], b["worst"], a["q5"], b["q5"], a["tot"], b["tot"], a["dd"], b["dd"]))
# 선물 1년치와 맞대기
try:
    F = pd.concat([pd.read_parquet(f) for f in sorted(glob.glob(str(BASE / "data" / "factory" / "fut" / "KR_*.parquet")))], ignore_index=True)
    F = F[F.sess == "D"]; F["m"] = (F.hm // 100) * 60 + F.hm % 100
    rows = {}
    for (sym, d), g in F.groupby(["sym", "d"]):
        g = g.sort_values("m"); k = g.m - g.m.iloc[0]; b = g[k >= 15]
        if len(b): rows[(sym, d)] = (g[k <= 395].c.iloc[-1] / b.o.iloc[0] - 1) * 100
    FI = pd.Series(rows).unstack(0)
    J = X.join(FI, how="inner").dropna()
    P("\n## 선물과 맞대기 (%s~%s · %d일)" % (J.index.min(), J.index.max(), len(J)))
    P("- 코스피200 인버스 시가→종가 × 코스피200 선물 09:00→15:20: 상관 %+.2f · 코스닥150 인버스 × 코스닥150 선물: 상관 %+.2f" % (np.corrcoef(J["114800"], J["K200"])[0, 1], np.corrcoef(J["251340"], J["KQ150"])[0, 1]))
    P("- 같은 날 평균: 코스피200 인버스 %+.3f vs 선물 반대 %+.3f · 코스닥150 인버스 %+.3f vs 선물 반대 %+.3f" % (J["114800"].mean(), -J["K200"].mean(), J["251340"].mean(), -J["KQ150"].mean()))
except Exception as ex:
    P("선물 맞대기 실패: " + repr(ex)[:150])
P("\n시험 칸 %d" % NC[0])
(ROOT / "reports" / "gap_hedge_1123.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
if "--nolog" not in sys.argv:
    try:
        from verdict import log_trials
        log_trials("gap_hedge_1123", NC[0])
    except Exception as ex: print("칸 수 기록 실패:", repr(ex)[:200])
