# -*- coding: utf-8 -*-
"""사이트 설명문에 넣을 새 기준(2016~) 실측치 — 규칙별 · 구간별.

2026-09-07 사용자 결정으로 학습 시점이 2016년이 됐다. 사이트 규칙 설명문에 박혀 있는
"학습(2018~22) → 검증(2023~26)" 숫자를 새 구간으로 다시 써야 한다.
산출: 스트레스2005~15 / 학습2016~22 / 검증2023~26 / 기준2016~ 각각
      건수 · 평균 · 중앙 · 승률 · PF · 최악 · 월블록 CI 하한, 그리고 연도별.
사용: python stats_2016.py   (portfolio.py 기본값이 이미 전체 이력 패널이다)
"""
import io, os, sys, json, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
BASE = Path(__file__).parent
src = (BASE/"portfolio.py").read_text(encoding="utf-8"); ns = {"__file__": str(BASE/"portfolio.py")}
real = sys.stdout; sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
exec(compile(src.split("# 신호를 한 표로 모은다")[0], "portfolio.py", "exec"), ns)
sys.stdout = real
RULES = ns["RULES"]
NAME = {"P7":"외인 매집","P1":"조용한 신고가","P4":"업종붕괴 이탈","P6":"깊은 이격","P3":"폭락반등",
        "P2":"조정매집","D1":"낙폭과대","D2":"저PBR 낙폭","P5":"자사주 낙폭"}
DISP = {"P7":"P1","P1":"P2","P4":"P3","P6":"P4","P3":"P5","P2":"P6","D1":"D1","D2":"D2","P5":"A1"}
ORDER = ["P7","P1","P2","P3","P4","P6","P5","D1","D2"]
PER = [("스트레스2005~15","20050101","20151231"), ("학습2016~22","20160101","20221231"),
       ("검증2023~26","20230101","20991231"), ("기준2016~","20160101","20991231")]

def take(rid):
    K, hold, stop, pct, mx, cond = RULES[rid]
    g = K.groupby("ticker", sort=False)
    if stop:
        low = pd.concat([g.low.shift(-i) for i in range(hold)], axis=1).min(axis=1)
        r = np.where((low <= K.buy*(1-stop)).fillna(False), -stop*100 - K.cost, K[f"n{hold}"])
    else: r = K[f"n{hold}"].values
    m = cond.fillna(False); X = K[m].copy(); X["_r"] = r[m.values]; X = X.dropna(subset=["_r"])
    di = {x: i for i, x in enumerate(sorted(K.date.unique()))}
    X["di"] = X.date.map(di); X = X.sort_values("di")
    keep, last = [], {}
    for t, i, ix in zip(X.ticker.values, X.di.values, X.index):
        if last.get(t, -10**9) >= i: continue
        last[t] = i+hold; keep.append(ix)
    return X.loc[keep].assign(y=lambda d: d.date.str[:4]), hold, stop

def ci(Z, n=2000, seed=0):
    if len(Z) < 8: return float("nan")
    rng = np.random.default_rng(seed); mo = Z.date.str[:6].values
    grp = [Z._r.values[mo == m] for m in np.unique(mo)]; k = len(grp)
    o = [np.concatenate([grp[i] for i in rng.integers(0, k, k)]).mean() for _ in range(n)]
    return np.percentile(o, 5)

def pf(z):
    up = z[z > 0].sum(); dn = -z[z < 0].sum()
    return up/dn if dn > 0 else float("inf")

OUT = {}
print(f"{'규칙':<14}{'구간':<14}{'건수':>6}{'평균':>8}{'중앙':>8}{'승률':>6}{'PF':>7}{'최악':>8}{'CI하한':>8}{'월수':>5}")
print("-"*94)
for rid in ORDER:
    Z, hold, stop = take(rid); OUT[rid] = {}
    for pn, lo, hi in PER:
        z = Z[(Z.date >= lo) & (Z.date <= hi)]
        if not len(z):
            print(f"{NAME[rid]:<14}{pn:<14}{'신호 없음':>6}"); OUT[rid][pn] = None; continue
        # 신호는 고르게 나지 않는다 — '월 N건' 단순 나눗셈은 오해를 부른다(2026-09-07).
        #   예: [업종붕괴 이탈] 검증 209건은 44개월 중 2개월에만 몰려 있다.
        #   그래서 '신호가 난 달 수 / 전체 달 수' 와 '난 달의 중앙 건수' 를 같이 남긴다.
        mo = z.date.str[:6]
        span = (int(hi[:4])*12+int(hi[4:6]) if hi < "20991231" else 2026*12+9) - (int(lo[:4])*12+int(lo[4:6])) + 1
        d = dict(n=len(z), avg=z._r.mean(), med=z._r.median(), win=(z._r>0).mean()*100,
                 pf=pf(z._r), worst=z._r.min(), ci=ci(z), months=mo.nunique(),
                 span=span, permo_med=float(mo.value_counts().median()),
                 top_mo=str(mo.value_counts().index[0]), top_n=int(mo.value_counts().iloc[0]))
        OUT[rid][pn] = d
        print(f"{NAME[rid]:<14}{pn:<14}{d['n']:>6}{d['avg']:>+7.2f}%{d['med']:>+7.2f}%{d['win']:>5.0f}%"
              f"{d['pf']:>7.2f}{d['worst']:>+7.1f}%{d['ci']:>+7.1f}%{d['months']:>5}")
    OUT[rid]["hold"] = hold; OUT[rid]["stop"] = stop; OUT[rid]["disp"] = DISP[rid]
    OUT[rid]["yearly"] = {y: dict(n=len(g), avg=g._r.mean(), win=(g._r>0).mean()*100)
                          for y, g in Z[Z.date >= "20160101"].groupby("y")}
    print()
json.dump(OUT, open(BASE/"data"/"stats_2016.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=float)
print("→ data/stats_2016.json 저장")
print("\n연도별 (2016~) 건수·평균·승률")
for rid in ORDER:
    y = OUT[rid]["yearly"]
    print(f"  {NAME[rid]:<14}" + " · ".join(f"{k}:{v['n']}건 {v['avg']:+.1f}%({v['win']:.0f}%)" for k, v in sorted(y.items())))
