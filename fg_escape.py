# -*- coding: utf-8 -*-
"""공포 탈출 신호 — 공탐지수 30 미만을 오래 끌다가 30 위로 올라와 2거래일 유지된 종목.

사용자 요청(2026-09-07): "공탐지수가 30미만을 30거래일 이상 유지하다가 30을 넘고
30이상인 상태가 2거래일 닿은 종목 매수후 시기별 매도".

정의
  · 침체: 종목 공탐(stock_fg_*.pkl) < 30 이 N거래일 이상 연속
  · 신호: 그 직후 공탐 ≥ 30 이 M거래일 연속된 날(M째 날 장 마감)
  · 매수: 신호 다음날 시가(패널 buy 열) · 매도: 신호일 기준 H거래일 뒤 종가(n{H})
  · 비용(거래세 0.15+슬리피지)은 n{H} 에 이미 반영돼 있다
판정
  · 구간: 스트레스 2005~15(참고) / 학습 2016~22 / 검증 2023~26  (2026-09-07 기준)
  · 3대 함정: 중복신호 제거(보유 중 재진입 금지) · 생존편향(폐지 종목 포함 패널) · 연도쏠림 표기
  · 같은 날 같은 시장 유니버스 평균 대비 '초과' 도 함께 본다 — 지수와 비교하지 않는다
  · 월 블록 부트스트랩 90% 신뢰구간 하한
사용: python fg_escape.py
"""
import io, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
BASE = Path(__file__).parent
HS = [5, 10, 15, 20, 30, 40, 60]          # 시기별 매도
PER = [("스트레스2005~15","20050101","20151231"), ("학습2016~22","20160101","20221231"),
       ("검증2023~26","20230101","20991231"), ("기준2016~","20160101","20991231")]

def load(mk, mkt):
    cols = ["ticker","date","close","open","buy","cost","amt20"] + [f"n{h}" for h in HS]
    K = pd.read_pickle(BASE/"data"/f"panel_{mk}.pkl")
    K = K[[c for c in cols if c in K.columns]].copy()
    K["mk"] = mkt
    # 우선주 판정은 portfolio.py 와 같은 방식(종목코드 끝자리가 0 이 아니면 우선주)
    K["pref"] = ~K.ticker.str.endswith("0")
    F = pd.read_pickle(BASE/"data"/f"stock_fg_{mk}.pkl")[["ticker","date","fg"]]
    n0 = len(K); K = K.merge(F, on=["ticker","date"], how="left"); assert len(K) == n0
    return K.sort_values(["ticker","date"]).reset_index(drop=True)
KP, KQ = load("kp","KOSPI"), load("kq","KOSDAQ")
print(f"패널 로드 · 코스피 {len(KP):,}행 · 코스닥 {len(KQ):,}행 · 공탐 유효 {KP.fg.notna().mean()*100:.0f}%/{KQ.fg.notna().mean()*100:.0f}%")

def signals(K, low_n, high_m, th=30.0):
    """침체 low_n일 이상 → 돌파 high_m일 연속인 날에 True"""
    t = K.ticker.values
    lo = (K.fg < th).fillna(False).values
    hi = (K.fg >= th).fillna(False).values
    # 종목별 연속 카운트 (경계에서 끊는다)
    def runlen(flag):
        out = np.zeros(len(flag), dtype=np.int32); c = 0; prev = None
        for i in range(len(flag)):
            if t[i] != prev: c = 0; prev = t[i]
            c = c + 1 if flag[i] else 0
            out[i] = c
        return out
    rl, rh = runlen(lo), runlen(hi)
    prev_lo = pd.Series(rl).groupby(K.ticker.values).shift(high_m).fillna(0).values
    return (rh == high_m) & (prev_lo >= low_n)

def dedup(X, hold):
    """중복신호 제거 — 보유 중 같은 종목 재진입 금지"""
    d = sorted(X.date.unique()); di = {x: i for i, x in enumerate(d)}
    X = X.assign(_di=X.date.map(di)).sort_values("_di")
    keep, last = [], {}
    for tk, i, ix in zip(X.ticker.values, X._di.values, X.index):
        if last.get(tk, -10**9) >= i: continue
        last[tk] = i + hold; keep.append(ix)
    return X.loc[keep]

def ci(z, n=1500, seed=0):
    if len(z) < 8: return float("nan")
    rng = np.random.default_rng(seed); mo = z.date.str[:6].values
    g = [z._r.values[mo == m] for m in np.unique(mo)]; k = len(g)
    return np.percentile([np.concatenate([g[i] for i in rng.integers(0,k,k)]).mean() for _ in range(n)], 5)

