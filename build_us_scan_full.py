# -*- coding: utf-8 -*-
"""미장 연구 패널 — **폐지 포함**판 (2026-10-04, 사용자 "원해").

왜: run_spec 이 쓰던 us_scan.pkl 은 yfinance 현재 상장 종목으로 만든 panel_us.pkl 에서 뽑아 **살아남은 종목뿐**이었다
    (5,983종목 중 폐지 4). '빠진 종목 사기' 규칙(낙폭·저PBR·평균회귀)이 부풀려졌다(GitHub 규칙 실측 H0290 에서 확인).
재료: data/us_full_2007.pkl (2007~ · 13,151종목 중 폐지 7,165 · 수정주가 px · 다음날 시가 buy · n5~n60 · 비용 cost)
      + data/us/fin.pkl·fin_dead.pkl(SEC 재무, 시점 기준) + data/us/finra/part_*.pkl(공매도 2019~)
특징값은 us_panel.py 와 **같은 정의**로 다시 계산한다(px = 수정주가 · 고가·저가는 px/원주가 비율로 맞춤).
다른 점 하나: 업종(up)은 상장 목록 업종명이 폐지 종목엔 없어서 **SIC 2자리**로 통일했다(u = 같은 SIC 의 60일 수익 중앙).
출력: data/us_scan_full.pkl — us_scan.pkl 과 같은 열 이름(close=수정주가 · rawclose=원주가)
    python build_us_scan_full.py
"""
import gc, glob, sys, time, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd

BASE = Path(__file__).parent; US = BASE / "data" / "us"
if sys.stdout is not None: sys.stdout.reconfigure(encoding="utf-8")
t0 = time.time()
log = lambda m: print("%s %s" % (time.strftime("%H:%M:%S"), m), flush=True)

F = pd.read_pickle(BASE / "data" / "us_full_2007.pkl")
F = F.sort_values(["ticker", "date"]).reset_index(drop=True)
log("원본 %s행 · %d종목" % (f"{len(F):,}", F.ticker.nunique()))
f32 = lambda s: s.astype(np.float32)
df = pd.DataFrame({"date": F.date, "ticker": F.ticker, "grp": F.grp, "sic2": F.sic2})
r = (F.px / F.rawclose).replace([np.inf, -np.inf], np.nan)
df["close"] = f32(F.px); df["rawclose"] = f32(F.rawclose); df["volume"] = F.volume.astype(np.float64)
df["p_high"] = f32(F.high * r); df["p_low"] = f32(F.low * r)
for c in ("buy", "cost", "amt20", "PBR", "부채비율", "marcap", "n5", "n10", "n20", "n40", "n60"):
    df[c] = f32(F[c]) if F[c].dtype != object else F[c]
df["marcap"] = df.marcap * 1e6                       # us_full 은 백만달러 — 옛 us_scan(달러)과 단위를 맞춘다
del F; gc.collect()
g = df.groupby("ticker", sort=False)
px = df.close.astype(np.float64)
log("가격 파생")
df["gap"] = f32((df.buy / px - 1) * 100)
for m in (5, 20, 60, 120):
    ma = g.close.transform(lambda s: s.astype(np.float64).rolling(m, min_periods=m).mean())
    df["dma%d" % m] = f32((px / ma - 1) * 100)
for k in (3, 5, 10, 20, 60, 120, 250):
    df["ret%d" % k] = f32((px / g.close.shift(k) - 1) * 100)
