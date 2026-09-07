# -*- coding: utf-8 -*-
"""공탐 밴드 매매 격자 — '공탐 L 이하로 내려오면 사서 H 이상 되면 판다' 를 전 조합 훑는다.

사용자 요청(2026-09-07): "공탐지수 20에서 50 이라든지 50에서 80 이라든지" 다른 각도로.
  · 매수: 공탐이 L 위에서 아래로 처음 내려온 날(크로스) 다음날 시가
  · 매도: 그 뒤 공탐이 H 이상 되는 첫날 종가. 못 닿으면 MAXHOLD 거래일에 강제 청산.
  · L ∈ {10,15,20,25,30,40,50} × H ∈ {30,40,50,60,70,80}, H>L 인 조합 전부.
벤치마크가 핵심이다 — 보유기간이 조합마다 다르므로, 같은 시장 유니버스의 '같은 기간' 누적수익을
따로 계산해 초과분을 본다(지수와 비교하지 않는다). 그래야 '오래 들고 있어서 번 것' 을 걸러낸다.
판정: 검증2023~26 의 중앙값>0 · CI하한>0 · 초과>0 을 동시에 만족해야 후보다.
"""
import io, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
BASE = Path(__file__).parent
MAXHOLD = 120
LS = [10, 15, 20, 25, 30, 40, 50]
HS = [30, 40, 50, 60, 70, 80]

def load(mk, mkt):
    K = pd.read_pickle(BASE/"data"/f"panel_{mk}.pkl")[["ticker","date","close","buy","cost","amt20"]].copy()
    K["pref"] = ~K.ticker.str.endswith("0")
    F = pd.read_pickle(BASE/"data"/f"stock_fg_{mk}.pkl")[["ticker","date","fg"]]
    n0 = len(K); K = K.merge(F, on=["ticker","date"], how="left"); assert len(K) == n0
    K = K.sort_values(["ticker","date"]).reset_index(drop=True)
    # 유니버스 누적지수 — 같은 기간 '아무 종목이나' 들고 있었을 때의 성적
    g = K.groupby("ticker", sort=False)
    K["_r1"] = g.close.pct_change()
    m = K[(K.close >= 1000)].groupby("date")._r1.mean()
    cum = (1 + m.fillna(0)).cumprod()
    return K, cum

def scan(K, cum, L, H, maxhold=MAXHOLD):
    fg = K.fg.values; cl = K.close.values; bu = K.buy.values; co = K.cost.values
    dt = K.date.values; ok = ((~K.pref) & (K.close >= 1000) & (K.amt20.fillna(0) >= 3)).values
    rows = []
    for tk, ii in K.groupby("ticker", sort=False).indices.items():
        f = fg[ii]; n = len(ii)
        bel = np.zeros(n, bool); bel[~np.isnan(f)] = f[~np.isnan(f)] < L
        cross = np.where(bel[1:] & ~bel[:-1])[0] + 1            # 위→아래 크로스
        if not len(cross): continue
        hs = np.where((~np.isnan(f)) & (f >= H))[0]
        for c in cross:
            gi = ii[c]
            if not ok[gi] or not (bu[gi] == bu[gi]) or bu[gi] <= 0: continue
            p = np.searchsorted(hs, c+1)
            forced = not (p < len(hs) and hs[p] - c <= maxhold)
            j = min(c+maxhold, n-1) if forced else hs[p]
            if j <= c: continue
            gj = ii[j]
            r = (cl[gj]/bu[gi]-1)*100 - co[gi]
            b0, b1 = cum.get(dt[gi]), cum.get(dt[gj])
            bm = (b1/b0-1)*100 if (b0 and b1 and b0 == b0 and b1 == b1) else np.nan
            rows.append((tk, dt[gi], r, r-bm if bm == bm else np.nan, j-c, forced))
    X = pd.DataFrame(rows, columns=["ticker","date","_r","_ex","held","forced"])
    if not len(X): return X
    X = X.sort_values("date"); keep, until = [], {}
    for tk, d, ix in zip(X.ticker.values, X.date.values, X.index):
        if until.get(tk, "") >= d: continue
        keep.append(ix); until[tk] = d
    return X.loc[keep]

def ci(z, n=800, seed=0):
    if len(z) < 8: return float("nan")
    rng = np.random.default_rng(seed); mo = pd.Series(z.date.values).str[:6].values
    g = [z._r.values[mo == m] for m in np.unique(mo)]; k = len(g)
    return np.percentile([np.concatenate([g[i] for i in rng.integers(0,k,k)]).mean() for _ in range(n)], 5)

for mk, mkt in (("kp","코스피"), ("kq","코스닥")):
    K, cum = load(mk, mkt)
    print("="*128); print(f"[{mkt}]  매수=공탐 L 하향돌파 다음날 시가 · 매도=공탐 H 이상 첫날 종가(최대 {MAXHOLD}일)"); print("="*128)
    print(f"  {'L→H':<9}{'전체':>7}{'보유':>6}{'미도달':>6}"
          f"{'학습2016~22 (평균·중앙·승률·CI)':>34}{'검증2023~26':>34}{'초과(검증)':>11}")
    print("  " + "-"*124)
    best = []
    for L in LS:
        for H in HS:
            if H <= L: continue
            X = scan(K, cum, L, H)
            if len(X) < 30: continue
            a = X[(X.date>="20160101")&(X.date<="20221231")]; b = X[X.date>="20230101"]
            if len(b) < 15: continue
            f = lambda z: (f"{len(z):>5}건{z._r.mean():>+7.1f}%{z._r.median():>+6.1f}{(z._r>0).mean()*100:>4.0f}%{ci(z):>+6.1f}"
                           if len(z) >= 8 else f"{'—':>34}")
            exb = b._ex.mean()
            mark = " ★" if (b._r.median() > 0 and ci(b) > 0 and exb > 0) else ""
            print(f"  {L:>3}→{H:<5}{len(X):>7}{X.held.mean():>5.0f}일{X.forced.mean()*100:>5.0f}%{f(a):>34}{f(b):>34}{exb:>+10.2f}%{mark}")
            if mark: best.append((L, H, len(X), b._r.mean(), b._r.median(), exb))
    print(f"\n  ★ 통과(검증 중앙>0 & CI>0 & 초과>0): {len(best)}개" + (" — " + ", ".join(f"{l}→{h}" for l,h,*_ in best) if best else ""))
    print()
