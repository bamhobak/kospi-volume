# -*- coding: utf-8 -*-
"""2026-11-23 사용자 "성적 관계 재줘" — 살 때 아는 시장 방향(지수 선물·QQQ 장전) × 데이 규칙 성적. H0431·H0432·H0433.
자료: 덧 수집 첫 사용 — data/factory/fut(코스피200·코스닥150 선물 1분봉 2025-12-12~) · research/cache/bf_us_idx(QQQ 한국 시각 1분봉).
A [갭하락](data/y1_hist.pkl 넓은 판, 시장 대비 갭 ≤ -1.5 가 '말한 그대로' · 변형 -1.0·-2.0, 시가→종가 − 0.23)
  A1 날 성적 × 선물 09:00→15:20(지수 몫 확인) · × 08:45→08:59 · 08:45→08:52 · 선물 갭(어제 15:45→08:59) · 야간 선물(어제 15:45→06:00)
  A2 08:45→08:59 구간별 날 성적 · A3 쉬는 판(그 값이 x 아래면 그날 안 삼) · A4 선물 헤지 판(09:00 매도·15:20 환매, 배율 0.5·0.87·1.0)
B [장후 낙폭](C:/temp/kp/t6_full_panel_1115.pkl, 19:50 -2.5%↓ · 낮 ±1% 빼기 · 깊은 순 40, 19:51~20:00 VWAP → 다음 날 시가 − 0.23)
  B1 밤 성적 × 19:50 에 아는 값(야간 선물 18:00→19:50 · 15:45→19:50 · QQQ 아침 첫 봉→19:50 · QQQ 저녁 첫 봉→19:50) · B2 구간별 · B3 쉬는 판
  B4 야간 선물 헤지 판(19:50 매도 → 다음 거래일 09:00 환매)
표본이 1년(선물)·1년 8달(QQQ)뿐 — 앞 절반·뒤 절반 부호가 같은지만 같이 본다(학습/검증 나누기엔 짧다).
    python research/memguard.py research/fut_rel_1123.py → research/reports/fut_rel_1123.md"""
import sys, glob, bisect
from pathlib import Path
import numpy as np, pandas as pd
sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(BASE))
OUT = []; P = lambda s="": (OUT.append(str(s)), print(s, flush=True))
CK, HC = 0.23, 0.02                       # 왕복 비용 · 선물 헤지 왕복 비용(수수료·호가 한 틱쯤)
NC = {"A": 0, "B": 0, "H": 0}


def tstat(x):
    x = pd.Series(x).dropna()
    return x.mean() / (x.std(ddof=1) / np.sqrt(len(x))) if len(x) > 2 and x.std(ddof=1) > 0 else np.nan


def corr(a, b):
    z = pd.concat([pd.Series(a), pd.Series(b)], axis=1).dropna()
    return (np.corrcoef(z.iloc[:, 0], z.iloc[:, 1])[0, 1], len(z)) if len(z) > 5 else (np.nan, len(z))


def halves(D, x, y):
    D = D.dropna(subset=[x, y]).sort_index(); h = len(D) // 2
    return corr(D[x].iloc[:h], D[y].iloc[:h])[0], corr(D[x].iloc[h:], D[y].iloc[h:])[0]


