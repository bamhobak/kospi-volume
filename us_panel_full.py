# -*- coding: utf-8 -*-
"""생존편향 없는 미장 패널 — 지금 상장 종목 + Tiingo 폐지 종목 (2026-09-23).

기존 panel_us.pkl 은 **지금 상장된 종목만**으로 과거를 거슬러 만든 판이다([[lookahead-surv]]).
여기에 Tiingo 에서 받은 폐지 종목(collect_tiingo_dead.py)을 넣고, 미장 규칙 N1~N5 가 쓰는 재료만
**같은 계산식으로** 만든다. 사이트용 패널은 건드리지 않는다(출력 파일이 다르다).

폐지 종목에서만 터지는 함정 둘을 고친다 — **두 집단 모두 같은 규칙**을 쓴다(그래야 비교가 공정하다):
  ① 거래정지 중 청산: 옛 코드는 파는 날 거래량이 0 이면 그 거래를 결측으로 버렸다. SVB 는 2023-03-09
     $106 에서 정지돼 03-28 장외 $0.40 으로 재개됐는데, 그 사이에 끝나는 거래가 통째로 빠졌다 —
     제일 큰 손실이 제일 먼저 사라진다. → 목표일 **이후 처음 거래된 날** 가격에 판다.
  ② 폐지 후 청산: 보유 기간이 그 종목의 마지막 거래일을 넘으면 결측이었다. 인수 폐지(트위터)의
     마지막 가격은 실제로 받은 돈이다. → **끝난 종목은 마지막 거래 가격에 청산**(국내 build_panel 과 같다).
     아직 살아 있는 종목이 패널 끝을 넘는 건 덜 끝난 거래라 그대로 결측.

업종: 두 집단 모두 **SEC SIC 2자리**로 통일한다. 기존 업종표(FDR)는 현재 상장사뿐이라 폐지 종목엔 없다.
      업종 60일 수익률(u)은 비교하려는 집단마다 따로 계산해야 하므로 여기선 ret60·sic2 만 남긴다.
재무: 생존 fin.pkl + 폐지 fin_dead.pkl — 둘 다 SEC companyfacts · 최초 공시값 · filed 시점 기준.

폐지 종목 이름은 `티커^D` (389개가 지금 우리 종목과 같은 티커를 쓴다 — 다른 회사다).
대상: A(거래소 폐지) · B(장외 파산주). C(장외 일반)는 넣지 않는다 — 옛 상장사와 외국 장외 종목을
      가를 수 없어서다(--with-c 로 회사번호가 맞은 C 만 넣어 볼 수 있다).

출력: data/us_full.pkl
    python us_panel_full.py
"""
import glob, json, sqlite3, sys, time, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd

BASE = Path(__file__).parent
US = BASE / "data" / "us"
START = sys.argv[sys.argv.index("--from") + 1] if "--from" in sys.argv else "20140601"   # 2016~ 규칙에 250일·a240(283일) 이력이 필요하다
OUTP = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else "us_full.pkl"
HS = [5, 10, 20, 40, 60]
t0 = time.time()


def log(m):
    print(f"{time.strftime('%H:%M:%S')} {m}", flush=True)


# ── 1. 원본 ───────────────────────────────────────────────────────────
log("생존 종목 원본 읽는 중")
S = pd.concat([pd.read_pickle(f) for f in sorted(glob.glob(str(US / "raw" / "chunk_*.pkl")))], ignore_index=True)
S = S[S.date >= START].drop_duplicates(["ticker", "date"])
S["grp"] = "생존"
log(f"  생존 {S.ticker.nunique():,}종목 · {len(S):,}행")

log("폐지 종목 원본 읽는 중 (tiingo_dead.db)")
c = sqlite3.connect(f"file:{US / 'tiingo_dead.db'}?mode=ro", uri=True, timeout=600)
grps = ("A", "B", "C") if "--with-c" in sys.argv else ("A", "B")
D = pd.read_sql(f"""select p.ticker, p.date, p.open, p.high, p.low, p.close, p.adjClose as adj, p.volume
                    from px p join meta m using(ticker)
                    where m.grp in ({','.join('?' * len(grps))}) and p.date >= ?""", c, params=(*grps, START))
