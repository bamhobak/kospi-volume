# -*- coding: utf-8 -*-
"""미장 규칙 후보 실측 (2026-10-25, 사용자 "위 미장규칙 후보들 테스트 가능한 것들 실측해줘" + "변형도 알아서") — H0367.

재료: research/cache/m1_daysum_us.parquet(토스 1분봉 → 정규장 요약, 1,083종목 · 2021-12~2026-10) ·
      data/us_scan_full.pkl(일봉 2007~, 폐지 포함) · data/kr_scan.pkl(국장 일봉) · yfinance(대만·일본).
비용 = 토스 미장 왕복 0.20%(0.1%×2, 환전 빼고). 학습 2022~24 / 검증 2025~ (1분봉은 짧아서) · 일봉(C10)은 학습 2016~22 / 검증 2023~.
롱만(공매도 안 함) — 내리는 쪽 칸은 '피하기' 참고용.

 B4 장중 모멘텀   SPY·QQQ·IWM·대형 100: 전날 종가→10:00 등락 → 15:30→종가 / 10:00→종가
 B5 레버리지 막판 QQQ·SPY·메가캡: 전날 종가→15:00 큰 날 → 15:00→종가 · 15:30→종가 · 다음 날 시가
 C7 짝 종목       2022 상관 최고 짝(대형 200) — 하루 짝보다 -3/-5%p 처진 쪽 종가 매수 → 1·5일 · 15:30 버전
 C8 큰 갭 날      대형 500 · 갭 ±4/±8% × 첫 30분 방향 → 10:00→종가 · 다음 날 / 실제 실적일(2025-08~) 확인
 C10 업종 대비 급락 일봉 대형 500 · 하루 -5%↓ & 같은 업종(SIC2) 중앙보다 -5%p↓ → 다음 날 시가 1·5·20일
 A1 국장 → 미장   삼성전자·하이닉스 하루 등락(그날 미장 밤 전에 끝남) − 전날 밤 미장 반도체 → 그날 밤 MU·NVDA 등 시가→종가·갭
 A2 아시아 → 미장 TSMC(2330.TW)·도쿄일렉(8035.T)·닛케이 — 같은 방식
    python research/us_ideas.py
"""
import sys, time, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(BASE)); sys.path.insert(0, str(ROOT))
from verdict import log_trials

COST = 0.20
OUT = []; CELLS = [0]
def P(s=""): OUT.append(s); print(s, flush=True)


def st(x):
    x = pd.Series(x).dropna()
    if len(x) < 15: return None
    t = x.mean() / (x.std() / np.sqrt(len(x))) if x.std() > 0 else 0
    return dict(n=len(x), mean=x.mean(), med=x.median(), win=(x > 0).mean() * 100, t=t)


def cell(s):
    return "- (%d)" % (0 if s is None else s) if not isinstance(s, dict) else "%+.2f · 중앙 %+.2f · %.0f%% · t%.1f (%d)" % (s["mean"], s["med"], s["win"], s["t"], s["n"])


def row(name, D, col, net=True, split="d", cut="20250101"):
    """D[col] = 수익(%) · 비용 빼고 학습/검증"""
    CELLS[0] += 1
    v = D[col] - (COST if net else 0)
    L, V = v[D[split] < cut], v[D[split] >= cut]
    P("| %s | %s | %s |" % (name, cell(st(L) or len(L.dropna())), cell(st(V) or len(V.dropna()))))


def head(title, note=""):
    P("\n### " + title)
    if note: P(note)
    P("\n| 칸 | 학습 2022~24 (평균 · 중앙 · 승률 · t · 건) | 검증 2025~ |"); P("|---|---|---|")


