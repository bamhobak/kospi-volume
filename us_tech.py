# -*- coding: utf-8 -*-
"""미국에서 만들어진 매매법을 **미국 데이터**로 대입한다.

왜 지금 하나: 2026-09-02 에 해외 기법 36종을 쟀는데 그때는 미국 패널이 없어서
**전부 한국 패널에 대입**했다([[community-techniques]]). 결론이 "미국 캘린더 아노말리는
한국서 역방향" 이었는데, 그건 기법이 틀렸다는 증거가 아니라 **다른 시장에 옮겼다는 증거**다.
지금은 미국 패널(1,704만 행 · 2005~)이 있으니 제 고향에서 재는 게 맞다.

목록 출처: 웹 검색(Connors RSI2 · Quantified Strategies · Double Seven) +
GitHub sofus-nl/swing-trading-strategies 16종(VCP · Qullamaggie · Minervini 추세템플릿 ·
Donchian/Turtle · MA stack · Frog-in-the-Pan · ROC · Multi-period momentum).
우리 규칙과 겹치는 것(52주 고점 눌림 ≈ [상승장 신고가])은 뺐고,
고가·저가 시계열이 필요한 ADX 는 슬림 캐시에 없어 뺐다.

판정: n{h} 가 이미 익일 시가 매수 · 비용차감이다. 여기에
     중복제거 · 거래대금 상위 40% · $3 이상 · 우선주 제외
     · 같은날 유니버스 대비 초과 · 학습 2016~22 / 검증 2023~26 / 스트레스 2005~15
     · 월블록 CI · 중앙값 · 상위5% 절삭평균 · 연도별 양수 개수

    python us_tech.py
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
TK = K.ticker                                  # 열을 더할 때마다 새로 묶는다(묵은 groupby 함정)
def G(c): return K.groupby(TK, sort=False)[c]
def roll(c, n, how="mean"):
    return G(c).transform(lambda s: getattr(s.rolling(n, min_periods=n), how)())

log("지표 계산 중")
K["r1"] = G("close").pct_change() * 100
for n in (10, 21, 50, 150, 200):
    K[f"ma{n}"] = roll("close", n)
K["ma200p"] = G("ma200").shift(21)
K["up200"] = K.close > K.ma200
# Connors RSI(2) — 2일 상승분 평균 ÷ 하락분 평균
K["_u2"] = G("r1").transform(lambda s: s.clip(lower=0).rolling(2).mean())
K["_d2"] = G("r1").transform(lambda s: (-s).clip(lower=0).rolling(2).mean())
K["rsi2"] = np.where(K._d2 <= 0, 100.0, 100 - 100 / (1 + K._u2 / K._d2.replace(0, np.nan)))
for n in (7, 20, 55):
    K[f"lo{n}"] = roll("close", n, "min"); K[f"hi{n}"] = roll("close", n, "max")
K["r1p1"] = G("r1").shift(1); K["r1p2"] = G("r1").shift(2)
K["down3"] = (K.r1 < 0) & (K.r1p1 < 0) & (K.r1p2 < 0)
K["nr7"] = K.rng <= roll("rng", 7, "min")      # rng = (고-저)/종가 · 7일 최소폭
K["vsq"] = K.vol20 <= roll("vol20", 60) * 0.7  # VCP 근사 — 변동성 수축
K["stk"] = ((K.close > K.ma10) & (K.ma10 > K.ma21) & (K.ma21 > K.ma50)
              & (K.ma50 > K.ma200) & (K.ma200 > K.ma200p))
K["miner"] = ((K.close > K.ma150) & (K.close > K.ma200) & (K.ma150 > K.ma200)
              & (K.ma200 > K.ma200p) & (K.fromhi >= -25) & (K.fromlo >= 30))
K["multi"] = (K.ret60 > 0) & (K.ret120 > 0) & (K.ret250 > 0)
K["absr"] = G("r1").transform(lambda s: s.abs().rolling(60).mean())   # Frog-in-the-Pan 이산성
_dt = pd.to_datetime(K.date, format="%Y%m%d")
K["dow"] = _dt.dt.dayofweek; K["dom"] = _dt.dt.day; K["mon"] = _dt.dt.month
_nd = pd.Series(ud)
_gap = (pd.to_datetime(_nd.shift(-1), format="%Y%m%d") - pd.to_datetime(_nd, format="%Y%m%d")).dt.days
K["prehol"] = K.date.isin(set(_nd[_gap >= 4]))                       # 다음 거래일까지 4일↑ = 연휴 전날
HS = (5, 20, 40)
BEN = {h: K[UNI].dropna(subset=[f"n{h}"]).groupby("date")[f"n{h}"].mean() for h in HS}
NDAY = len([d for d in ud if d >= "20160101"])
log(f"준비 완료 · {len(K):,}행 · 유니버스 {int(UNI.sum()):,}행")

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

HDR = (f"  {'기법':<32} {'n':>7} {'일':>6} {'승률':>6} {'평균':>7} {'중앙':>7} {'절삭':>7} {'초과':>7} "
       f"{'학습':>7} {'검증':>7} {'스트':>7} {'CI':>7} {'연양수':>7}")
OK = []; NTRY = [0]
def show(tag, cond, h=5):
    NTRY[0] += 1
    d = dd(cond, h)
    if len(d) < 80: print(f"  {tag:<32} {len(d):>7}  (표본 부족)"); return
    st = dd(cond, h, lo="20050101", hi="20151231")
    tr = d[d.date <= TR1]; va = d[d.date >= VA0]
    ci = boot_ci(d.groupby("ym").ex.mean()); yr = d.groupby(d.date.str[:4]).ex.mean()
    trim = d.r[d.r <= d.r.quantile(0.95)].mean()
    stx = st.ex.mean() if len(st) >= 80 else np.nan
    print(f"  {tag:<32} {len(d):>7,} {len(d)/NDAY:>6.2f} {(d.r>0).mean()*100:>5.1f}% {d.r.mean():>7.2f} "
          f"{d.r.median():>7.2f} {trim:>7.2f} {d.ex.mean():>7.2f} {tr.ex.mean():>7.2f} {va.ex.mean():>7.2f} "
          f"{stx:>7.2f} {ci:>7.2f} {int((yr>0).sum()):>4}/{len(yr)}")
    # 집안 잣대: 중앙값>0 · 절삭평균>0 · 초과>0 · 검증>0 · CI>0 · 연양수 72%↑
    if (d.r.median() > 0 and trim > 0 and d.ex.mean() > 0 and va.ex.mean() > 0
            and ci > 0 and (yr > 0).sum() >= len(yr) * 0.72):
        OK.append((tag, h, len(d), d.ex.mean(), va.ex.mean(), ci, int((yr > 0).sum()), len(yr)))

W = 158
print("\n" + "=" * W); print("① 평균회귀 계열 (5일 보유)"); print("=" * W); print(HDR)
show("Connors RSI2<10 & 200일선 위", (K.rsi2 < 10) & K.up200)
show("Connors RSI2<5 & 200일선 위", (K.rsi2 < 5) & K.up200)
show("Connors RSI2<10 (필터 없음)", K.rsi2 < 10)
show("Connors RSI2>90 (반대쪽 확인)", (K.rsi2 > 90) & K.up200)
show("IBS 종가위치<0.2 & 200일선 위", (K.clv < 0.2) & K.up200)
show("IBS<0.2 (필터 없음)", K.clv < 0.2)
show("IBS<0.1 & 200일선 위", (K.clv < 0.1) & K.up200)
show("Double Seven(7일최저·200위)", (K.close <= K.lo7) & K.up200)
show("3연속 음봉 & 200일선 위", K.down3 & K.up200)
show("NR7 다음날", K.nr7)
show("NR7 & 200일선 위", K.nr7 & K.up200)
print()
show("하루 -10% 폭락 익일", K.r1 <= -10)
show("하루 -15~-20% 폭락 익일", (K.r1 <= -15) & (K.r1 > -20))
show("하루 -20% 이하 폭락 익일", K.r1 <= -20)
show("-15%↓ 폭락 & 200일선 위", (K.r1 <= -15) & K.up200)

print("\n" + "=" * W); print("② 추세·모멘텀 계열 (20일 보유)"); print("=" * W); print(HDR)
FROG = K.multi & (K.ret250 >= 50) & (K.absr <= 1.5)
QM = K.stk & (K.ret60 >= 30)
show("Donchian 20일 신고가", K.close >= K.hi20, h=20)
show("Donchian 55일 신고가", K.close >= K.hi55, h=20)
show("이평 정배열 10>21>50>200", K.stk, h=20)
show("Minervini 추세 템플릿", K.miner, h=20)
show("3·6·12개월 전부 양수", K.multi, h=20)
show("Frog-in-the-Pan(1년↑·잔잔)", FROG, h=20)
show("ROC 가속(20일 > 60일/3)", (K.ret20 > K.ret60 / 3) & (K.ret60 > 0), h=20)
show("Qullamaggie(정배열·ret60 30↑)", QM, h=20)
show("VCP 근사(정배열·변동성 수축)", K.stk & K.vsq, h=20)
show("Minervini + 변동성 수축", K.miner & K.vsq, h=20)
print()
print("  ── 같은 조건 40일 보유 ──")
for nm, c in (("Donchian 20일", K.close >= K.hi20), ("이평 정배열", K.stk),
              ("Minervini 템플릿", K.miner), ("Frog-in-the-Pan", FROG),
              ("Qullamaggie", QM), ("VCP 근사", K.stk & K.vsq)):
    show(f"  {nm}", c, h=40)

print("\n" + "=" * W)
print("③ 집안 잣대 통과 (중앙값>0 · 절삭>0 · 초과>0 · 검증>0 · CI>0 · 연양수 72%↑)")
print("=" * W)
if OK:
    for t, h, n, ex, va, ci, y, ny in OK:
        print(f"  ✅ {t:<32} {h:>2}일 · {n:>6,}건 · 초과 {ex:+.2f} · 검증 {va:+.2f} · CI {ci:+.2f} · 양수해 {y}/{ny}")
else:
    print("  통과 없음")
try:
    import verdict; print("\n누적 시행:", verdict.log_trials("us_tech_web", NTRY[0]))
except Exception as e: print(e)
