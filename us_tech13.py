# -*- coding: utf-8 -*-
"""이평 교차를 미국 패널에 대입한다 — DaviddTech 'GPT-6 트레이딩 봇' 영상(2026-09-11 사용자 링크).

영상 자체는 **도구 설명**이다. ChatGPT 데스크톱 + TradingView MCP + 브로커 중계를 엮어
AI 가 파인스크립트 전략을 만들고 백테스트하게 하는 법. 구체적 매매 규칙은 두 개뿐이고
가장 크게 자랑한 +3,130% 전략은 **규칙을 공개하지 않는다**(MNTUSDT 한 종목 · 695거래 · PF 1.35).

잴 수 있는 것:
  ① 이평 20/50 골든크로스 — 영상이 연결 확인용으로 쓴 것(BTCUSDT +4.74% · 승률 38% · PF 1.5)
  ② 이웃 기간을 나란히 — [[community-techniques]] 50일선 교훈: 한 쌍만 좋으면 노이즈다
  ③ RSI + MACD — 영상이 '다음 전략' 으로 언급한 조합(국내에선 이미 음수)

국내는 이미 쟀다(44조합 전량 기각). **미국 패널 대입은 처음이다.**

    python us_tech13.py
"""
import sys, time, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
from vp_lib import boot_ci

BASE = Path(__file__).parent; TR1, VA0 = "20221231", "20230101"
def log(m): print(f"{time.strftime('%H:%M:%S')} {m}", flush=True)

log("us_scan.pkl 읽는 중")
K = pd.read_pickle(BASE / "data/us_scan.pkl")
K = K[((~K.pref.fillna(False)) & (K.rawclose >= 3)).fillna(False)]
K = K.sort_values(["ticker", "date"]).reset_index(drop=True)
ud = sorted(K.date.unique()); K["di"] = K.date.map({d: i for i, d in enumerate(ud)}).astype(np.int32)
UNI = (K.groupby("date").amt20.rank(pct=True) >= 0.6).fillna(False)
TK = K.ticker
def G(c): return K.groupby(TK, sort=False)[c]
def roll(c, n): return G(c).transform(lambda s: s.rolling(n, min_periods=n).mean())

log("지표 계산 중")
K["r1"] = G("close").pct_change() * 100
for n in (5, 10, 20, 30, 50, 60, 100, 200):
    K[f"m{n}"] = roll("close", n)
# RSI(14) — 영상이 말한 조합용
up_ = K.r1.clip(lower=0); dn_ = (-K.r1).clip(lower=0)
K["_u"] = up_.groupby(TK).transform(lambda s: s.rolling(14).mean())
K["_d"] = dn_.groupby(TK).transform(lambda s: s.rolling(14).mean())
K["rsi14"] = np.where(K._d <= 0, 100.0, 100 - 100 / (1 + K._u / K._d.replace(0, np.nan)))
# MACD(12,26,9) — 종가 EMA
e12 = G("close").transform(lambda s: s.ewm(span=12, adjust=False).mean())
e26 = G("close").transform(lambda s: s.ewm(span=26, adjust=False).mean())
K["macd"] = e12 - e26
K["sig"] = G("macd").transform(lambda s: s.ewm(span=9, adjust=False).mean())
K["mhist"] = K.macd - K.sig
K["mhistp"] = G("mhist").shift(1)

BEN = {h: K[UNI].dropna(subset=[f"n{h}"]).groupby("date")[f"n{h}"].mean() for h in (5, 20, 40, 60)}
NDAY = len([d for d in ud if d >= "20160101"])
def trim(r):
    r = pd.Series(r).dropna()
    return r[r <= r.quantile(0.95)].mean() if len(r) else np.nan
BT = {h: trim(K[UNI & (K.date >= "20160101")][f"n{h}"].dropna().astype(float)) for h in (5, 20, 40, 60)}
log(f"준비 완료 · {len(K):,}행 · 유니버스 절삭 " + " ".join(f"{h}일 {BT[h]:.2f}" for h in BT))

def dd(cond, h, lo="20160101", hi="20991231"):
    X = K[(cond & UNI).fillna(False)].dropna(subset=[f"n{h}"])
    X = X[(X.date >= lo) & (X.date <= hi)].sort_values("di")
    keep, last = [], {}
    for t, i, ix in zip(X.ticker.values, X.di.values, X.index):
        if last.get(t, -10**9) >= i: continue
        last[t] = i + h; keep.append(ix)
    d = X.loc[keep].copy()
    d["r"] = d[f"n{h}"].astype(float); d["ex"] = d.r - d.date.map(BEN[h]); d["ym"] = d.date.str[:6]
    return d[d.r.notna()]

