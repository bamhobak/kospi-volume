# -*- coding: utf-8 -*-
"""미장 후보 2차 (2026-10-25, us_ideas.py 뒤 '변형 알아서') — H0367.
 ① C7 짝 5일 이 그냥 상승장 5일 흐름인지 — 같은 날 대형 200 아무거나 5일과 비교
 ② C8 갭 ≤ -4% & 첫 30분 +3%↑ 반등 → 10:00 매수: 해마다 · 대형 100/100~500 · 시장(SPY 갭) · 파는 때(15:00·15:30·종가) · 실적일 빼고(2025-08~)
 ③ A3 토스 주간거래(뉴욕 밤~새벽) 값 — 아시아가 새로 알려 준 몫(잔차)이 '주간거래 값 → 미장 시가' 에 남아 있나.
    반도체 9종목 1분봉(bf)에서 뉴욕 02:30 이전 마지막 체결가(한국 15:30~16:30 — 국장 마감 뒤).
    python research/us_ideas2.py
"""
import sys, glob, os, time, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(BASE)); sys.path.insert(0, str(ROOT))
from verdict import log_trials

COST = 0.20
OUT = []; CELLS = [0]
def P(s=""): OUT.append(s); print(s, flush=True)
pct = lambda a, b: (a / b - 1) * 100


def st(x):
    x = pd.Series(x).dropna()
    if len(x) < 15: return None
    t = x.mean() / (x.std() / np.sqrt(len(x))) if x.std() > 0 else 0
    return dict(n=len(x), mean=x.mean(), med=x.median(), win=(x > 0).mean() * 100, t=t)


def cell(s, n=0):
    return "- (%d)" % n if not s else "%+.2f · 중앙 %+.2f · %.0f%% · t%.1f (%d)" % (s["mean"], s["med"], s["win"], s["t"], s["n"])


def row(name, D, col, net=True, cut="20250101"):
    CELLS[0] += 1
    v = D[col] - (COST if net else 0)
    L, V = v[D.d < cut], v[D.d >= cut]
    P("| %s | %s | %s |" % (name, cell(st(L), L.notna().sum()), cell(st(V), V.notna().sum())))


def head(title, note="", lab="학습 2022~24"):
    P("\n### " + title)
    if note: P(note)
    P("\n| 칸 | %s (평균 · 중앙 · 승률 · t · 건) | 검증 2025~ |" % lab); P("|---|---|---|")


t0 = time.time()
A = pd.read_parquet(ROOT / "cache" / "m1_daysum_us.parquet").sort_values(["t", "d"]).reset_index(drop=True)
A = A[(A.nb >= 300) & (A.o > 0) & (A.pc > 0)].copy()
g = A.groupby("t", sort=False)
A["gap"] = pct(A.o, A.pc); A["r30"] = pct(A.p1000, A.o); A["day"] = pct(A.c, A.pc)
A["rest"] = pct(A.c, A.p1000); A["to1500"] = pct(A.p1500, A.p1000); A["to1530"] = pct(A.p1530, A.p1000)
A["nc"] = g.c.shift(-1); A["c5"] = pct(g.c.shift(-5), A.c); A["nx"] = pct(A.nc, A.p1000)
A["v20"] = g.val.transform(lambda s: s.shift(1).rolling(20, min_periods=10).mean())
A["vk"] = A.groupby("d").v20.rank(ascending=False)
A = A[A.d >= "20220101"]
P("# 미장 후보 2차 · %s" % time.strftime("%Y-%m-%d"))

