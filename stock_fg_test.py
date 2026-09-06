# -*- coding: utf-8 -*-
"""종목 공포탐욕 점수를 아홉 규칙에 얹어 본다 — 2016년 기준.

세 가지를 본다.
 ① 규칙 신호가 날 때 그 종목의 점수는 어디쯤인가 (유니버스 같은 날 중앙값과 비교)
    — 이미 극단이면 '규칙을 숫자로 요약한 것' 이고, 새 정보는 아니다.
 ② 점수 4분위로 신호를 나눠 수익률이 단조롭게 갈리는가 — 갈리면 정보, 평평하면 없음.
 ③ 문턱 얹기: 하락장 규칙엔 '공포 ≤ th', 상승장 규칙엔 '탐욕 ≥ th' 와 반대 방향도.
    판정은 학습(2016~22)·검증(2023~26) CI 하한 > 0 & 중앙 > 0 & 2026 승 & 기준선 대비 양쪽 개선.
 ④ 조기 청산: 보유 중 탐욕 ≥ th 가 되면 판다 — [폭락반등]·[낙폭과대](20일 보유)만.
사용: python stock_fg_test.py
"""
import io, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
BASE = Path(__file__).parent
src = (BASE/"portfolio.py").read_text(encoding="utf-8"); ns = {"__file__": str(BASE/"portfolio.py")}
real = sys.stdout; sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
exec(compile(src.split("# 신호를 한 표로 모은다")[0], "portfolio.py", "exec"), ns)
sys.stdout = real
KP, KQ, RULES = ns["KP"], ns["KQ"], ns["RULES"]
NAME = {"P7":"외인 매집","P1":"조용한 신고가","P4":"업종붕괴 이탈","P6":"깊은 이격","P3":"폭락반등",
        "P2":"조정매집","D1":"낙폭과대","D2":"저PBR 낙폭","P5":"자사주 낙폭"}
UP = {"P7","P1"}                       # 상승장 규칙(탐욕 쪽)
for mk, K in (("kp", KP), ("kq", KQ)):
    F = pd.read_pickle(BASE/"data"/f"stock_fg_{mk}.pkl")[["ticker","date","fg"]]
    n0 = len(K); K2 = K.merge(F, on=["ticker","date"], how="left"); assert len(K2) == n0
    K["fg"] = K2.fg.values
KB = ns["KB"] if "KB" in ns else None
if KB is not None and "fg" not in KB.columns:
    # 시장을 옮긴 종목(코스닥→코스피)은 두 패널에 다 있어 (ticker,date) 가 겹친다 — 하나만 남긴다
    F = pd.concat([pd.read_pickle(BASE/"data"/f"stock_fg_{m}.pkl")[["ticker","date","fg"]] for m in ("kp","kq")])
    F = F.drop_duplicates(["ticker","date"], keep="first")
    n0 = len(KB); KB2 = KB.merge(F, on=["ticker","date"], how="left"); assert len(KB2) == n0
    KB["fg"] = KB2.fg.values

def trades(K, cond, hold, stop):
    g = K.groupby("ticker", sort=False)
    if stop:
        low = pd.concat([g.low.shift(-i) for i in range(hold)], axis=1).min(axis=1)
        r = np.where((low <= K.buy*(1-stop)).fillna(False), -stop*100-K.cost, K[f"n{hold}"])
    else: r = K[f"n{hold}"].values
    m = cond.fillna(False); X = K[m].copy(); X["_r"] = r[m.values]; X = X.dropna(subset=["_r"])
    di = {x:i for i,x in enumerate(sorted(K.date.unique()))}
    X["di"] = X.date.map(di); X = X.sort_values("di"); keep, last = [], {}
    for t,i,ix in zip(X.ticker.values, X.di.values, X.index):
        if last.get(t,-10**9) >= i: continue
        last[t] = i+hold; keep.append(ix)
    return X.loc[keep].assign(y=lambda d: d.date.str[:4])
def ci(Z, n=1500, seed=0):
    if len(Z) < 8: return float("nan")
    rng = np.random.default_rng(seed); mo = Z.date.str[:6].values
    grp = [Z._r.values[mo == m] for m in np.unique(mo)]; k = len(grp)
    return np.percentile([np.concatenate([grp[i] for i in rng.integers(0,k,k)]).mean() for _ in range(n)], 5)
def cell(Z):
    if not len(Z): return f"{'—':>26}"
    return f"{len(Z):>4}건{Z._r.mean():>+6.1f}%{Z._r.median():>+6.1f}{(Z._r>0).mean()*100:>4.0f}%{ci(Z):>+6.1f}"
TR, VA = ("20160101","20221231"), ("20230101","20991231")
def row(nm, Z):
    a = Z[(Z.date>=TR[0])&(Z.date<=TR[1])]; b = Z[(Z.date>=VA[0])]
    y26 = Z[Z.y=="2026"]._r.mean() if (Z.y=="2026").any() else float("nan")
    print(f"  {nm:<22}{cell(a)}   {cell(b)}   {y26:>+6.1f}")
