# -*- coding: utf-8 -*-
"""미국 패널 만들기 — 한국 패널(panel_kp/kq)과 같은 컬럼으로 맞춘다.

목적: 한국에서 만든 아홉 규칙의 조건을 **그대로 미국에 대입**할 수 있게 하는 것.
그래서 컬럼 이름·정의를 한국 패널에 최대한 맞춘다. 이름이 다르면 규칙을 옮길 때마다
번역해야 하고 그 과정에서 조건이 조용히 틀어진다.

옮겨지는 재료 / 안 옮겨지는 재료를 처음부터 분명히 해둔다.

  ✅ 가격 파생  ma5/20/60/120 · dma* · ret3/5/10/20/60/120 · hi250/lo250 · fromhi/fromlo
                vol20 · rng · clv · hi60 · dd · mdd60 · su1 · r16 · rw1 · a40 · a240
                amt · amt20 · buy(다음날 시가) · gap · n1~n60(선도수익)
  ✅ 업종       up(업종명) · u(업종 60일 수익률)  ← FDR 상장목록의 Industry
  ✅ 밸류·재무   PBR · PER · BPS · 부채비율  ← SEC XBRL 시점기준(us_fin.py)
  ✅ 시총·주식수 marcap · shares            ← SEC 주식수 × 종가
  ✅ 공매도      sr20 · srd                 ← FINRA 일별 공매도 거래량 (2019~ 만)
  ❌ 수급       frgn/organ/fw5/ow20 …      — 미국은 외국인·기관 일별 순매수 공시가 없다
  ❌ 공시       dil(유상증자·CB) · bb(자사주) · ins60(내부자)
                — EDGAR 8-K/4-K 파싱이 필요. 나중 과제.
  ❌ 신용잔고    cr_chg20                   — 미국은 종목별 일별 공시가 없다

  ⚠ 비용(cost): 한국은 거래세 0.15% + 슬리피지였다. 미국은 거래세가 사실상 없고(SEC 수수료
     0.0028% 수준) 수수료도 0 인 브로커가 많다. 대신 스프레드·슬리피지가 남으므로
     거래대금 구간별로 0.10~0.60% 를 잡는다. 한국보다 낮게 잡되 0 으로 두지 않는다.

출력: data/panel_us.pkl
"""
import io, sys, time, glob, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd

BASE = Path(__file__).parent
US = BASE / "data" / "us"
HS = [1, 2, 3, 4, 5, 7, 10, 12, 15, 20, 25, 30, 40, 50, 60]


def log(m):
    print(f"{time.strftime('%H:%M:%S')} {m}", flush=True)


# ── 1. 원본 조각 합치기 ────────────────────────────────────────────────
files = sorted(glob.glob(str(US / "raw" / "chunk_*.pkl")))
log(f"조각 {len(files)}개 읽는 중")
df = pd.concat([pd.read_pickle(f) for f in files], ignore_index=True)
df = df.drop_duplicates(["ticker", "date"]).sort_values(["ticker", "date"]).reset_index(drop=True)
df = df[df.date >= "20050101"]
log(f"  {df.ticker.nunique():,}종목 · {len(df):,}행 · {df.date.min()}~{df.date.max()}")

# 이상치 정리 — 종가 0 이하, 거래량 음수
df = df[(df.close > 0) & (df.open > 0) & (df.volume >= 0)]
# ⚠ 수정주가(adj)가 0 이하인 종목은 통째로 뺀다(2026-09-12 감사). yfinance 가 adj 계수를
#   음수로 준 종목이 있었다(VATE·CBIO·DEC) — 원주가는 멀쩡한데 수정주가가 -2,788 이라
#   fromhi +527%, n60 -1,007%/inf 가 나왔다. 수익률은 -100% 아래로 갈 수 없다.
_badadj = set(df.loc[df.adj <= 0, "ticker"])
if _badadj:
    log(f"  수정주가 ≤0 종목 {len(_badadj)}개 제거: {sorted(_badadj)[:8]}")
    df = df[~df.ticker.isin(_badadj)]

# ── 2. 수정주가로 통일 ────────────────────────────────────────────────
# yfinance 의 adj 는 배당·분할이 반영된 값이다. 수익 계산은 adj 로 해야 분할일에
# 가짜 폭락이 안 생긴다. 다만 '주가 1달러 이상' 같은 조건은 **원주가**로 봐야 한다.
# 그래서 close(원주가)는 남겨두고, 계산용 가격 px 를 따로 만든다.
r = (df.adj / df.close).replace([np.inf, -np.inf], np.nan)
df["px"] = df.adj
for c in ("open", "high", "low"):
    df["p" + c[0] if c != "open" else "po"] = df[c] * r
df = df.rename(columns={"po": "p_open", "ph": "p_high", "pl": "p_low"})
log("  수정주가 계열(px·p_open·p_high·p_low) 생성")

g = df.groupby("ticker", sort=False)

