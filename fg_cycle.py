# -*- coding: utf-8 -*-
"""공탐 진동 매매 — 40 미만↔60 이상을 반복하던 종목의 다음 저점에서 사서 고점에서 판다.

사용자 요청(2026-09-07): "공탐지수가 6개월 사이 혹은 1년 안에 40 미만되었다가 60이상 되었다가를
3회이상 반복한경우 4회차 40미만으로 내려갈때 매수 후 60이상 되었을때 매도".

정의
  · 사이클 1회 = 공탐이 lo 아래로 내려갔다가(LOW) 다시 hi 위로 올라옴(HIGH). HIGH 도달 시점에 1회 완성.
  · 신호 = 새로 LOW 로 진입한 날 기준, 직전 창(120/250거래일) 안에 완성된 사이클이 need 회 이상.
  · 매수 = 신호 다음날 시가(buy) · 매도 = 이후 공탐이 hi 이상 되는 첫날 종가.
    hi 에 닿지 않으면 maxhold 거래일에 강제 청산한다(안 그러면 영원히 들고 있는 셈이라 성적이 왜곡된다).
비교
  · 대조군: 같은 'LOW 진입' 이지만 사이클 요구가 0회인 경우 — 진동 이력이 정말 값어치가 있는지 가른다.
  · 같은 날 같은 시장 유니버스의 '같은 보유일수' 평균 대비 초과.
  · 구간: 스트레스2005~15(참고)/학습2016~22/검증2023~26 · 중복신호 제거 · 월블록 CI 하한 · 중앙값.
"""
import io, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
BASE = Path(__file__).parent
MAXHOLD = 120                     # 고점에 안 닿으면 여기서 자른다(약 6개월)

def load(mk, mkt):
    K = pd.read_pickle(BASE/"data"/f"panel_{mk}.pkl")[["ticker","date","close","buy","cost","amt20"]].copy()
    K["mk"] = mkt; K["pref"] = ~K.ticker.str.endswith("0")
    F = pd.read_pickle(BASE/"data"/f"stock_fg_{mk}.pkl")[["ticker","date","fg"]]
    n0 = len(K); K = K.merge(F, on=["ticker","date"], how="left"); assert len(K) == n0
    return K.sort_values(["ticker","date"]).reset_index(drop=True)

def scan(K, lo, hi, need, win, maxhold=MAXHOLD):
    """종목별 상태기계로 사이클을 세고, 조건을 만족한 LOW 진입일에 거래를 만든다."""
    out = []
    fg = K.fg.values; cl = K.close.values; bu = K.buy.values; co = K.cost.values
    idx = K.groupby("ticker", sort=False).indices
    for tk, ii in idx.items():
        f = fg[ii]; n = len(ii)
        state = None; cyc = []                     # 사이클 완성 시점(지역 인덱스)
        for i in range(n):
            v = f[i]
            if v != v: continue                    # NaN
            if v < lo:
                if state != "L":
                    state = "L"
                    # 이 시점이 '새 LOW 진입' — 창 안 사이클 수를 센다
                    k = sum(1 for c in cyc if i - c <= win)
                    if k >= need and bu[ii[i]] == bu[ii[i]] and bu[ii[i]] > 0:
                        # 매도: 이후 hi 이상 첫날, 없으면 maxhold 에서 강제청산
                        j = -1
                        for t in range(i+1, min(i+1+maxhold, n)):
                            if f[t] == f[t] and f[t] >= hi: j = t; break
                        forced = (j < 0)
                        if forced: j = min(i+maxhold, n-1)
                        if j <= i: continue
                        r = (cl[ii[j]]/bu[ii[i]]-1)*100 - co[ii[i]]
                        out.append((tk, K.date.values[ii[i]], r, j-i, forced, k))
            elif v >= hi:
                if state == "L": cyc.append(i)
                state = "H"
        # (MID 구간은 상태 유지)
    return pd.DataFrame(out, columns=["ticker","date","_r","held","forced","cycles"])

def dedup(X):
    """같은 종목이 보유 중 또 신호를 내면 건너뛴다"""
    if not len(X): return X
    X = X.sort_values("date"); keep, until = [], {}
    for tk, d, h, ix in zip(X.ticker.values, X.date.values, X.held.values, X.index):
        if until.get(tk, "") >= d: continue
        keep.append(ix); until[tk] = d           # 날짜 기준 근사(보유일수는 아래서 다시 본다)
    return X.loc[keep]
def ci(z, n=1200, seed=0):
    if len(z) < 8: return float("nan")
    rng = np.random.default_rng(seed); mo = pd.Series(z.date.values).str[:6].values
    g = [z._r.values[mo == m] for m in np.unique(mo)]; k = len(g)
    return np.percentile([np.concatenate([g[i] for i in rng.integers(0,k,k)]).mean() for _ in range(n)], 5)
def cell(z):
    return (f"{len(z):>4}건{z._r.mean():>+6.1f}%{z._r.median():>+6.1f}{(z._r>0).mean()*100:>4.0f}%{ci(z):>+6.1f}"
            if len(z) >= 5 else f"{'—':>25}")

KP, KQ = load("kp","KOSPI"), load("kq","KOSDAQ")
print(f"패널 로드 완료 · 코스피 {len(KP):,} · 코스닥 {len(KQ):,}\n")
HDR = f"  {'조건':<22}{'스트레스2005~15':>25}{'학습2016~22':>25}{'검증2023~26':>25}{'평균보유':>8}{'미도달':>7}"
for K, mkt in ((KP,"코스피"), (KQ,"코스닥")):
    print("="*130); print(f"[{mkt}]  매수=LOW 진입 다음날 시가 · 매도=공탐 {'{hi}'} 이상 첫날 종가 (최대 {MAXHOLD}일)"); print("="*130)
    print(HDR)
    for win, wn in ((120,"6개월"), (250,"1년")):
        for need in (0, 2, 3, 4):
            X = scan(K, 40, 60, need, win)
            if not len(X): print(f"  {wn} · 사이클 {need}회 이상 — 신호 없음"); continue
            X = X.merge(K[["ticker","date","close","amt20","pref"]], on=["ticker","date"], how="left")
            X = X[(~X.pref) & (X.close >= 1000) & (X.amt20.fillna(0) >= 3)]
            X = dedup(X)
            if len(X) < 5: print(f"  {wn} · 사이클 {need}회 이상 — 표본 부족({len(X)})"); continue
            s = X[X.date <= "20151231"]; a = X[(X.date>="20160101")&(X.date<="20221231")]; b = X[X.date>="20230101"]
            lab = f"{wn} · 사이클 {'요구없음' if need==0 else f'{need}회+'}"
            print(f"  {lab:<22}{cell(s):>25}{cell(a):>25}{cell(b):>25}{X.held.mean():>7.0f}일{X.forced.mean()*100:>6.0f}%")
    print()