def report(title, K, sig, base_filter=True):
    S = K[sig].copy()
    if base_filter:
        S = S[(~S.pref.fillna(False)) & (S.close >= 1000) & (S.amt20.fillna(0) >= 3)]
    if not len(S): print(f"\n[{title}] 신호 없음"); return None
    print(f"\n[{title}]  신호 {len(S):,}건 (기본필터 {'적용' if base_filter else '없음'})")
    print(f"  {'매도':<6}" + "".join(f"{p[0]:>26}" for p in PER) + f"{'초과(기준2016~)':>16}")
    best = None
    for h in HS:
        col = f"n{h}"
        if col not in K.columns: continue
        Z = dedup(S.dropna(subset=[col]).assign(_r=lambda d: d[col]), h)
        uni = K.dropna(subset=[col]).groupby("date")[col].mean()
        Z["_ex"] = Z._r - Z.date.map(uni)
        row = f"  {h:>3}일  "
        for pn, lo, hi in PER:
            z = Z[(Z.date >= lo) & (Z.date <= hi)]
            row += (f"{len(z):>5}건{z._r.mean():>+6.1f}%{z._r.median():>+6.1f}{(z._r>0).mean()*100:>4.0f}%{ci(z):>+6.1f}"
                    if len(z) >= 5 else f"{'—':>26}")
        b = Z[Z.date >= "20160101"]
        row += f"{b._ex.mean() if len(b) else float('nan'):>+15.2f}%"
        print(row)
    return S

print("\n" + "="*118)
print("① 요청하신 조건 그대로 — 침체 30일 이상 → 돌파 2일 연속 (건수·평균·중앙·승률·CI하한)")
print("="*118)
for K, nm in ((KP,"코스피"), (KQ,"코스닥")):
    report(f"{nm} · 침체30일→돌파2일", K, signals(K, 30, 2))

print("\n" + "="*118)
print("② 문턱을 바꿔 본다 — 침체 기간·돌파 확인일 (20일 보유 기준 요약)")
print("="*118)
print(f"  {'시장':<5}{'침체':>5}{'돌파':>5}{'신호':>7}{'학습2016~22':>22}{'검증2023~26':>22}{'초과':>9}")
for K, nm in ((KP,"코스피"), (KQ,"코스닥")):
    for low_n in (20, 30, 40, 60):
        for high_m in (1, 2, 3):
            sig = signals(K, low_n, high_m)
            S = K[sig]; S = S[(~S.pref.fillna(False)) & (S.close >= 1000) & (S.amt20.fillna(0) >= 3)]
            if len(S) < 20: continue
            Z = dedup(S.dropna(subset=["n20"]).assign(_r=lambda d: d.n20), 20)
            uni = K.dropna(subset=["n20"]).groupby("date").n20.mean()
            Z["_ex"] = Z._r - Z.date.map(uni)
            a = Z[(Z.date>="20160101")&(Z.date<="20221231")]; b = Z[Z.date>="20230101"]
            f = lambda z: (f"{len(z):>4}건{z._r.mean():>+6.1f}%{(z._r>0).mean()*100:>4.0f}%{ci(z):>+6.1f}"
                           if len(z) >= 5 else f"{'—':>22}")
            ex = Z[Z.date>="20160101"]._ex.mean()
            print(f"  {nm:<5}{low_n:>5}{high_m:>5}{len(Z):>7}{f(a):>22}{f(b):>22}{ex:>+8.2f}%")

print("\n" + "="*118)
print("③ 연도쏠림 — 요청 조건(30일→2일)의 연도별 신호 수와 20일 성적")
print("="*118)
for K, nm in ((KP,"코스피"), (KQ,"코스닥")):
    S = K[signals(K, 30, 2)]; S = S[(~S.pref.fillna(False)) & (S.close >= 1000) & (S.amt20.fillna(0) >= 3)]
    Z = dedup(S.dropna(subset=["n20"]).assign(_r=lambda d: d.n20), 20)
    Z = Z[Z.date >= "20050101"].assign(y=lambda d: d.date.str[:4])
    g = Z.groupby("y")._r.agg(["size","mean"])
    print(f"  {nm}: " + " · ".join(f"{y}:{int(r['size'])}건 {r['mean']:+.1f}%" for y, r in g.iterrows()))