# ① C7 바탕
head("① C7 짝 5일 — 같은 날 아무 대형 종목 5일과 비교", "짝 고르기 = 2022 · 학습 2023~24.", "학습 2023~24")
D = A.pivot(index="d", columns="t", values="day")
top = A[A.d < "20230101"].groupby("t").val.mean().nlargest(200).index
C = D.loc[D.index < "20230101", [t for t in top if t in D.columns]].corr(min_periods=150)
np.fill_diagonal(C.values, np.nan)
pairs = {t: C[t].idxmax() for t in C.columns if C[t].max() >= 0.7}
Y = A[A.t.isin(pairs.keys()) & (A.d >= "20230101")].copy()
mk = list(zip(Y.t.map(pairs), Y.d)); M = A.set_index(["t", "d"])
Y["rel"] = Y.day - M.day.reindex(mk).values
base = Y.groupby("d").c5.transform("mean")                        # 같은 날 짝 있는 대형 종목 전체 5일 평균
Y["x5"] = Y.c5 - base
row("대형 200(짝 있는 것) 아무 날 5일 (비용 뒤)", Y, "c5")
for th in (3, 5):
    Z = Y[Y.rel <= -th]
    row("짝보다 -%d%%p↓ · 5일 (비용 뒤)" % th, Z, "c5")
    row("짝보다 -%d%%p↓ · 5일 − 같은 날 대형 전체 (비용 전)" % th, Z, "x5", net=False)
    Z = Y[(Y.day <= -th)]
    row("[대조] 본인 -%d%%↓ (짝 상관없이) · 5일 − 같은 날 대형 전체" % th, Z, "x5", net=False)

# ② C8 반등
head("② C8 갭 ≤ -4% & 첫 30분 +3%↑ 반등 → 10:00 매수", "대형 500. 파는 때 15:00(to1500)·15:30(to1530)·종가(rest).")
G = A[A.vk <= 500].copy()
spy = A[A.t == "SPY"].set_index("d").gap
G["sgap"] = G.d.map(spy)
base = (G.gap <= -4) & (G.r30 >= 3)
for th_g, th_r in ((-4, 3), (-4, 2), (-6, 3), (-4, 4), (-3, 3)):
    row("갭 ≤ %d%% & 첫 30분 +%d%%↑ · 10:00→종가" % (th_g, th_r), G[(G.gap <= th_g) & (G.r30 >= th_r)], "rest")
Z = G[base]
row("  10:00→15:00", Z, "to1500"); row("  10:00→15:30", Z, "to1530")
row("  대형 100", Z[Z.vk <= 100], "rest"); row("  대형 101~500", Z[Z.vk > 100], "rest")
row("  SPY 갭 ≥ 0 (시장 멀쩡한 날 · 종목 혼자 빠짐)", Z[Z.sgap >= 0], "rest")
row("  SPY 갭 < -0.5 (시장도 빠진 날)", Z[Z.sgap < -0.5], "rest")
row("  갭 -4~-8%", Z[Z.gap > -8], "rest"); row("  갭 -8%↓", Z[Z.gap <= -8], "rest")
row("[대조] 갭 ≤ -4% & 첫 30분 0~+1% · 10:00→종가", G[(G.gap <= -4) & (G.r30 >= 0) & (G.r30 < 1)], "rest")
row("[대조] 갭 ≥ -1% (보통 날) & 첫 30분 +3%↑ · 10:00→종가", G[(G.gap >= -1) & (G.r30 >= 3)], "rest")
P("\n해마다 (갭 ≤ -4% & 첫 30분 +3%↑ · 10:00→종가, 비용 뒤): " + " · ".join(
    "%s %+.2f(%d·%.0f%%)" % (y, (q.rest - COST).mean(), len(q), (q.rest > COST).mean() * 100) for y, q in Z.groupby(Z.d.str[:4])))