# ── 3. 가격 파생 — 한국 패널과 같은 정의 ─────────────────────────────
log("가격 파생 계산")
df["buy"] = g.p_open.shift(-1)                       # 다음날 시가에 산다(한국과 동일)
# ⚠ '다음 행' 이 다음 거래일이 아니면(정지·자료 공백) 그 시가에 살 수 없다. 다음날 거래가
#   없어도(volume 0) 못 산다. 한국 패널과 같은 병이었다(2026-09-12 감사: 5,764행).
_ud = sorted(df.date.unique()); _DI = {d: i for i, d in enumerate(_ud)}
_pos = df.date.map(_DI).astype(np.int64)
_nxt = g.date.shift(-1).map(_DI)
_lastpos = g.date.transform("max").map(_DI)
_buybad = ((_nxt - _pos != 1) & (_pos != _lastpos)) | (g.volume.shift(-1).fillna(0) <= 0)
df.loc[_buybad, "buy"] = np.nan
log(f"  매수 불가(공백·다음날 거래량 0) {int(_buybad.sum()):,}행 → buy 결측")
df["gap"] = (df.buy / df.px - 1) * 100
df["amt"] = df.px * df.volume / 1e6                  # 백만달러
df["amt20"] = g.amt.transform(lambda s: s.rolling(20).mean())
for m in (5, 20, 60, 120):
    df[f"ma{m}"] = g.px.transform(lambda s: s.rolling(m, min_periods=m).mean())
    df[f"dma{m}"] = (df.px / df[f"ma{m}"] - 1) * 100
for k in (3, 5, 10, 20, 60, 120):
    df[f"ret{k}"] = (df.px / g.px.shift(k) - 1) * 100
df["hi250"] = g.p_high.transform(lambda s: s.rolling(250, min_periods=60).max())
df["lo250"] = g.p_low.transform(lambda s: s.rolling(250, min_periods=60).min())
df["fromhi"] = (df.px / df.hi250 - 1) * 100
df["fromlo"] = (df.px / df.lo250 - 1) * 100
df["hi60"] = g.p_high.transform(lambda s: s.rolling(60, min_periods=20).max())
df["dd"] = (df.px / df.hi60 - 1) * 100
df["mdd60"] = g.dd.transform(lambda s: s.rolling(60, min_periods=20).min())
df["vol20"] = g.px.transform(lambda s: (s.pct_change().rolling(20).std()) * 100)
df["rng"] = (df.p_high - df.p_low) / df.px * 100
df["clv"] = ((df.px - df.p_low) - (df.p_high - df.px)) / (df.p_high - df.p_low).replace(0, np.nan)
df["dev25"] = (df.px / g.px.transform(lambda s: s.rolling(25, min_periods=25).mean()) - 1) * 100
# 거래량 축 — 한국과 같은 정의
df["vm1"] = df.volume
df["vm3"] = g.volume.transform(lambda s: s.rolling(3).mean())
df["a40"] = g.volume.transform(lambda s: s.shift(3).rolling(40).mean())
df["a240"] = g.volume.transform(lambda s: s.shift(43).rolling(240).mean())
df["r16"] = df.a40 / df.a240 * 100
df["rw1"] = df.vm3 / df.a40 * 100
df["su1"] = df.vm1 / g.volume.transform(lambda s: s.shift(1).rolling(20).mean())
df["y"] = df.date.str[:4]

# ── 4. 비용 ───────────────────────────────────────────────────────────
# 한국: 거래세 0.15% + 유동성별 슬리피지. 미국: 거래세 사실상 없음 → 스프레드·슬리피지만.
df["cost"] = np.select(
    [df.amt20 >= 100, df.amt20 >= 20, df.amt20 >= 5, df.amt20 >= 1],
    [0.10, 0.18, 0.30, 0.45], default=0.60)
log("  비용 모델: 거래대금 구간별 0.10~0.60% (한국 대비 거래세 없음)")

# ── 5. 선도수익 n1~n60 ────────────────────────────────────────────────
for h in HS:
    # 보유 구간이 달력상 h 일과 어긋나거나(공백) 팔 날 거래가 없으면 그 값은 성적이 아니라 결측이다
    _sp = g.date.shift(-h).map(_DI)
    _span = ((_pos + h) <= _lastpos) & (_sp - _pos != h)
    _sv0 = (g.volume.shift(-h).fillna(1) <= 0)
    df[f"n{h}"] = ((g.px.shift(-h) / df.buy - 1) * 100 - df.cost).where(~(_span | _sv0))
log(f"  선도수익 n{HS[0]}~n{HS[-1]} 계산")

# ── 6. 업종 ───────────────────────────────────────────────────────────
T = pd.read_csv(US / "tickers.csv", dtype=str)
df = df.merge(T[["Symbol", "Industry", "mk"]].rename(
    columns={"Symbol": "ticker", "Industry": "up"}), on="ticker", how="left")
# 업종 60일 수익률 u — 같은 업종 종목들의 60일 수익률 중앙값(한국 정의와 맞춤)
uu = df.dropna(subset=["up", "ret60"]).groupby(["date", "up"]).ret60.median().rename("u")
df = df.merge(uu, on=["date", "up"], how="left")
log(f"  업종 {df.up.nunique()}개 · 업종 60일 수익률(u) 병합")

