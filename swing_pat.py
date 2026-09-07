# -*- coding: utf-8 -*-
"""유튜브 스윙 전략(Trade with Pat) 실측 — 50EMA 추세 + 3연속 음봉 눌림 + 피보 50% 할인 + 확인 양봉.

전략 원문(2026-09-07 사용자 제공):
  ① 50 EMA 위 = 상승추세, 매수만 노린다
  ② 최소 3개 연속 음봉 = 일시 조정(풀백)
  ③ 피보나치 되돌림 50% 아래 = '할인 구간' 일 때만 진입
  ④ 할인 구간에서 반등을 확인하는 양봉이 뜨면 매수
  ⑤ 보유 24시간~2주(= 1~10거래일)
검증 방식은 우리 표준을 따른다(유튜브 기법은 단독 실측 → 우리 재료와 조합 2단계).
조건을 하나씩 쌓아 각 단계가 실제로 기여하는지 본다 — 마지막 단계만 좋아 보이면 우연일 수 있다.
피보나치는 자동화가 필요해 '최근 창의 고점~저점' 으로 정의하고 창 길이를 20/40/60 으로 바꿔 본다.
판정: 스트레스2005~15(참고)/학습2016~22/검증2023~26 · 중복신호 제거 · 같은 날 유니버스 대비 초과 ·
     월블록 CI 하한 · 중앙값. 매수는 신호 다음날 시가(우리 표준).
"""
import io, os, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
BASE = Path(__file__).parent
HS = [1, 3, 5, 10]                      # 24시간~2주
src = (BASE/"portfolio.py").read_text(encoding="utf-8"); ns = {"__file__": str(BASE/"portfolio.py")}
real = sys.stdout; sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
exec(compile(src.split("# 신호를 한 표로 모은다")[0], "portfolio.py", "exec"), ns)
sys.stdout = real
KP, KQ, base = ns["KP"], ns["KQ"], ns["base"]
for K in (KP, KQ):
    g = K.groupby("ticker", sort=False)
    for h in HS:
        if f"n{h}" not in K.columns: K[f"n{h}"] = (g.close.shift(-h)/K.buy-1)*100 - K.cost
    K["ema50"] = g.close.transform(lambda s: s.ewm(span=50, min_periods=50).mean())
    K["red"]   = K.close < K.open                       # 음봉(영상의 빨간 캔들)
    K["green"] = K.close > K.open                       # 양봉
    r = K.red.astype(int)
    K["red3"] = (r.groupby(K.ticker).shift(1).fillna(0) + r.groupby(K.ticker).shift(2).fillna(0)
                 + r.groupby(K.ticker).shift(3).fillna(0)) >= 3      # 직전 3일 연속 음봉
    for w in (20, 40, 60):
        hi = g.high.transform(lambda s, w=w: s.rolling(w).max())
        lo = g.low.transform(lambda s, w=w: s.rolling(w).min())
        K[f"fib{w}"] = (hi - K.close) / (hi - lo).replace(0, np.nan)  # 되돌림 비율(0=고점, 1=저점)
def uni(K, h): return K.dropna(subset=[f"n{h}"]).groupby("date")[f"n{h}"].mean()
def dedup(X, hold, K):
    di = {x:i for i,x in enumerate(sorted(K.date.unique()))}
    X = X.assign(_di=X.date.map(di)).sort_values("_di"); keep, last = [], {}
    for t,i,ix in zip(X.ticker.values, X._di.values, X.index):
        if last.get(t,-10**9) >= i: continue
        last[t] = i+hold; keep.append(ix)
    return X.loc[keep]
def ci(z, col, n=800, seed=0):
    if len(z) < 8: return float("nan")
    rng = np.random.default_rng(seed); mo = z.date.str[:6].values
    g = [z[col].values[mo == m] for m in np.unique(mo)]; k = len(g)
    return np.percentile([np.concatenate([g[i] for i in rng.integers(0,k,k)]).mean() for _ in range(n)], 5)
def row(lab, K, mask, hs=HS):
    m = mask.fillna(False)
    if m.sum() < 30: print(f"  {lab:<30} 표본 부족({int(m.sum())})"); return
    out = f"  {lab:<30}{int(m.sum()):>8}"
    for h in hs:
        col = f"n{h}"
        Z = dedup(K[m].dropna(subset=[col]), h, K)
        if len(Z) < 20: out += f"{'—':>26}"; continue
        ex = (Z[col] - Z.date.map(uni(K, h))).mean()
        v = Z[Z.date >= "20230101"]
        out += (f"{Z[col].mean():>+6.2f}%({ex:>+5.2f}) "
                f"검증{v[col].mean() if len(v)>=8 else float('nan'):>+5.1f}%{ci(v,col) if len(v)>=8 else float('nan'):>+5.1f} ")
    print(out)
for K, mkt in ((KP,"코스피"), (KQ,"코스닥")):
    print("="*140); print(f"[{mkt}]  숫자 = 전체평균(유니버스 대비 초과) · 검증2023~26 평균·CI하한"); print("="*140)
    print(f"  {'조건 단계':<30}{'신호':>8}" + "".join(f"{'  n'+str(h)+'(1~2주)':>26}" for h in HS))
    b = base(K, 3) & (K.date >= "20160101")
    s1 = b & (K.close > K.ema50)
    s2 = s1 & K.red3
    for w in (20, 40, 60):
        pass
    row("① 50EMA 위", K, s1)
    row("② + 3연속 음봉", K, s2)
    for w in (20, 40, 60):
        s3 = s2 & (K[f"fib{w}"] >= 0.5)
        row(f"③ + 피보 50%↓ (창 {w}일)", K, s3)
        row(f"④ + 확인 양봉 (창 {w}일)", K, s3 & K.green)
    print("  ── 참고: 각 조건 단독 ──")
    row("50EMA 위만", K, s1)
    row("3연속 음봉만", K, b & K.red3)
    row("피보 50%↓만 (창 40)", K, b & (K.fib40 >= 0.5))
    row("양봉만", K, b & K.green)
    print()