P("분기마다: " + " ".join("%s:%+.2f(%d)" % (k, (q.rest - COST).mean(), len(q)) for k, q in Z.groupby(Z.d.str[:4] + "Q" + ((Z.d.str[4:6].astype(int) - 1) // 3 + 1).astype(str))))
P("하루 몇 건: 신호 날 %d · 하루 중앙 %d · 최대 %d" % (Z.d.nunique(), Z.groupby("d").size().median(), Z.groupby("d").size().max()))
try:
    E = pd.read_csv(BASE / "data" / "us" / "earn_recent.csv", dtype={"edate": str})
    ek = set(zip(E.ticker, E.edate)); dl = sorted(A.d.unique()); prv = {b: a for a, b in zip(dl, dl[1:])}
    Z2 = Z[Z.d >= "20250815"].copy()
    Z2["earn"] = [((t, d) in ek) or ((t, prv.get(d)) in ek) for t, d in zip(Z2.t, Z2.d)]
    P("2025-08-15~ (실적일 자료 있는 구간): 실적 반응일 %d건 평균 %+.2f · 실적 아님 %d건 평균 %+.2f (비용 뒤, 10:00→종가)" % (
        Z2.earn.sum(), (Z2[Z2.earn].rest - COST).mean(), (~Z2.earn).sum(), (Z2[~Z2.earn].rest - COST).mean()))
except Exception as ex:
    P("실적일 실패 %r" % ex)

# ③ A3 주간거래
P("\n### ③ A3 토스 주간거래 값 → 미장 시가 (반도체 9종목)")
SEMI = ["MU", "NVDA", "AMD", "AVGO", "AMAT", "LRCX", "KLAC", "TSM", "INTC"]
rec = []
for tk in SEMI:
    f = BASE / "data" / "m1" / "US" / "bf" / (tk + ".parquet")
    if not f.exists(): continue
    x = pd.read_parquet(f)
    k = pd.to_datetime(x.ts, unit="s", utc=True).dt.tz_convert("America/New_York")
    x = x.assign(dt=k)
    # 주간거래·프리장: 정규장 아닌 봉 → '다음 정규장 날짜'에 붙인다(뉴욕 16:00 뒤면 다음 날)
    hm = k.dt.hour * 100 + k.dt.minute
    early = (hm <= 230) & (hm >= 0)          # 뉴욕 00:00~02:30 (한국 13:00~16:30 · 주간거래 시간)
    q = x[early].assign(d=k[early].dt.strftime("%Y%m%d"))
    rec.append(q.groupby("d").c.last().rename("dm").to_frame().assign(t=tk, nbar=q.groupby("d").size()).reset_index())
if rec:
    DM = pd.concat(rec)
    P("주간거래 봉 있는 날: " + " ".join("%s %d(%s~)" % (t, len(q), q.d.min()) for t, q in DM.groupby("t")))
    J = A[A.t.isin(SEMI)].merge(DM, on=["t", "d"], how="inner")
    J = J[J.nbar >= 5]
    J["dm_gap"] = pct(J.dm, J.pc)          # 전날 종가 → 주간거래 02:30
    J["dm_open"] = pct(J.o, J.dm)          # 주간거래 02:30 → 정규장 시가
    J["dm_close"] = pct(J.c, J.dm)
    try:
        K = pd.read_pickle(BASE / "data" / "kr_scan.pkl")
        K = K[K.ticker.isin(["005930", "000660"]) & (K.date >= "20211101")]
        kr = (K.pivot(index="date", columns="ticker", values="close").pct_change() * 100).mean(axis=1).rename("kr")
        S = A[A.t.isin(SEMI)].groupby("d").day.mean().shift(1).rename("prev")
        J = J.merge(kr, left_on="d", right_index=True, how="left").merge(S, left_on="d", right_index=True, how="left")
        J["res"] = J.kr - 0.31 * J.prev
        P("상관(검증·학습 합쳐 %d건): 잔차↔주간거래 갭 %+.2f · 잔차↔(주간거래→시가) %+.2f · 잔차↔(주간거래→종가) %+.2f · 주간거래 갭↔(주간거래→시가) %+.2f" % (
            J.res.notna().sum(), J.res.corr(J.dm_gap), J.res.corr(J.dm_open), J.res.corr(J.dm_close), J.dm_gap.corr(J.dm_open)))
        head("국장 반도체 잔차 → 주간거래 02:30 매수", "비용 0.20 (주간거래 매수 → 정규장 시가/종가 매도)")
        for th in (1.5, 3.0):
            Z = J[J.res >= th]
            row("잔차 ≥ +%.1f%% · 주간거래 → 시가" % th, Z, "dm_open"); row("잔차 ≥ +%.1f%% · 주간거래 → 종가" % th, Z, "dm_close")
            Z = J[(J.res >= th) & (J.dm_gap < th * 0.31)]
            row("[변형] 잔차 ≥ +%.1f%% & 주간거래가 아직 덜 오름 · → 시가" % th, Z, "dm_open")
        row("[대조] 아무 날 · 주간거래 → 시가 (비용 전)", J, "dm_open", net=False)
    except Exception as ex:
        import traceback; traceback.print_exc(); P("국장 붙이기 실패 %r" % ex)
P("\n칸 수 %d · %.1f분" % (CELLS[0], (time.time() - t0) / 60))
log_trials("us_ideas2_20261025", CELLS[0])
(ROOT / "reports" / "us_ideas2_20261025.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