if "--with-c" in sys.argv:
    cm = pd.read_pickle(US / "tiingo_cik.pkl")
    okc = set(cm[cm.cik.notna()].ticker)
    grp = pd.read_sql("select ticker, grp from meta", c).set_index("ticker").grp
    D = D[(D.ticker.map(grp) != "C") | D.ticker.isin(okc)]
c.close()
D["ticker"] = D.ticker + "^D"
D["grp"] = "폐지"
log(f"  폐지 {D.ticker.nunique():,}종목 · {len(D):,}행")

df = pd.concat([S, D], ignore_index=True)
del S, D
df = df[(df.close > 0) & (df.open > 0) & (df.volume >= 0) & (df.adj > 0)]
df = df.sort_values(["ticker", "date"]).reset_index(drop=True)
for col in ("open", "high", "low", "close", "adj", "volume"):
    df[col] = df[col].astype("float64")

# ── 2. 수정주가 계열 (us_panel.py 와 같다) ────────────────────────────
r = (df.adj / df.close).replace([np.inf, -np.inf], np.nan)
df["px"] = df.adj
df["p_open"], df["p_high"], df["p_low"] = df.open * r, df.high * r, df.low * r
g = df.groupby("ticker", sort=False)

# ── 3. 매수 가능·파생 (us_panel.py 와 같다) ──────────────────────────
ud = sorted(df.date.unique()); DI = {d: i for i, d in enumerate(ud)}
df["pos"] = df.date.map(DI).astype(np.int32)
df["buy"] = g.p_open.shift(-1)
_nxt = g.pos.shift(-1)
_lastpos = g.pos.transform("max")
_buybad = ((_nxt - df.pos != 1) & (df.pos != _lastpos)) | (g.volume.shift(-1).fillna(0) <= 0)
df.loc[_buybad, "buy"] = np.nan
df["amt"] = df.px * df.volume / 1e6
df["amt20"] = g.amt.transform(lambda s: s.rolling(20).mean())
df["ret20"] = (df.px / g.px.shift(20) - 1) * 100
df["ret60"] = (df.px / g.px.shift(60) - 1) * 100
df["a240"] = g.volume.transform(lambda s: s.shift(43).rolling(240).mean())
df["su1"] = df.volume / g.volume.transform(lambda s: s.shift(1).rolling(20).mean())
df["cost"] = np.select([df.amt20 >= 100, df.amt20 >= 20, df.amt20 >= 5, df.amt20 >= 1],
                       [0.10, 0.18, 0.30, 0.45], default=0.60)
log("  가격 파생 완료")

# ── 4. 선도수익 — 고친 청산 규칙 ─────────────────────────────────────
# 끝난 종목: 마지막 거래일이 패널 끝보다 10거래일 넘게 앞선다
END_ALIVE = len(ud) - 1 - 10
pos = df.pos.values
vol = df.volume.values
px = df.px.values
starts = np.r_[0, np.flatnonzero(df.ticker.values[1:] != df.ticker.values[:-1]) + 1]
ends = np.r_[starts[1:], len(df)]
for h in HS:
    sell = np.full(len(df), np.nan)
    for a, b in zip(starts, ends):
        tp = pos[a:b]
        tr = vol[a:b] > 0
        ptr, xtr = tp[tr], px[a:b][tr]
        if not len(ptr):
            continue
        k = np.searchsorted(ptr, tp + h, "left")          # 목표일 이후 처음 거래된 날
        ok = k < len(ptr)
        out = np.full(b - a, np.nan)
        out[ok] = xtr[k[ok]]
        if ptr[-1] < END_ALIVE:                           # 끝난 종목 → 마지막 거래 가격에 청산
            late = ~ok & (ptr[-1] > tp)
            out[late] = xtr[-1]
        sell[a:b] = out
    df[f"n{h}"] = (sell / df.buy - 1) * 100 - df.cost
    log(f"  n{h} 완료")