# ───────────────────────── 1분봉 요약 ─────────────────────────
t0 = time.time()
A = pd.read_parquet(ROOT / "cache" / "m1_daysum_us.parquet").sort_values(["t", "d"]).reset_index(drop=True)
A = A[(A.nb >= 300) & (A.o > 0) & (A.pc > 0)].copy()                 # 반나절 장·빈 날 빼기
g = A.groupby("t", sort=False)
pct = lambda a, b: (a / b - 1) * 100
A["gap"] = pct(A.o, A.pc); A["f30"] = pct(A.p1000, A.pc); A["r30"] = pct(A.p1000, A.o)
A["rest"] = pct(A.c, A.p1000); A["l30"] = pct(A.c, A.p1530); A["l60"] = pct(A.c, A.p1500); A["l10"] = pct(A.c, A.p1550)
A["to1500"] = pct(A.p1500, A.pc); A["to1530"] = pct(A.p1530, A.pc); A["oc"] = pct(A.c, A.o); A["day"] = pct(A.c, A.pc)
A["no"] = g.o.shift(-1); A["nc"] = g.c.shift(-1); A["nd"] = g.d.shift(-1)
A["on"] = pct(A.no, A.c); A["c1"] = pct(A.nc, A.c)
A["c5"] = pct(g.c.shift(-5), A.c)
A["v20"] = g.val.transform(lambda s: s.shift(1).rolling(20, min_periods=10).mean())
A["vr"] = A.val / A.v20
A["vk"] = A.groupby("d").v20.rank(ascending=False)
A = A[A.d >= "20220101"]
P("# 미장 규칙 후보 실측 · %s" % time.strftime("%Y-%m-%d"))
P("\n1분봉 요약 %s행 · %d종목 · %s~%s · 비용 왕복 %.2f%% 뺀 값(%%)" % (f"{len(A):,}", A.t.nunique(), A.d.min(), A.d.max(), COST))

# ── B4 ──
head("B4 장중 모멘텀 — 전날 종가→10:00 방향이 막판까지 가나",
     "15:30→종가(l30) · 10:00→종가(rest). Gao 외(2018) 미국 ETF 첫 30분 → 마지막 30분 연구의 재현.")
for tk in ("SPY", "QQQ", "IWM"):
    X = A[A.t == tk]
    row("%s 전부 · 15:30→종가 (비용 전)" % tk, X, "l30", net=False)
    for th in (0.5, 1.0):
        row("%s f30 ≥ +%.1f%% · 15:30→종가" % (tk, th), X[X.f30 >= th], "l30")
        row("%s f30 ≥ +%.1f%% · 15:30→종가 (비용 전)" % (tk, th), X[X.f30 >= th], "l30", net=False)
        row("%s f30 ≤ -%.1f%% · 15:30→종가 (비용 전, 롱이면)" % (tk, th), X[X.f30 <= -th], "l30", net=False)
        row("%s f30 ≥ +%.1f%% · 10:00→종가" % (tk, th), X[X.f30 >= th], "rest")
        row("%s f30 ≤ -%.1f%% · 10:00→종가 (되돌림 롱)" % (tk, th), X[X.f30 <= -th], "rest")
    X = X.assign(sg=np.sign(X.f30) * X.l30)
    row("%s 방향 맞히기 sign(f30)×l30 (비용 전, 롱숏)" % tk, X, "sg", net=False)
B = A[A.vk <= 100]
for th in (1.0, 2.0):
    row("대형 100 f30 ≥ +%.0f%% · 15:30→종가" % th, B[B.f30 >= th], "l30")
    row("대형 100 f30 ≥ +%.0f%% · 10:00→종가" % th, B[B.f30 >= th], "rest")
    row("대형 100 f30 ≤ -%.0f%% · 10:00→종가 (되돌림 롱)" % th, B[B.f30 <= -th], "rest")
# 추가 변형: 15:30 까지 방향(전날 종가→15:30) → 마지막 30분
for tk in ("SPY", "QQQ"):
    X = A[A.t == tk]
    for th in (1.0, 2.0):
        row("[변형] %s 전날→15:30 ≥ +%.0f%% · 15:30→종가" % (tk, th), X[X.to1530 >= th], "l30")
        row("[변형] %s 전날→15:30 ≤ -%.0f%% · 15:30→종가 (비용 전)" % (tk, th), X[X.to1530 <= -th], "l30", net=False)

# ── B5 ──
head("B5 레버리지 ETF 막판 재조정 — 크게 움직인 날 15:00 뒤 같은 방향",
     "레버리지·인버스 ETF 는 장 마감 직전에 그날 방향으로 사고판다(QQQ·SPY 3배, 단일 종목 2배: NVDA·TSLA·MSTR 등).")
