# -*- coding: utf-8 -*-
"""공탐 지수 전환 신호 — 문턱 30/20, 공포 탈출과 탐욕 붕괴 양방향.

앞선 실측(fg_escape.py)에서 '공탐 30 미만 30일 → 30 돌파 2일' 은 기각됐다(중앙값 음수·CI 음수·
유니버스 대비 초과 없음). 사용자 요청으로 두 가지를 더 본다.
  A) 문턱을 20 으로 낮춘다 — 더 깊은 공포에서의 탈출이면 다를까
  B) 반대 방향 — 탐욕(≥th)을 오래 끌다가 그 아래로 무너지는 순간
     · 매수 신호로도 재고(반등 기대), '회피·매도 신호' 인지도 본다(수익률이 음수면 그게 값어치)
판정은 앞과 같다: 스트레스2005~15(참고)/학습2016~22/검증2023~26 · 중복제거 · 유니버스 대비 초과 ·
월블록 CI 하한 · 중앙값. 문턱 th 는 '높음/낮음' 의 경계로만 쓰고 방향만 뒤집는다.
"""
import io, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
BASE = Path(__file__).parent
HS = [5, 10, 20, 40, 60]
def load(mk, mkt):
    cols = ["ticker","date","close","buy","cost","amt20"] + [f"n{h}" for h in HS]
    K = pd.read_pickle(BASE/"data"/f"panel_{mk}.pkl")
    K = K[[c for c in cols if c in K.columns]].copy(); K["mk"] = mkt
    K["pref"] = ~K.ticker.str.endswith("0")
    F = pd.read_pickle(BASE/"data"/f"stock_fg_{mk}.pkl")[["ticker","date","fg"]]
    n0 = len(K); K = K.merge(F, on=["ticker","date"], how="left"); assert len(K) == n0
    return K.sort_values(["ticker","date"]).reset_index(drop=True)
KP, KQ = load("kp","KOSPI"), load("kq","KOSDAQ")

def runlen(t, flag):
    out = np.zeros(len(flag), dtype=np.int32); c = 0; prev = None
    for i in range(len(flag)):
        if t[i] != prev: c = 0; prev = t[i]
        c = c + 1 if flag[i] else 0
        out[i] = c
    return out
def signals(K, hold_n, cross_m, th, direction):
    """direction='escape': fg<th 를 hold_n 일 → fg>=th 가 cross_m 일
       direction='break' : fg>=th 를 hold_n 일 → fg<th 가 cross_m 일"""
    t = K.ticker.values
    lo = (K.fg < th).fillna(False).values; hi = (K.fg >= th).fillna(False).values
    a, b = (lo, hi) if direction == "escape" else (hi, lo)
    ra, rb = runlen(t, a), runlen(t, b)
    prev = pd.Series(ra).groupby(K.ticker.values).shift(cross_m).fillna(0).values
    return (rb == cross_m) & (prev >= hold_n)
def dedup(X, hold):
    d = sorted(X.date.unique()); di = {x: i for i, x in enumerate(d)}
    X = X.assign(_di=X.date.map(di)).sort_values("_di")
    keep, last = [], {}
    for tk, i, ix in zip(X.ticker.values, X._di.values, X.index):
        if last.get(tk, -10**9) >= i: continue
        last[tk] = i + hold; keep.append(ix)
    return X.loc[keep]
def ci(z, n=1200, seed=0):
    if len(z) < 8: return float("nan")
    rng = np.random.default_rng(seed); mo = z.date.str[:6].values
    g = [z._r.values[mo == m] for m in np.unique(mo)]; k = len(g)
    return np.percentile([np.concatenate([g[i] for i in rng.integers(0,k,k)]).mean() for _ in range(n)], 5)
def cell(z):
    return (f"{len(z):>4}건{z._r.mean():>+6.1f}%{z._r.median():>+6.1f}{(z._r>0).mean()*100:>4.0f}%{ci(z):>+6.1f}"
            if len(z) >= 5 else f"{'—':>25}")
UNI = {}
def run(K, mkt, th, direction, hold_n=30, cross_m=2):
    sig = signals(K, hold_n, cross_m, th, direction)
    S = K[sig]; S = S[(~S.pref) & (S.close >= 1000) & (S.amt20.fillna(0) >= 3)]
    if len(S) < 20: print(f"  {mkt} 문턱{th} {direction}: 신호 부족({len(S)})"); return
    for h in HS:
        col = f"n{h}"
        Z = dedup(S.dropna(subset=[col]).assign(_r=lambda d: d[col]), h)
        key = (mkt, h)
        if key not in UNI: UNI[key] = K.dropna(subset=[col]).groupby("date")[col].mean()
        Z["_ex"] = Z._r - Z.date.map(UNI[key])
        a = Z[(Z.date>="20160101")&(Z.date<="20221231")]; b = Z[Z.date>="20230101"]
        s = Z[Z.date<="20151231"]; base = Z[Z.date>="20160101"]
        print(f"  {h:>3}일{cell(s):>25}{cell(a):>25}{cell(b):>25}{base._ex.mean() if len(base) else float('nan'):>+9.2f}%")
HDR = f"  {'매도':<5}{'스트레스2005~15':>25}{'학습2016~22':>25}{'검증2023~26':>25}{'초과':>9}"
for th in (30, 20):
    for direction, label in (("escape", f"공포 탈출 — fg<{th} 30일 이상 → fg≥{th} 2일 연속"),
                             ("break",  f"탐욕 붕괴 — fg≥{th} 30일 이상 → fg<{th} 2일 연속")):
        print("\n" + "="*116); print(f"문턱 {th} · {label}"); print("="*116)
        for K, mkt in ((KP,"코스피"), (KQ,"코스닥")):
            n = int(signals(K, 30, 2, th, direction).sum())
            print(f"\n[{mkt}] 원신호 {n:,}건"); print(HDR)
            run(K, mkt, th, direction)