# ── 5. 업종 SIC 2자리 ────────────────────────────────────────────────
sec = pd.read_pickle(US / "sec_cik.pkl")
sic = dict(zip(sec.cik, sec.sic.astype(str).str[:2]))
ct = json.load(open(US / "company_tickers.json", encoding="utf-8"))
t2c = {}
for v in ct.values():
    t2c.setdefault(str(v["ticker"]).upper(), int(v["cik_str"]))
cm = pd.read_pickle(US / "tiingo_cik.pkl")
cm = cm[cm.cik.notna()]
t2c.update({t + "^D": int(k) for t, k in zip(cm.ticker, cm.cik)})
tk = pd.Series(df.ticker.unique())
df["cik"] = df.ticker.map(dict(zip(tk, tk.map(t2c))))
df["sic2"] = df.cik.map(sic)
cov = df.groupby("grp").sic2.apply(lambda s: s.notna().mean() * 100)
log("  업종(SIC) 채움률 " + " · ".join(f"{k} {v:.0f}%" for k, v in cov.items()))

# ── 6. 재무 — 시점 기준 (us_panel.py 와 같은 계산) ───────────────────
F = pd.concat([pd.read_pickle(US / "fin.pkl"), pd.read_pickle(US / "fin_dead.pkl")], ignore_index=True)
F = F.dropna(subset=["equity"]).copy()
F["filedn"] = F.filed.astype(int)
d2 = df[["ticker", "date"]].copy()
d2["daten"] = d2.date.astype(int)
d2["_i"] = np.arange(len(d2))
M = pd.merge_asof(d2.sort_values("daten"), F.sort_values("filedn")[["ticker", "filedn", "equity", "liab", "shares", "ni"]],
                  left_on="daten", right_on="filedn", by="ticker", direction="backward").sort_values("_i")
bps = M.equity.values / M.shares.values
df["PBR"] = df.close / bps
df["부채비율"] = M.liab.values / M.equity.values * 100
# 조정안 실험용(2026-09-24): 시가총액(원주가 × 주식수, 백만$)과 최근 공시 순이익 부호
df["marcap"] = df.close * M.shares.values / 1e6
df["ni_pos"] = np.where(np.isfinite(M.ni.values), (M.ni.values > 0).astype(float), np.nan)
df.loc[~np.isfinite(df.marcap) | (df.marcap <= 0), "marcap"] = np.nan
for col in ("PBR", "부채비율"):
    df.loc[~np.isfinite(df[col]), col] = np.nan
df.loc[df.PBR <= 0, "PBR"] = np.nan
cov = df.groupby("grp").PBR.apply(lambda s: s.notna().mean() * 100)
log("  재무 병합 · PBR 채움률 " + " · ".join(f"{k} {v:.0f}%" for k, v in cov.items()))

# ── 저장 ─────────────────────────────────────────────────────────────
KEEP = ["ticker", "date", "grp", "high", "low", "close", "volume", "px", "buy", "cost", "amt20", "a240",
        "su1", "ret20", "ret60", "PBR", "부채비율", "marcap", "ni_pos", "sic2"] + [f"n{h}" for h in HS]
out = df[KEEP].rename(columns={"close": "rawclose"})
for col in out.columns:
    if out[col].dtype == np.float64:
        out[col] = out[col].astype("float32")
out.to_pickle(BASE / "data" / OUTP)
log(f"저장 data/{OUTP} · {len(out):,}행 · 생존 {out[out.grp == '생존'].ticker.nunique():,} · "
    f"폐지 {out[out.grp == '폐지'].ticker.nunique():,}종목 · {(time.time() - t0) / 60:.1f}분")