# ── 선물 날별 값 ─────────────────────────────────────────────────────
F = pd.concat([pd.read_parquet(f) for f in sorted(glob.glob(str(BASE / "data" / "factory" / "fut" / "KR_*.parquet")))], ignore_index=True)
F["m"] = (F.hm // 100) * 60 + F.hm % 100


def fut_feat(sym):
    rows = {}
    for (d, se), g in F[F.sym == sym].groupby(["d", "sess"]):
        g = g.sort_values("m"); r = rows.setdefault(d, {})
        if se == "D":
            m0 = g.m.iloc[0]
            if m0 not in (525, 585): continue                       # 08:45(늦은 개장 날 09:45)부터 받은 날만
            k = g.m - m0; b = g[k >= 15]
            r.update(o0=g.o.iloc[0], c7=g[k <= 7].c.iloc[-1], c14=g[k <= 14].c.iloc[-1], o15=b.o.iloc[0] if len(b) else np.nan,
                     c395=g[k <= 395].c.iloc[-1], cl=g.c.iloc[-1])
        else:
            x = g[g.hm <= 1950]
            if len(x): r.update(n_o=g.o.iloc[0], n1950=x.c.iloc[-1], n_end=g.c.iloc[-1])
    X = pd.DataFrame.from_dict(rows, orient="index").sort_index()
    X = X[X.o0.notna()]
    pv = X.shift(1)
    X["f15"] = (X.c14 / X.o0 - 1) * 100; X["f07"] = (X.c7 / X.o0 - 1) * 100
    X["fgap"] = (X.c14 / pv.cl - 1) * 100; X["fnight"] = (pv.n_end / pv.cl - 1) * 100
    X["intr"] = (X.c395 / X.o15 - 1) * 100
    X["n1"] = (X.n1950 / X.n_o - 1) * 100; X["n2"] = (X.n1950 / X.cl - 1) * 100
    X["o15_next"] = X.o15.shift(-1); X["hedge_n"] = (X.o15_next / X.n1950 - 1) * 100       # 19:50 → 다음 거래일 09:00
    return X


K, Q = fut_feat("K200"), fut_feat("KQ150")
FX = {"코스피200": K, "코스닥150": Q, "둘 평균": (K + Q) / 2}
P("# 살 때 아는 시장 방향 × 데이 규칙 성적 (2026-11-23 · H0431·H0432·H0433)\n")
P("- 선물 1분봉 %s~%s · %d거래일(코스피200) · 비용 %.2f%% · 헤지 왕복 %.2f%%" % (K.index.min(), K.index.max(), len(K), CK, HC))

# ── A [갭하락] ───────────────────────────────────────────────────────
U = pd.read_pickle(BASE / "data" / "y1_hist.pkl")
U = U[(U.date >= K.index.min()) & (U.liq <= 2 / 3) & (U.q_gap <= 0.40) & (U.q_vm.fillna(1) <= 0.30) & (U.rgap <= 3.0)].dropna(subset=["oc", "amt20"])
P("\n## A. [갭하락] — %s~%s" % (U.date.min(), U.date.max()))
FN = [("f15", "선물 08:45→08:59"), ("f07", "선물 08:45→08:52"), ("fgap", "선물 갭(어제 15:45→08:59)"), ("fnight", "야간 선물(어제 15:45→06:00)")]
for th, lab in ((-1.5, "말한 그대로(시장 대비 갭 ≤ -1.5)"), (-1.0, "변형 ≤ -1.0"), (-2.0, "변형 ≤ -2.0")):
    B = U[U.rgap <= th].groupby("date").oc.agg(n="size", r="mean"); B["r"] -= CK
    P("\n### %s — %d일 · %d건 · 날 평균 %+.2f%% (t %.1f) · 플러스 날 %d%% · 최악의 날 %+.2f%%" % (lab, len(B), B.n.sum(), B.r.mean(), tstat(B.r), (B.r > 0).mean() * 100, B.r.min()))
    P("\n| 지수 | 날 성적×선물 09:00→15:20 (1%당) | " + " | ".join(n for _, n in FN) + " | 08:45→08:59 가 그날 선물 장중을 맞히나 |"); P("|---|---|" + "---|" * (len(FN) + 1))
    for nm, X in FX.items():
        D = B.join(X, how="inner")
        c0, n0 = corr(D.intr, D.r); z = D.dropna(subset=["intr", "r"]); beta = np.polyfit(z.intr, z.r, 1)
        cells = []
        for k, _ in FN:
            c, n = corr(D[k], D.r); h1, h2 = halves(D, k, "r"); cells.append("%+.2f (앞 %+.2f·뒤 %+.2f)" % (c, h1, h2)); NC["A"] += 1
        c9, _ = corr(D.f15, D.intr); g1, g2 = halves(D, "f15", "intr")
        P("| %s | %+.2f (%+.2f%%p · 0 일 때 %+.2f%%) | %s | %+.2f (앞 %+.2f·뒤 %+.2f) |" % (nm, c0, beta[0], beta[1], " | ".join(cells), c9, g1, g2))
    if th != -1.5: continue
    D = B.join(FX["둘 평균"], how="inner").dropna(subset=["f15", "r"])
    P("\n**A2 선물 08:45→08:59(둘 평균) 구간별** — 표본 %d일" % len(D)); P("\n| 구간 | 날 | [갭하락] 날 평균 | 플러스 날 | 최악의 날 | 그날 선물 장중 평균 |"); P("|---|---|---|---|---|---|")
    for lo, hi in ((-99, -0.3), (-0.3, -0.1), (-0.1, 0.1), (0.1, 0.3), (0.3, 99)):
        x = D[(D.f15 > lo) & (D.f15 <= hi)]; NC["A"] += 1
        if len(x): P("| %s~%s%% | %d | %+.2f | %d%% | %+.2f | %+.2f |" % ("" if lo < -9 else "%+.1f" % lo, "" if hi > 9 else "%+.1f" % hi, len(x), x.r.mean(), (x.r > 0).mean() * 100, x.r.min(), x.intr.mean()))
    P("\n**A3 쉬는 판** — 그 값이 문턱 아래인 날은 안 삼(날 성적 합 = 같은 금액으로 매일 샀을 때 %p 합)"); P("\n| 기준 | 문턱 | 사는 날 | 날 평균 | 합 | 지금(전부 삼) 대비 | 앞 절반·뒤 절반 차이 |"); P("|---|---|---|---|---|---|---|")
    P("| 전부 삼 | — | %d | %+.2f | %+.1f | — | — |" % (len(D), D.r.mean(), D.r.sum()))
    h = len(D) // 2
    for k, nm in FN[:3]:
        for x in (-0.5, -0.3, -0.2, -0.1, 0.0):
            keep = D[k] > x; NC["A"] += 1
            d1 = D.r[keep].iloc[:0].sum(); a = D.iloc[:h]; b = D.iloc[h:]
            P("| %s | > %+.1f%% | %d | %+.2f | %+.1f | %+.1f | %+.1f · %+.1f |" % (nm, x, keep.sum(), D.r[keep].mean(), D.r[keep].sum(), D.r[keep].sum() - D.r.sum(),
              a.r[a[k] > x].sum() - a.r.sum(), b.r[b[k] > x].sum() - b.r.sum()))
    P("\n**A4 선물 헤지 판** — 09:00 에 산 금액 × 배율만큼 선물 매도, 15:20 환매"); P("\n| 헤지 지수 | 배율 | 날 평균 | 표준편차 | 평균÷편차 | 플러스 날 | 최악의 날 | 하위 5% 날 | 합 |"); P("|---|---|---|---|---|---|---|---|---|")
    D0 = B.join(K[["intr"]].rename(columns={"intr": "ik"}), how="inner").join(Q[["intr"]].rename(columns={"intr": "iq"}), how="inner").dropna()
    D0["im"] = (D0.ik + D0.iq) / 2
    P("| 헤지 없음 | 0 | %+.2f | %.2f | %.2f | %d%% | %+.2f | %+.2f | %+.1f |" % (D0.r.mean(), D0.r.std(), D0.r.mean() / D0.r.std(), (D0.r > 0).mean() * 100, D0.r.min(), D0.r.quantile(0.05), D0.r.sum()))
    for col, nm in (("ik", "코스피200"), ("iq", "코스닥150"), ("im", "둘 반반")):
        for b in (0.5, 0.87, 1.0):
            hr = D0.r - b * D0[col] - HC * b; NC["H"] += 1
            P("| %s | %.2f | %+.2f | %.2f | %.2f | %d%% | %+.2f | %+.2f | %+.1f |" % (nm, b, hr.mean(), hr.std(), hr.mean() / hr.std(), (hr > 0).mean() * 100, hr.min(), hr.quantile(0.05), hr.sum()))
    hh = len(D0) // 2
    for lab2, Z in (("앞 절반", D0.iloc[:hh]), ("뒤 절반", D0.iloc[hh:])):
        hr = Z.r - 0.87 * Z.im - HC * 0.87
        P("- %s(%s~%s): 헤지 없음 평균 %+.2f·편차 %.2f·최악 %+.2f → 둘 반반 0.87배 평균 %+.2f·편차 %.2f·최악 %+.2f" % (lab2, Z.index.min(), Z.index.max(), Z.r.mean(), Z.r.std(), Z.r.min(), hr.mean(), hr.std(), hr.min()))
    w = D0.sort_values("r").head(8)
    P("\n가장 나빴던 8일: " + " · ".join("%s 규칙 %+.2f(선물 장중 %+.2f → 헤지 뒤 %+.2f)" % (d, r.r, r.im, r.r - 0.87 * r.im - HC * 0.87) for d, r in w.iterrows()))

# ── B [장후 낙폭] ────────────────────────────────────────────────────
Z = pd.read_pickle(r"C:\temp\kp\t6_full_panel_1115.pkl")
R = Z[(Z.AH50 <= -2.5) & ~((Z.dayr.abs() <= 1.0).fillna(False)) & (0.10 * Z.v41 >= 30e4)].sort_values(["d", "AH50"])
R = R[R.groupby("d").cumcount() < 40]
N = R.groupby("d").agg(n=("g_vw", "size"), r=("g_vw", "mean"), d1=("d1", "first"))
US = pd.read_parquet(BASE / "data" / "factory" / "us_daily.parquet"); US = US[US.sym == "QQQ"].assign(date=lambda x: x.date.astype(str)).sort_values("date")
ud, uc = US.date.tolist(), US.close.tolist()
def us_ret(d, d1):
    i, j = bisect.bisect_left(ud, d) - 1, bisect.bisect_left(ud, d1) - 1
    return (uc[j] / uc[i] - 1) * 100 if i >= 0 and j >= 0 else np.nan
N["nq"] = [us_ret(d, d1) for d, d1 in zip(N.index, N.d1)]
qf = sorted(glob.glob(str(ROOT / "cache" / "bf_us_idx" / "bars_*.parquet")))
if qf:
    QB = pd.concat([pd.read_parquet(f) for f in qf], ignore_index=True); QB = QB[QB.t == "QQQ"].assign(d=lambda x: x.d.astype(str)).drop_duplicates(["d", "hm"]).sort_values(["d", "hm"])
    mo = QB[QB.hm <= 900].groupby("d").o.first(); ev = QB[(QB.hm >= 1641) & (QB.hm <= 1950)].groupby("d"); e0, e1 = ev.o.first(), ev.c.last()
    last_hm = QB[(QB.hm >= 1641) & (QB.hm <= 1950)].groupby("d").hm.max()
    N["q1"] = ((e1 / mo - 1) * 100).reindex(N.index); N["q2"] = ((e1 / e0 - 1) * 100).reindex(N.index)
    N.loc[last_hm.reindex(N.index).fillna(0).to_numpy() < 1930, ["q1", "q2"]] = np.nan          # 19:30 뒤 봉이 없으면 '19:50 값'이 아님
else:
    N["q1"] = np.nan; N["q2"] = np.nan
N = N.join(K[["n1", "n2", "hedge_n"]], how="left")
P("\n## B. [장후 낙폭] — %s~%s · %d밤 · %d건 · 밤 평균 %+.2f%% (t %.1f) · 플러스 밤 %d%% · 최악의 밤 %+.2f%%" % (N.index.min(), N.index.max(), len(N), N.n.sum(), N.r.mean(), tstat(N.r), (N.r > 0).mean() * 100, N.r.min()))
GN = [("n1", "야간 선물 18:00→19:50"), ("n2", "선물 15:45→19:50"), ("q1", "QQQ 아침 첫 봉→19:50"), ("q2", "QQQ 저녁 첫 봉→19:50")]
P("\n**B1 19:50 에 아는 값**"); P("\n| 값 | 표본 밤 | 밤 성적과 상관 (앞·뒤) | 1%당 | 그날 밤 나스닥 전체와 상관 | 참고: 밤 성적×나스닥 전체(같은 표본) |"); P("|---|---|---|---|---|---|")
for k, nm in GN:
    D = N.dropna(subset=[k, "r"]); NC["B"] += 1
    if len(D) < 20: P("| %s | %d | 표본 부족 | | | |" % (nm, len(D))); continue
    c, n = corr(D[k], D.r); h1, h2 = halves(D, k, "r"); b = np.polyfit(D[k], D.r, 1); cq, _ = corr(D[k], D.nq); cr, _ = corr(D.nq, D.r)
    P("| %s | %d | %+.2f (%+.2f·%+.2f) | %+.2f%%p | %+.2f | %+.2f |" % (nm, n, c, h1, h2, b[0], cq, cr))
for k, nm, cuts in (("q1", "QQQ 아침 첫 봉→19:50", ((-99, -0.5), (-0.5, -0.1), (-0.1, 0.1), (0.1, 0.5), (0.5, 99))), ("n2", "선물 15:45→19:50", ((-99, -0.5), (-0.5, -0.1), (-0.1, 0.1), (0.1, 0.5), (0.5, 99)))):
    D = N.dropna(subset=[k, "r"])
    if len(D) < 20: continue
    P("\n**B2 %s 구간별** — %d밤" % (nm, len(D))); P("\n| 구간 | 밤 | 밤 평균 | 플러스 밤 | 최악의 밤 | 그날 밤 나스닥 평균 |"); P("|---|---|---|---|---|---|")
    for lo, hi in cuts:
        x = D[(D[k] > lo) & (D[k] <= hi)]; NC["B"] += 1
        if len(x): P("| %s~%s%% | %d | %+.2f | %d%% | %+.2f | %+.2f |" % ("" if lo < -9 else "%+.1f" % lo, "" if hi > 9 else "%+.1f" % hi, len(x), x.r.mean(), (x.r > 0).mean() * 100, x.r.min(), x.nq.mean()))
    P("\n**B3 쉬는 판(%s)**" % nm); P("\n| 문턱 | 사는 밤 | 밤 평균 | 합 | 전부 삼 대비 | 앞 절반·뒤 절반 차이 |"); P("|---|---|---|---|---|---|")
    P("| 전부 삼 | %d | %+.2f | %+.1f | — | — |" % (len(D), D.r.mean(), D.r.sum())); h = len(D) // 2; a, b = D.iloc[:h], D.iloc[h:]
    for x in (-1.0, -0.5, -0.3, -0.1, 0.0):
        keep = D[k] > x; NC["B"] += 1
        P("| > %+.1f%% | %d | %+.2f | %+.1f | %+.1f | %+.1f · %+.1f |" % (x, keep.sum(), D.r[keep].mean(), D.r[keep].sum(), D.r[keep].sum() - D.r.sum(), a.r[a[k] > x].sum() - a.r.sum(), b.r[b[k] > x].sum() - b.r.sum()))
D = N.dropna(subset=["hedge_n", "r"])
P("\n**B4 야간 선물 헤지 판(코스피200, 19:50 매도 → 다음 거래일 09:00 환매)** — %d밤(%s~%s)" % (len(D), D.index.min(), D.index.max()))
c, _ = corr(D.hedge_n, D.r); b = np.polyfit(D.hedge_n, D.r, 1)
P("- 밤 성적 × 선물 19:50→09:00: 상관 %+.2f · 선물 1%%당 %+.2f%%p · 선물 0 일 때 %+.2f%%" % (c, b[0], b[1]))
P("\n| 배율 | 밤 평균 | 표준편차 | 평균÷편차 | 플러스 밤 | 최악의 밤 | 하위 5% 밤 | 합 |"); P("|---|---|---|---|---|---|---|---|")
for bb in (0.0, 0.3, 0.5, 0.7, 1.0):
    hr = D.r - bb * D.hedge_n - HC * bb; NC["H"] += 1
    P("| %.1f | %+.2f | %.2f | %.2f | %d%% | %+.2f | %+.2f | %+.1f |" % (bb, hr.mean(), hr.std(), hr.mean() / hr.std(), (hr > 0).mean() * 100, hr.min(), hr.quantile(0.05), hr.sum()))
hh = len(D) // 2
for lab2, X in (("앞 절반", D.iloc[:hh]), ("뒤 절반", D.iloc[hh:])):
    hr = X.r - 0.5 * X.hedge_n - HC * 0.5
    P("- %s(%s~%s): 헤지 없음 평균 %+.2f·편차 %.2f·최악 %+.2f → 0.5배 평균 %+.2f·편차 %.2f·최악 %+.2f" % (lab2, X.index.min(), X.index.max(), X.r.mean(), X.r.std(), X.r.min(), hr.mean(), hr.std(), hr.min()))
w = D.sort_values("r").head(8)
P("\n가장 나빴던 8밤: " + " · ".join("%s 규칙 %+.2f(선물 %+.2f → 0.5배 헤지 뒤 %+.2f)" % (d, r.r, r.hedge_n, r.r - 0.5 * r.hedge_n - HC * 0.5) for d, r in w.iterrows()))
P("\n시험 칸: A %d · B %d · 헤지 %d" % (NC["A"], NC["B"], NC["H"]))
(ROOT / "reports" / "fut_rel_1123.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
try:
    if "--nolog" in sys.argv: raise SystemExit          # 같은 칸을 다시 돌릴 때 칸 수를 두 번 세지 않게
    from verdict import log_trials
    log_trials("fut_rel_1123_A", NC["A"]); log_trials("fut_rel_1123_B", NC["B"]); log_trials("fut_rel_1123_hedge", NC["H"])
except Exception as ex:
    print("칸 수 기록 실패:", repr(ex)[:200])