MEGA = ["NVDA", "TSLA", "AAPL", "MSFT", "AMZN", "META", "GOOGL", "AMD", "AVGO", "MSTR", "COIN", "PLTR", "SMCI", "NFLX"]
for nm, X in (("QQQ", A[A.t == "QQQ"]), ("SPY", A[A.t == "SPY"]), ("메가캡 14", A[A.t.isin(MEGA)])):
    for th in ((1.5, 2.0) if nm != "메가캡 14" else (3.0, 5.0)):
        up, dn = X[X.to1500 >= th], X[X.to1500 <= -th]
        row("%s 전날→15:00 ≥ +%.1f%% · 15:00→종가" % (nm, th), up, "l60")
        row("%s ≥ +%.1f%% · 15:00→종가 (비용 전)" % (nm, th), up, "l60", net=False)
        row("%s ≥ +%.1f%% · 15:50→종가 (비용 전)" % (nm, th), up, "l10", net=False)
        row("%s ≥ +%.1f%% · 종가→다음 날 시가 (비용 전)" % (nm, th), up, "on", net=False)
        row("%s ≤ -%.1f%% · 15:00→종가 (비용 전, 롱이면)" % (nm, th), dn, "l60", net=False)
        row("%s ≤ -%.1f%% · 종가→다음 날 시가 (비용 전, 되돌림)" % (nm, th), dn, "on", net=False)
        row("[변형] %s ≤ -%.1f%% · 종가 매수→다음 날 종가" % (nm, th), dn, "c1")

# ── C7 ──
head("C7 짝 종목 — 짝보다 처진 쪽을 산다",
     "짝 = 2022 일봉 상관이 가장 높은 대형 종목(2022 평균 거래대금 상위 200, 상관 ≥ 0.7). 2022 는 짝 고르기에만 쓰고 학습은 2023~24.")
D = A.pivot(index="d", columns="t", values="day")
top = A[A.d < "20230101"].groupby("t").val.mean().nlargest(200).index
C = D.loc[D.index < "20230101", [t for t in top if t in D.columns]].corr(min_periods=150)
np.fill_diagonal(C.values, np.nan)
pairs = {t: C[t].idxmax() for t in C.columns if C[t].max() >= 0.7}
P("\n짝 %d쌍 (예: %s)" % (len(pairs), ", ".join("%s-%s" % kv for kv in list(pairs.items())[:12])))
Y = A[A.t.isin(pairs.keys()) & (A.d >= "20230101")].copy()
Y["mate"] = Y.t.map(pairs)
M = A.set_index(["t", "d"])
mk = list(zip(Y.mate, Y.d))
Y["mday"] = M.day.reindex(mk).values; Y["m1530"] = M.to1530.reindex(mk).values
Y["mc1"] = M.c1.reindex(mk).values; Y["mc5"] = M.c5.reindex(mk).values
Y["rel"] = Y.day - Y.mday; Y["rel1530"] = Y.to1530 - Y.m1530
Y["x1"] = Y.c1 - Y.mc1; Y["x5"] = Y.c5 - Y.mc5
Y["p1530_c1"] = pct(Y.nc, Y.p1530)
for th in (3, 5):
    Z = Y[Y.rel <= -th]
    row("짝보다 -%d%%p↓ · 종가 매수 → 다음 날 종가" % th, Z, "c1")
    row("짝보다 -%d%%p↓ · 종가 매수 → 5일" % th, Z, "c5")
    row("  짝 대비(롱숏, 비용 전) 1일" % (), Z, "x1", net=False)
    row("  짝 대비(롱숏, 비용 전) 5일", Z, "x5", net=False)
    Z = Y[Y.rel1530 <= -th]
    row("[15:30] 짝보다 -%d%%p↓ · 15:30 매수 → 다음 날 종가" % th, Z, "p1530_c1")
    Z = Y[(Y.rel <= -th) & (Y.day <= -th)]
    row("[변형] 짝보다 -%d%%p↓ & 본인 -%d%%↓ · 5일" % (th, th), Z, "c5")
    Z = Y[(Y.rel <= -th) & (Y.mday >= 0)]
    row("[변형] 짝은 올랐는데 본인만 -%d%%p · 5일" % th, Z, "c5")
Y["split"] = Y.d
P("(C7 은 학습 2023~24)")

# ── C8 ──
head("C8 큰 갭 날(실적 대용) — 첫 30분 방향 뒤 10:00 매수",
     "대형 500(20일 거래대금) · 갭 = 시가/전날 종가. 10:00→종가(rest) · 다음 날 종가까지(10:00 매수 → 다음 날 종가 = nx).")