hi250 = g.p_high.transform(lambda s: s.rolling(250, min_periods=60).max()); lo250 = g.p_low.transform(lambda s: s.rolling(250, min_periods=60).min())
df["fromhi"] = f32((px / hi250 - 1) * 100); df["fromlo"] = f32((px / lo250 - 1) * 100)
hi60 = g.p_high.transform(lambda s: s.rolling(60, min_periods=20).max())
df["dd"] = f32((px / hi60 - 1) * 100)
df["mdd60"] = f32(df.dd.groupby(df.ticker).transform(lambda s: s.rolling(60, min_periods=20).min()))
df["vol20"] = f32(g.close.transform(lambda s: s.astype(np.float64).pct_change().rolling(20).std() * 100))
hl = (df.p_high - df.p_low).astype(np.float64)
df["rng"] = f32(hl / px * 100)
df["clv"] = f32(((px - df.p_low) - (df.p_high - px)) / hl.replace(0, np.nan))
df["dev25"] = f32((px / g.close.transform(lambda s: s.astype(np.float64).rolling(25, min_periods=25).mean()) - 1) * 100)
del hi250, lo250, hi60, hl; gc.collect()
log("거래량 축")
df["vm1"] = f32(df.volume)
df["vm3"] = f32(g.volume.transform(lambda s: s.rolling(3).mean()))
df["a40"] = f32(g.volume.transform(lambda s: s.shift(3).rolling(40).mean()))
df["a240"] = f32(g.volume.transform(lambda s: s.shift(43).rolling(240).mean()))
df["r16"] = f32(df.a40 / df.a240 * 100); df["rw1"] = f32(df.vm3 / df.a40 * 100)
df["su1"] = f32(df.vm1 / g.volume.transform(lambda s: s.shift(1).rolling(20).mean()))
ma20 = g.close.transform(lambda s: s.rolling(20).mean())
df["above20"] = f32((df.close > ma20).groupby(df.ticker).transform(lambda s: s.rolling(250, min_periods=80).mean()) * 100)
del ma20; gc.collect()
log("업종(SIC 2자리) · 업종 60일 수익")
df["up"] = np.where(df.sic2.notna(), "SIC" + df.sic2.astype(str).str.replace(r"\.0$", "", regex=True), None)
uu = df.dropna(subset=["up", "ret60"]).groupby(["date", "up"]).ret60.median().rename("u").reset_index()
df = df.merge(uu, on=["date", "up"], how="left"); df["u"] = f32(df.u)
log("재무(PER · 시점 기준 · 살아있는 + 폐지)")
FN = pd.concat([pd.read_pickle(US / "fin.pkl"), pd.read_pickle(US / "fin_dead.pkl")]).dropna(subset=["filed"])
FN = FN.drop_duplicates(["ticker", "filed", "end"], keep="last")
FN["filedn"] = FN.filed.astype(str).str.replace("-", "").astype(np.int64)
# ⚠ SEC eps 는 **회계연도 초부터 누적(YTD)** 이다(KO 2024: 1분기 0.74 · 반기 1.29 · 3분기 1.95 · 연간 2.46).
#   그대로 PER 을 내면 분기 보고 뒤엔 3~4배로 부푼다 → 최근 4분기 합(TTM) = 이번 누적 + 작년 연간 − 작년 같은 시점 누적.
#   회계연도 말 달 = 다음 보고에서 누적이 줄어드는(초기화되는) 일이 가장 잦은 달(종목별 다수결).
def ttm(G):
    G = G.sort_values("end").drop_duplicates("end", keep="last")
    e = pd.to_datetime(G.end.astype(str), format="%Y%m%d", errors="coerce"); y = G.eps.to_numpy(dtype=float)
    m = e.dt.month.to_numpy()
    drop = pd.Series(np.r_[y[1:] < y[:-1], False], index=G.index)
    votes = pd.Series(m)[drop.to_numpy()].value_counts()
    if votes.empty:
        return pd.Series(np.nan, index=G.index)
    fym = votes.idxmax()
    ed = e.to_numpy(); out = np.full(len(G), np.nan)
    for i in range(len(G)):
        if not np.isfinite(y[i]) or pd.isna(ed[i]): continue
        if m[i] == fym: out[i] = y[i]; continue
        prev_fy = [j for j in range(i) if m[j] == fym]
        if not prev_fy: continue
        j = prev_fy[-1]
        same = [k for k in range(i) if abs((ed[i] - ed[k]) / np.timedelta64(1, "D") - 365) <= 25]
        if not same: continue
        out[i] = y[i] + y[j] - y[same[-1]]
    return pd.Series(out, index=G.index)
FN = FN.sort_values(["ticker", "end"])
FN["eps_ttm"] = FN.groupby("ticker", group_keys=False).apply(ttm)
log("  TTM EPS 유효 %.0f%% (원 eps 대비)" % (FN.eps_ttm.notna().sum() / max(FN.eps.notna().sum(), 1) * 100))
d2 = df[["ticker", "date"]].reset_index().assign(daten=lambda x: x.date.astype(np.int64)).sort_values("daten")
M = pd.merge_asof(d2, FN[["ticker", "filedn", "eps_ttm"]].rename(columns={"eps_ttm": "eps"}).dropna(subset=["eps"]).sort_values("filedn"),
                  left_on="daten", right_on="filedn", by="ticker", direction="backward")
eps = pd.Series(M.eps.values, index=M["index"].values).reindex(df.index)
per = df.rawclose / eps.replace(0, np.nan)
df["PER"] = f32(per.where(np.isfinite(per)))
del FN, d2, M, eps, per; gc.collect()
log("공매도(FINRA 2019~)")
fs = sorted(glob.glob(str(US / "finra" / "part_*.pkl")))
if fs:
    S = pd.concat([pd.read_pickle(f) for f in fs], ignore_index=True).drop_duplicates(["ticker", "date"])
    S["short_ratio"] = S.shortvol / S.totvol.replace(0, np.nan) * 100
    df = df.merge(S[["ticker", "date", "short_ratio"]], on=["ticker", "date"], how="left"); del S
    gg = df.groupby("ticker", sort=False)
    df["sr20"] = f32(gg.short_ratio.transform(lambda s: s.rolling(20, min_periods=10).mean()))
    sr5 = gg.short_ratio.transform(lambda s: s.rolling(5, min_periods=3).mean())
    df["srd"] = np.where(df.sr20.notna() & sr5.notna(), sr5 < df.sr20, np.nan); df = df.drop(columns=["short_ratio"])
else:
    df["sr20"] = np.nan; df["srd"] = np.nan
df["mk"] = "US"; df["pref"] = False
df = df.drop(columns=["p_high", "p_low", "sic2"]).sort_values(["ticker", "date"]).reset_index(drop=True)
out = BASE / "data" / "us_scan_full.pkl"
df.to_pickle(out)
log("저장 %s · %s행 · %d열 · %d종목(폐지 %d) · PER 유효 %.0f%% · PBR %.0f%% · %.0f분" % (
    out.name, f"{len(df):,}", len(df.columns), df.ticker.nunique(), df[df.grp == "폐지"].ticker.nunique(),
    df.PER.notna().mean() * 100, df.PBR.notna().mean() * 100, (time.time() - t0) / 60))
