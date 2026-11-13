# -*- coding: utf-8 -*-
"""2026-11-14 사용자 "장마감후 상승이나 하락 한쪽으로 쏠려서 금요일 애프터장이 끝났을때 월요일 어떻게 시작했는지 과거 데이터".
장후 움직임 ah = 통합 종가(토스, NXT 20:00) ÷ KRX 종가 − 1. 대상 = 다음 날 NXT 장전 봉 있는 종목(t5_full_panel 의 t·pd).
다음 날: 장전(08:40 NXT ÷ 통합 종가) · KRX 시가 ÷ KRX 종가(gapK) · KRX 시가 ÷ 통합 종가(gapN, 장후 움직임 유지 or 반납) · 그날 시가→종가.
시장 쏠림 = 그날 대상 종목 ah 평균(동일 가중) · 폭(+0.5%↑ 비율 − -0.5%↓ 비율)."""
import sys, glob
from pathlib import Path
import numpy as np, pandas as pd
BASE = Path(r"C:\vscode\kospi-volume"); C = BASE / "research/cache"
sys.stdout.reconfigure(encoding="utf-8")
OUT = []; P = lambda s="": (OUT.append(str(s)), print(s, flush=True))
S = pd.read_pickle(r"C:\temp\kp\t5_full_panel_1114.pkl")[["t", "d", "pd", "tc_y", "o", "pre"]]
K = pd.read_parquet(C / "m1_daysum.parquet", columns=["t", "d", "o", "c"]); K["t"] = K.t.astype(str); K["d"] = K.d.astype(str); K = K[K.d >= "20250101"]; ks = []
for f in sorted(glob.glob(str(BASE / "data/m1/KR/day/*.parquet"))):
    d = Path(f).stem
    if d <= K.d.max(): continue
    x = pd.read_parquet(f, columns=["t", "ts", "o", "c", "v"]); x = x[x.v > 0].sort_values("ts")
    g = x.groupby("t").agg(o=("o", "first"), c=("c", "last")).reset_index(); g["d"] = d; ks.append(g)
K = pd.concat([K] + ks, ignore_index=True).drop_duplicates(["t", "d"], keep="last")
S = S.merge(K[["t", "d", "c"]].rename(columns={"d": "pd", "c": "kc"}), on=["t", "pd"], how="left").merge(K[["t", "d", "c"]].rename(columns={"c": "c1"}), on=["t", "d"], how="left")
S = S[S.kc.notna() & S.o.notna() & S.tc_y.notna()].copy()
S["ah"] = (S.tc_y / S.kc - 1) * 100
S["gapK"] = (S.o / S.kc - 1) * 100
S["gapN"] = (S.o / S.tc_y - 1) * 100
S["oc"] = (S.c1 / S.o - 1) * 100
S = S[(S.ah.abs() < 30) & (S.gapK.abs() < 30)]
S["wd"] = pd.to_datetime(S.pd).dt.weekday          # 장후가 있었던 날 요일(4=금)
S["gapd"] = (pd.to_datetime(S.d) - pd.to_datetime(S.pd)).dt.days
P("종목-날 %d · 장후 날 %d (%s~%s) · 금요일 %d" % (len(S), S.pd.nunique(), S.pd.min(), S.pd.max(), S[S.wd == 4].pd.nunique()))
D = S.groupby("pd").agg(wd=("wd", "first"), nxt=("d", "first"), gapd=("gapd", "first"), n=("t", "size"), AH=("ah", "mean"), AHmed=("ah", "median"),
                        up=("ah", lambda v: (v > 0.5).mean() * 100), dn=("ah", lambda v: (v < -0.5).mean() * 100),
                        pre=("pre", "mean"), gapK=("gapK", "mean"), gapN=("gapN", "mean"), oc=("oc", "mean")).reset_index()
D["br"] = D.up - D.dn
D.to_csv(BASE / "research/reports/fri_ah_1114_days.csv", index=False, encoding="utf-8-sig")
F = D[D.wd == 4]; W = D[D.wd < 4]
P("금요일 장후 쏠림(AH 평균) 분포: " + " · ".join("%d%% %+.2f" % (q * 100, F.AH.quantile(q)) for q in (0, .1, .25, .5, .75, .9, 1)))
P("평일(월~목) 장후 쏠림 분포: " + " · ".join("%d%% %+.2f" % (q * 100, W.AH.quantile(q)) for q in (0, .1, .25, .5, .75, .9, 1)))


def row(nm, X):
    if not len(X): return "| %s | 0 | | | | | | |" % nm
    hit = (np.sign(X.gapK) == np.sign(X.AH)).mean() * 100
    return "| %s | %d | %+.2f%% | %+.2f%% | %+.2f%% | %+.2f%% | %+.2f%% | %.0f%% |" % (nm, len(X), X.AH.mean(), X.pre.mean(), X.gapK.mean(), X.gapN.mean(), X.oc.mean(), hit)