HDR = f"  {'':<22}{'학습 2016~22 (건·평균·중앙·승률·CI)':>26}   {'검증 2023~26':>26}   {'2026':>6}"

print("① 신호 시점의 종목 점수 vs 같은 날 유니버스 중앙값 (2016~)")
for rid, (K, hold, stop, pct, mx, cond) in RULES.items():
    Z = trades(K, cond, hold, stop); Z = Z[Z.date >= "20160101"].dropna(subset=["fg"])
    uni = K[(K.date>="20160101")].dropna(subset=["fg"]).groupby("date").fg.median()
    if not len(Z): print(f"  {NAME[rid]:<14} 신호 없음"); continue
    ub = Z.date.map(uni)
    print(f"  {NAME[rid]:<14} 신호 {len(Z):>4}건 · 점수 중앙 {Z.fg.median():>4.0f} (4분위 {Z.fg.quantile(.25):.0f}~{Z.fg.quantile(.75):.0f})"
          f" · 유니버스 같은 날 중앙 {ub.median():>4.0f} · 차이 {Z.fg.median()-ub.median():>+5.0f}")

print("\n② 점수 4분위별 수익률 (규칙 신호 안에서 나눔 · 2016~) — 단조롭게 갈리면 정보가 있다")
print(f"  {'규칙':<14}{'Q1 낮음(공포)':>16}{'Q2':>14}{'Q3':>14}{'Q4 높음(탐욕)':>16}   판정")
for rid, (K, hold, stop, pct, mx, cond) in RULES.items():
    Z = trades(K, cond, hold, stop); Z = Z[Z.date >= "20160101"].dropna(subset=["fg"])
    if len(Z) < 40: print(f"  {NAME[rid]:<14} 표본 부족({len(Z)})"); continue
    q = pd.qcut(Z.fg, 4, labels=False, duplicates="drop"); m = Z.groupby(q)._r.mean(); n = Z.groupby(q).size()
    cells = "".join(f"{m.get(i, float('nan')):>+8.1f}%({n.get(i,0):>3})" for i in range(4))
    d = m.iloc[-1] - m.iloc[0]
    verdict = ("탐욕 쪽이 낫다" if d > 2 else "공포 쪽이 낫다" if d < -2 else "차이 없음") + f" ({d:+.1f}p)"
    print(f"  {NAME[rid]:<14}{cells}   {verdict}")

print("\n③ 문턱 얹기 — 기준선과 비교")
for rid, (K, hold, stop, pct, mx, cond) in RULES.items():
    Z0 = trades(K, cond, hold, stop); Z0 = Z0[Z0.date >= "20160101"]
    if len(Z0) < 30: continue
    print(f"\n [{NAME[rid]}]"); print(HDR)
    row("기준선", Z0)
    ths = ((30,"≤"),(40,"≤"),(50,"≤"),(60,"≥"),(70,"≥")) if rid in UP else ((20,"≤"),(30,"≤"),(40,"≤"),(50,"≤"),(60,"≥"))
    for th, op in ths:
        c2 = cond & ((K.fg <= th) if op == "≤" else (K.fg >= th))
        Z = trades(K, c2, hold, stop); Z = Z[Z.date >= "20160101"]
        row(f"+ 점수 {op}{th}", Z)

print("\n④ 조기 청산 — 보유 중 탐욕 ≥ th 면 그날 종가에 판다 ([폭락반등]·[낙폭과대] 20일 보유)")
for rid in ("P3", "D1"):
    K, hold, stop, pct, mx, cond = RULES[rid]
    g = K.groupby("ticker", sort=False)
    fgf = pd.concat([g.fg.shift(-i) for i in range(1, hold+1)], axis=1).values      # 1..hold 일 뒤 점수
    clf = pd.concat([g.close.shift(-i) for i in range(1, hold+1)], axis=1).values   # 그날 종가
    Z0 = trades(K, cond, hold, stop); Z0 = Z0[Z0.date >= "20160101"]
    print(f"\n [{NAME[rid]}]"); print(HDR); row("기준선(20일 보유)", Z0)
    for th in (70, 80, 90):
        hitm = fgf[Z0.index] >= th
        first = np.where(hitm.any(axis=1), hitm.argmax(axis=1), -1)
        ex = np.where(first >= 0, clf[Z0.index, np.maximum(first,0)], np.nan)
        r_early = (ex/Z0.buy.values-1)*100 - Z0.cost.values
        Z = Z0.copy(); Z["_r"] = np.where(first >= 0, r_early, Z0._r.values)
        row(f"탐욕 ≥{th} 조기청산 ({(first>=0).mean()*100:.0f}% 발동)", Z)