G = A[A.vk <= 500].copy()
G["nx"] = pct(G.nc, G.p1000)
for th in (4, 8):
    for nm, m in (("갭 ≥ +%d%% & 첫 30분 더 오름" % th, (G.gap >= th) & (G.r30 > 0)),
                  ("갭 ≥ +%d%% & 첫 30분 밀림" % th, (G.gap >= th) & (G.r30 < 0)),
                  ("갭 ≤ -%d%% & 첫 30분 반등" % th, (G.gap <= -th) & (G.r30 > 0)),
                  ("갭 ≤ -%d%% & 첫 30분 더 빠짐" % th, (G.gap <= -th) & (G.r30 < 0))):
        Z = G[m]
        row(nm + " · 10:00→종가", Z, "rest")
        row(nm + " · 10:00→다음 날 종가", Z, "nx")
for th in (2, 3):
    Z = G[(G.gap <= -4) & (G.r30 >= th)]
    row("[변형] 갭 ≤ -4%% & 첫 30분 +%d%%↑ 반등 · 10:00→종가" % th, Z, "rest")
    Z = G[(G.gap >= 4) & (G.r30 >= th)]
    row("[변형] 갭 ≥ +4%% & 첫 30분 +%d%%↑ · 10:00→종가" % th, Z, "rest")
# 실제 실적일 (2025-08~, 검증 구간만)
try:
    E = pd.read_csv(BASE / "data" / "us" / "earn_recent.csv", dtype={"edate": str})
    ek = set(zip(E.ticker, E.edate))
    dl = sorted(A.d.unique()); nxt = {a: b for a, b in zip(dl, dl[1:])}
    G["earn"] = [((t, d) in ek) or ((t, prv) in ek) for t, d, prv in zip(G.t, G.d, G.d.map({b: a for a, b in nxt.items()}))]
    Z = G[G.earn & (G.d >= "20250812")]
    P("\n실제 실적 반응일(실적일 당일 또는 다음 날 중 갭 쪽) 대형 500 · %d건" % len(Z))
    for nm, m in (("실적 · 갭 ≥ +4% & 첫 30분 더 오름", (Z.gap >= 4) & (Z.r30 > 0)), ("실적 · 갭 ≥ +4% & 밀림", (Z.gap >= 4) & (Z.r30 < 0)),
                  ("실적 · 갭 ≤ -4% & 반등", (Z.gap <= -4) & (Z.r30 > 0)), ("실적 · 갭 ≤ -4% & 더 빠짐", (Z.gap <= -4) & (Z.r30 < 0))):
        row(nm + " · 10:00→종가", Z[m], "rest")
except Exception as ex:
    P("실적일 실패 %r" % ex)

# ── A1·A2 ──
head("A1·A2 아시아 → 그날 밤 미장 반도체",
     "아시아 종목 하루 등락 − (전날 밤 미장 반도체 평균 하루 등락 × 베타) = '아시아가 새로 알려 준 몫'(잔차). 미장 반도체 = MU·NVDA·AMD·AVGO·AMAT·LRCX·KLAC·TSM·INTC 평균. "
     "그날 밤 미장 시가→종가(oc)·갭. 아시아가 미장 개장 전에 끝나니 정보는 이미 갭에 들어가야 맞다 → 시가→종가에 남는 게 있나.")
SEMI = ["MU", "NVDA", "AMD", "AVGO", "AMAT", "LRCX", "KLAC", "TSM", "INTC"]
S = A[A.t.isin(SEMI)].groupby("d")[["oc", "gap", "day"]].mean()
S["prev_day"] = S.day.shift(1)
asia = {}
try:
    K = pd.read_pickle(BASE / "data" / "kr_scan.pkl")
    K = K[K.ticker.isin(["005930", "000660"]) & (K.date >= "20211101")]
    kr = K.pivot(index="date", columns="ticker", values="close").pct_change() * 100
    asia["삼성·하이닉스 평균"] = kr.mean(axis=1)
except Exception as ex:
    P("국장 실패 %r" % ex)
try:
    import yfinance as yf
    for nm, sym in (("TSMC 대만", "2330.TW"), ("도쿄일렉", "8035.T"), ("닛케이", "^N225")):
        h = yf.Ticker(sym).history(start="2021-11-01", auto_adjust=True)
        if len(h):
            s = h.Close.pct_change() * 100
            s.index = s.index.strftime("%Y%m%d"); asia[nm] = s
except Exception as ex:
    P("야후 실패 %r" % ex)
