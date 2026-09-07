# -*- coding: utf-8 -*-
"""유튜브 스윙 기초 영상 실측 — 지지선 바운스·저항선 돌파·손절·트레일링·손익비.

전략 원문(2026-09-07 사용자 제공, 개념 위주라 검증 가능한 형태로 정의했다):
  ① 저점에서 사서 고점에서 판다 → '지지선 바운스': 최근 창의 저점 근처(+3% 이내)에서 양봉이 뜨면 매수
  ② 저항선 '브레이크아웃': 최근 창의 고점을 종가로 돌파하면 매수
  ③ 손절(stop) 설정: -5/-8/-10/-15% 를 각각 재고 손절 없음과 비교
  ④ 트레일링 스톱: 오를수록 손절선을 올린다(보유 중 고점 대비 -X% 하락 시 청산)
  ⑤ 손익비(R:R): 목표(저항선까지) ÷ 위험(손절까지) 가 2 이상일 때만 진입
정의를 내가 정한 만큼, 창 길이(10/20/60일)를 바꿔 특정 값에 기댄 결과가 아닌지 함께 본다.
판정은 우리 표준 — 학습2016~22 / 검증2023~26 · 중복제거 · 유니버스 대비 초과 · 월블록 CI 하한 · 중앙값.
"""
import io, os, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
BASE = Path(__file__).parent
HS = [3, 5, 10, 20]
src = (BASE/"portfolio.py").read_text(encoding="utf-8"); ns = {"__file__": str(BASE/"portfolio.py")}
real = sys.stdout; sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
exec(compile(src.split("# 신호를 한 표로 모은다")[0], "portfolio.py", "exec"), ns)
sys.stdout = real
KP, KQ, base = ns["KP"], ns["KQ"], ns["base"]
for K in (KP, KQ):
    g = K.groupby("ticker", sort=False)
    for h in HS:
        if f"n{h}" not in K.columns: K[f"n{h}"] = (g.close.shift(-h)/K.buy-1)*100 - K.cost
    K["green"] = K.close > K.open
    for w in (10, 20, 60):
        K[f"lo{w}"] = g.low.transform(lambda s, w=w: s.shift(1).rolling(w).min())
        K[f"hi{w}"] = g.high.transform(lambda s, w=w: s.shift(1).rolling(w).max())
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
def row(lab, K, mask, hs=HS, stop=None, trail=None):
    m = mask.fillna(False)
    if m.sum() < 30: print(f"  {lab:<32} 표본 부족({int(m.sum())})"); return
    g = K.groupby("ticker", sort=False)
    out = f"  {lab:<32}{int(m.sum()):>8}"
    for h in hs:
        col = f"n{h}"
        if stop or trail:
            lows = pd.concat([g.low.shift(-i) for i in range(1, h+1)], axis=1)
            if stop:
                hit = (lows.min(axis=1) <= K.buy*(1-stop)).fillna(False)
                r = np.where(hit, -stop*100 - K.cost, K[col])
            else:
                # 트레일링 스톱. ⚠ 청산가에 '보유기간 전체 최고점' 을 쓰면 미래를 보는 것이다
                #   (2026-09-07 첫 구현의 버그 — 검증 +7.1% 라는 가짜 결과가 나왔다).
                #   발동한 그 시점까지의 최고점만 쓴다. 최고점의 시작값은 매수가다.
                C = np.column_stack([g.close.shift(-i).values for i in range(1, h+1)])
                run = np.maximum.accumulate(
                    np.column_stack([K.buy.values, C]), axis=1)[:, 1:]
                hit = C <= run*(1-trail)
                ok = hit.any(axis=1)
                first = np.where(ok, hit.argmax(axis=1), 0)
                px = np.where(ok, run[np.arange(len(C)), first]*(1-trail), C[:, -1])
                r = (px/K.buy.values-1)*100 - K.cost.values
                r = np.where(np.isnan(C).all(axis=1), np.nan, r)
            K["_r"] = r
        else:
            K["_r"] = K[col].values
        Z = dedup(K[m].dropna(subset=["_r"]), h, K)
        if len(Z) < 20: out += f"{'—':>28}"; continue
        ex = (Z._r - Z.date.map(uni(K, h))).mean()
        v = Z[Z.date >= "20230101"]
        out += (f"{Z._r.mean():>+6.2f}%({ex:>+5.2f}){Z._r.median():>+6.1f} "
                f"검{v._r.mean() if len(v)>=8 else float('nan'):>+5.1f}{ci(v,'_r') if len(v)>=8 else float('nan'):>+5.1f} ")
    print(out)
for K, mkt in ((KP,"코스피"), (KQ,"코스닥")):
    print("="*160); print(f"[{mkt}] 숫자 = 전체평균(초과)중앙 · 검증평균/CI하한"); print("="*160)
    print(f"  {'':<32}{'신호':>8}" + "".join(f"{'  n'+str(h):>28}" for h in HS))
    b = base(K, 3) & (K.date >= "20160101")
    print("  ── ① 지지선 바운스 (저점 +3% 이내에서 양봉) ──")
    for w in (10, 20, 60):
        row(f"창 {w}일", K, b & (K.close <= K[f"lo{w}"]*1.03) & K.green)
    print("  ── ② 저항선 돌파 (고점 종가 돌파) ──")
    for w in (10, 20, 60):
        row(f"창 {w}일", K, b & (K.close > K[f"hi{w}"]))
    print("  ── ③ 손절 효과 (창 20일 바운스에 적용) ──")
    bo = b & (K.close <= K.lo20*1.03) & K.green
    row("손절 없음", K, bo)
    for st in (0.05, 0.08, 0.10, 0.15):
        row(f"손절 -{st*100:.0f}%", K, bo, stop=st)
    print("  ── ④ 트레일링 스톱 (같은 신호) ──")
    for tr in (0.03, 0.05, 0.08):
        row(f"트레일링 -{tr*100:.0f}%", K, bo, trail=tr)
    print("  ── ⑤ 손익비 2:1 이상 (저항선까지 여유 ÷ 손절폭) ──")
    for st in (0.05, 0.08):
        rr = (K.hi20 - K.close) / (K.close*st)
        row(f"손절 -{st*100:.0f}% · R:R≥2", K, bo & (rr >= 2), stop=st)
        row(f"손절 -{st*100:.0f}% · R:R≥3", K, bo & (rr >= 3), stop=st)
    print()