HD = "| 묶음 | 날 | 장후 쏠림(평균) | 다음 날 장전 08:40 (÷통합 종가) | 시가 ÷ KRX 종가 | 시가 ÷ 통합 종가 | 시가→종가 | 시가 방향 = 장후 방향 |\n|---|---|---|---|---|---|---|---|"
for nm, X in (("금요일 → 월요일", F), ("월~목 → 다음 날", W)):
    P("\n## %s — 장후 쏠림 크기별 (종목 동일 가중 평균)\n" % nm); P(HD)
    for lab, m in (("+1.0%↑", X.AH >= 1), ("+0.5~1.0", (X.AH >= .5) & (X.AH < 1)), ("+0.2~0.5", (X.AH >= .2) & (X.AH < .5)), ("-0.2~+0.2", X.AH.abs() < .2),
                   ("-0.5~-0.2", (X.AH <= -.2) & (X.AH > -.5)), ("-1.0~-0.5", (X.AH <= -.5) & (X.AH > -1)), ("-1.0%↓", X.AH <= -1), ("전체", X.AH == X.AH)):
        P(row(lab, X[m]))
    P("\n상위·하위 20%%(쏠림 순위): "); P(HD)
    P(row("오름 쏠림 상위 20%", X[X.AH >= X.AH.quantile(.8)])); P(row("내림 쏠림 하위 20%", X[X.AH <= X.AH.quantile(.2)]))
    P(row("폭(오른 비율−내린 비율) +30%p↑", X[X.br >= 30])); P(row("폭 -30%p↓", X[X.br <= -30]))
    P("상관: 장후 쏠림 vs 시가÷KRX 종가 %.2f · vs 시가÷통합 종가 %.2f · vs 시가→종가 %.2f" % (X.AH.corr(X.gapK), X.AH.corr(X.gapN), X.AH.corr(X.oc)))
P("\n## 금요일 쏠림 큰 날 하나하나 (|쏠림| 상위 24)\n")
P("| 금요일 | 다음 장 | 종목 | 장후 쏠림 | 오름%·내림% | 월 장전 | 월 시가÷KRX 종가 | 월 시가÷통합 종가 | 월 시가→종가 |"); P("|---|---|---|---|---|---|---|---|---|")
for r in F.reindex(F.AH.abs().sort_values(ascending=False).index).head(24).sort_values("pd").itertuples():
    P("| %s | %s | %d | %+.2f%% | %.0f·%.0f | %+.2f%% | %+.2f%% | %+.2f%% | %+.2f%% |" % (r.pd, r.nxt, r.n, r.AH, r.up, r.dn, r.pre, r.gapK, r.gapN, r.oc))
# 종목 단위 변형
P("\n## 종목 단위 — 그 종목 장후 크기별 다음 날 (금→월 vs 평일)\n")
P("| 장후 | 금→월 건 | 월 시가÷KRX 종가 | 월 시가÷통합 종가 | 월 시가→종가 | 평일 건 | 시가÷KRX 종가 | 시가÷통합 종가 | 시가→종가 |"); P("|---|---|---|---|---|---|---|---|---|")
for lab, lo, hi in (("+5%↑", 5, 99), ("+3~5", 3, 5), ("+1~3", 1, 3), ("-1~+1", -1, 1), ("-3~-1", -3, -1), ("-5~-3", -5, -3), ("-5%↓", -99, -5)):
    a = S[(S.wd == 4) & (S.ah >= lo) & (S.ah < hi)]; b = S[(S.wd < 4) & (S.ah >= lo) & (S.ah < hi)]
    P("| %s | %d | %+.2f%% | %+.2f%% | %+.2f%% | %d | %+.2f%% | %+.2f%% | %+.2f%% |" % (lab, len(a), a.gapK.mean(), a.gapN.mean(), a.oc.mean(), len(b), b.gapK.mean(), b.gapN.mean(), b.oc.mean()))
# 쏠린 금요일 안에서 종목 단위 — 쏠림과 같은 방향으로 크게 움직인 종목
P("\n## 쏠린 금요일(|쏠림| 상위 20%) 안에서 그 종목 장후 크기별 월요일\n")
FT = F[(F.AH >= F.AH.quantile(.8)) | (F.AH <= F.AH.quantile(.2))].pd
for side, sel in (("오름 쏠림 금요일", F[F.AH >= F.AH.quantile(.8)].pd), ("내림 쏠림 금요일", F[F.AH <= F.AH.quantile(.2)].pd)):
    Z = S[S.pd.isin(sel)]
    P("**%s** (%d일)  " % (side, len(sel)) + " · ".join("장후 %s: %d건 시가÷KRX %+.2f · 시가÷통합 %+.2f · 시가→종가 %+.2f" % (lab, len(z), z.gapK.mean(), z.gapN.mean(), z.oc.mean())
          for lab, z in (("+2%↑", Z[Z.ah >= 2]), ("-2~+2", Z[Z.ah.abs() < 2]), ("-2%↓", Z[Z.ah <= -2]))))
(BASE / "research/reports/fri_ah_1114.md").write_text("# 금요일 장후 쏠림 → 월요일 (11-14)\n\n" + "\n".join(OUT), encoding="utf-8")