HDR = (f"  {'조건':<30} {'n':>8} {'동시':>5} {'승률':>6} {'평균':>7} {'중앙':>7} {'절삭Δ':>7} "
       f"{'초과':>7} {'학습':>7} {'검증':>7} {'CI':>7} {'연양수':>7}")
OK = []
def show(tag, cond, h=20):
    d = dd(cond, h)
    if len(d) < 80: print(f"  {tag:<30} {len(d):>8}  (표본 부족)"); return
    yr = d.groupby(d.date.str[:4]).ex.mean(); per = len(d) / NDAY
    ci = boot_ci(d.groupby("ym").ex.mean()); dtm = trim(d.r) - BT[h]
    print(f"  {tag:<30} {len(d):>8,} {per*h:>5.0f} {(d.r>0).mean()*100:>5.1f}% {d.r.mean():>7.2f} "
          f"{d.r.median():>7.2f} {dtm:>7.2f} {d.ex.mean():>7.2f} {d[d.date<=TR1].ex.mean():>7.2f} "
          f"{d[d.date>=VA0].ex.mean():>7.2f} {ci:>7.2f} {int((yr>0).sum()):>4}/{len(yr)}")
    if dtm > 0 and d.ex.mean() > 0 and d[d.date >= VA0].ex.mean() > 0 and ci > 0 and (yr > 0).sum() >= len(yr) * 0.72:
        OK.append((tag, h, len(d), d.ex.mean(), ci, int((yr > 0).sum()), len(yr)))

def cross(a, b):
    """오늘 a 가 b 를 위로 뚫었다(어제는 아래)."""
    return (K[f"m{a}"] > K[f"m{b}"]) & (G(f"m{a}").shift(1) <= G(f"m{b}").shift(1))

W = 140
print("\n" + "=" * W)
print("① 영상이 쓴 그 조합 — 이평 20/50 골든크로스 (미국 · 보유별)")
print("=" * W); print(HDR)
C = cross(20, 50)
for h in (5, 20, 40, 60): show(f"  20/50 교차 · {h}일 보유", C, h)
print()
print("  ── 데드크로스(반대쪽) ──")
DC = (K.m20 < K.m50) & (G("m20").shift(1) >= G("m50").shift(1))
for h in (20, 60): show(f"  20/50 데드크로스 · {h}일", DC, h)

print("\n" + "=" * W)
print("② 이웃 기간을 나란히 — 20/50 이 특별한 숫자인가 (20일 보유)")
print("=" * W); print(HDR)
for a, b in ((5, 20), (10, 30), (10, 50), (20, 50), (20, 60), (20, 100), (50, 100), (50, 200)):
    show(f"  {a}/{b} 골든크로스", cross(a, b))
print("  → 이웃이 다 비슷하면 그 숫자에 정보가 없다는 뜻이다(국내 50일선에서 확인한 것).")

print("\n" + "=" * W)
print("③ 영상이 말한 다음 전략 — RSI + MACD (20일 보유)")
print("=" * W); print(HDR)
MX = (K.mhist > 0) & (K.mhistp <= 0)          # MACD 히스토그램 상향 전환
show("  MACD 상향 교차 단독", MX)
show("  RSI14 < 30 (과매도)", K.rsi14 < 30)
show("  RSI14 > 70 (과매수)", K.rsi14 > 70)
show("  MACD 교차 & RSI<50", MX & (K.rsi14 < 50))
show("  MACD 교차 & RSI>50", MX & (K.rsi14 > 50))
show("  MACD 교차 & RSI<30", MX & (K.rsi14 < 30))
show("  MACD 교차 & 200일선 위", MX & (K.close > K.m200))

print("\n" + "=" * W)
print("④ 집안 잣대 통과 (절삭Δ>0 · 초과>0 · 검증>0 · CI>0 · 연양수 72%↑)")
print("=" * W)
if OK:
    for t, h, n, ex, ci, y, ny in OK:
        print(f"  ✅ {t.strip():<30} {h:>2}일 · {n:>7,}건 · 초과 {ex:+.2f} · CI {ci:+.2f} · 양수해 {y}/{ny}")
else:
    print("  통과 없음")
try:
    import verdict; print("\n누적 시행:", verdict.log_trials("davidtech_gpt6_bot", 25))
except Exception as e: print(e)