for nm, s in asia.items():
    # 아시아 날 d 의 등락 → 미장 같은 날짜 d 의 밤(뉴욕 d). 직전 미장 밤 = 뉴욕 d-1.
    J = S.join(s.rename("a"), how="inner").dropna()
    Lm = J.index < "20250101"
    b = np.polyfit(J.prev_day[Lm], J.a[Lm], 1)[0]
    J["res"] = J.a - b * J.prev_day
    J = J.reset_index().rename(columns={"index": "d"})
    for part, m in (("학습", J.d < "20250101"), ("검증", J.d >= "20250101")):
        q = J[m]
        P("  %s %s: 잔차↔미장 갭 상관 %+.2f · 잔차↔시가→종가 상관 %+.2f (%d일, 베타 %.2f)" % (
            nm, part, q.res.corr(q.gap), q.res.corr(q.oc), len(q), b))
    for th in (1.5, 3.0):
        row("%s 잔차 ≥ +%.1f%% → 미장 반도체 시가→종가" % (nm, th), J[J.res >= th], "oc")
        row("%s 잔차 ≤ -%.1f%% → 시가→종가 (되돌림 롱)" % (nm, th), J[J.res <= -th], "oc")

# ── C10 (일봉) ──
P("\n### C10 대형주 업종 대비 하루 급락 → 다음 날 시가 (일봉 2007~)")
try:
    import run_spec as R
    U, uni, since = R.load_market("US")
    U = U.sort_values(["ticker", "date"]).reset_index(drop=True)
    gg = U.groupby("ticker", sort=False)
    U["r1"] = (U.close / gg.close.shift(1) - 1) * 100
    big = (U.groupby("date").amt20.rank(ascending=False) <= 500) & uni
    sg = U[big].groupby(["date", "up"]).r1.agg(["median", "size"])
    sg = sg[sg["size"] >= 3]["median"]
    U["sec"] = sg.reindex(pd.MultiIndex.from_arrays([U.date, U.up])).values
    U["rel"] = U.r1 - U.sec
    J = R.Judge(U, big, since)
    P("\n| 칸 | 보유 | 전체 2016~ (n · 중앙 · 평균 · 승률) | 학습 16~22 중앙 | 검증 23~ 중앙 | 같은 날 대형 대비(중앙) |"); P("|---|---|---|---|---|---|")
    for nm, m in (("하루 -5%↓ & 업종 -5%p↓", (U.r1 <= -5) & (U.rel <= -5)), ("하루 -8%↓ & 업종 -8%p↓", (U.r1 <= -8) & (U.rel <= -8)),
                  ("[대조] 하루 -5%↓ & 업종도 같이 빠짐(업종 대비 -1%p 안)", (U.r1 <= -5) & (U.rel > -1)),
                  ("[변형] 업종 -5%p↓ & 60일선 위(추세 살아 있는 종목)", (U.r1 <= -5) & (U.rel <= -5) & (U.dma60 > 0)),
                  ("[변형] 업종 -5%p↓ & 60일선 아래", (U.r1 <= -5) & (U.rel <= -5) & (U.dma60 <= 0)),
                  ("[변형] 업종 -10%p↓", (U.rel <= -10))):
        for h in (5, 20):
            Y2 = J.run(m.fillna(False), h)
            a = Y2[Y2.date >= "20160101"]
            if len(a) < 30: P("| %s | %d일 | 표본 부족(%d) | | | |" % (nm, h, len(a))); continue
            tr = a[a.date <= "20221231"]; va = a[a.date >= "20230101"]
            ex = (a.r - a.date.map(J.bench(h))).median()
            P("| %s | %d일 | %d · %+.2f · %+.2f · %.0f%% | %+.2f (%d) | %+.2f (%d) | %+.2f |" % (
                nm, h, len(a), a.r.median(), a.r.mean(), (a.r > 0).mean() * 100, tr.r.median(), len(tr),
                va.r.median() if len(va) else float("nan"), len(va), ex))
    CELLS[0] += J.cells
except Exception as ex:
    import traceback; traceback.print_exc(); P("C10 실패 %r" % ex)

P("\n칸 수 %d · %.1f분" % (CELLS[0], (time.time() - t0) / 60))
log_trials("us_ideas_20261025", CELLS[0])
(ROOT / "reports").mkdir(exist_ok=True)
(ROOT / "reports" / "us_ideas_20261025.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