# ── 7. 재무 — 시점 기준 ──────────────────────────────────────────────
fp = US / "fin.pkl"
if fp.exists():
    F = pd.read_pickle(fp)
    F = F.dropna(subset=["equity"]).sort_values(["ticker", "filed"])
    F["filedn"] = F.filed.astype(int)
    d2 = df[["ticker", "date"]].copy()
    d2["daten"] = d2.date.astype(int)
    d2 = d2.sort_values("daten")
    F = F.sort_values("filedn")
    M = pd.merge_asof(d2, F, left_on="daten", right_on="filedn", by="ticker",
                      direction="backward")
    df["equity"] = M.equity.values
    df["assets"] = M.assets.values
    df["liab"] = M.liab.values
    df["shares"] = M.shares.values
    df["eps"] = M.eps.values
    df["marcap"] = df.close * df.shares                  # 원주가 × 주식수
    df["BPS"] = df.equity / df.shares
    df["PBR"] = df.close / df.BPS
    df["PER"] = df.close / df.eps.replace(0, np.nan)
    df["부채비율"] = df.liab / df.equity * 100
    for c in ("PBR", "PER", "부채비율"):
        df.loc[~np.isfinite(df[c]), c] = np.nan
    df.loc[df.PBR <= 0, "PBR"] = np.nan
    log(f"  재무 병합 · PBR 유효 {df.PBR.notna().mean()*100:.0f}% · "
        f"부채비율 {df['부채비율'].notna().mean()*100:.0f}%")
else:
    for c in ("PBR", "PER", "BPS", "부채비율", "marcap", "shares"):
        df[c] = np.nan
    log("  ⚠ data/us/fin.pkl 없음 — 재무 컬럼은 NaN (us_fin.py 를 먼저 돌린다)")

# ── 8. 공매도 — FINRA (2019~) ────────────────────────────────────────
fs = sorted(glob.glob(str(US / "finra" / "part_*.pkl")))
if fs:
    S = pd.concat([pd.read_pickle(f) for f in fs], ignore_index=True)
    S = S.drop_duplicates(["ticker", "date"])
    S["short_ratio"] = S.shortvol / S.totvol.replace(0, np.nan) * 100
    df = df.merge(S[["ticker", "date", "short_ratio"]], on=["ticker", "date"], how="left")
    gg = df.groupby("ticker", sort=False)
    df["sr20"] = gg.short_ratio.transform(lambda s: s.rolling(20, min_periods=10).mean())
    sr5 = gg.short_ratio.transform(lambda s: s.rolling(5, min_periods=3).mean())
    # ⚠ NaN < NaN 은 False 가 되어 '유효 100%' 로 보인다. 실제로 잰 날만 True/False 로 둔다.
    df["srd"] = np.where(df.sr20.notna() & sr5.notna(), sr5 < df.sr20, np.nan)
    log(f"  공매도 병합 {len(S):,}행 · sr20 유효 {df.sr20.notna().mean()*100:.0f}%")
else:
    df["short_ratio"] = df["sr20"] = np.nan
    df["srd"] = np.nan
    log("  ⚠ FINRA 없음 — 공매도 컬럼은 NaN")

# ── 9. 한국에 있지만 미국엔 없는 것 — 자리만 만들어 둔다 ────────────
# 규칙 조건이 이 이름을 참조하면 KeyError 로 죽는다. NaN 으로 두면
# '결측이면 통과' 인 조건은 통과하고 '결측이면 탈락' 인 조건은 탈락한다.
for c in ("frgn", "organ", "fw5", "ow5", "fw20", "ow20", "fw60", "ow60",
          "dil", "bb", "ins60", "cr_chg20", "above20", "ret250"):
    if c not in df.columns:
        df[c] = np.nan
df["pref"] = False                                       # 미국은 우선주를 티커에서 이미 걸렀다
df["grp"] = "생존"                                        # 폐지 종목은 yfinance 가 거의 안 준다
g = df.groupby("ticker", sort=False)
df["ret250"] = (df.px / g.px.shift(250) - 1) * 100
ma20 = g.px.transform(lambda s: s.rolling(20).mean())
df["above20"] = (df.px > ma20).groupby(df.ticker).transform(
    lambda s: s.rolling(250, min_periods=80).mean()) * 100

p = BASE / "data" / "panel_us.pkl"
df.to_pickle(p)
log(f"저장 {p.name} · {len(df):,}행 · {len(df.columns)}컬럼 · {df.ticker.nunique():,}종목")
print()
print("  ── 한국 규칙을 옮길 때 쓸 수 있는 재료 ──")
for c in ("PBR", "PER", "부채비율", "marcap", "u", "sr20", "srd", "amt20",
          "dma20", "dev25", "fromhi", "mdd60", "su1", "r16", "rw1", "vol20"):
    if c in df.columns:
        print(f"    {c:<10}유효 {df[c].notna().mean()*100:>5.1f}%")
print("  ── 미국에 없어 NaN 인 재료 ──")
print("    frgn·organ·fw*·ow*(수급) · dil(증자공시) · bb(자사주) · ins60(내부자) · cr_chg20(신용)")
