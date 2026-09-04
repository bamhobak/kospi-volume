# -*- coding: utf-8 -*-
"""규칙끼리 얼마나 겹치고, 어느 규칙이 실제로 계좌에 보태는가.

셋을 본다.
  1) 신호 겹침   — A 규칙 신호(종목·날) 중 ±5일 안에 B 규칙도 뜬 비율
  2) 월별 동조   — 규칙별 월 신호 건수의 상관 (같이 터지면 분산 효과가 없다)
  3) 하나씩 빼기 — 계좌에서 규칙 하나를 뺐을 때 자산·낙폭이 어떻게 변하나(같은 시드 짝지어)
                  빼도 자산이 안 줄면 그 규칙은 다른 규칙이 이미 잡는 종목을 중복으로 잡는 것이다.
사용: python rules_relation.py
"""
import io, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
BASE = Path(__file__).parent
src = (BASE/"portfolio.py").read_text(encoding="utf-8")
ns = {"__file__": str(BASE/"portfolio.py")}
real = sys.stdout; sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
exec(compile(src.split("# 신호를 한 표로 모은다")[0], "portfolio.py", "exec"), ns)
sys.stdout = real
KP, KQ, RULES = ns["KP"], ns["KQ"], ns["RULES"]
DISP = {"P7":"P1","P1":"P2","P4":"P3","P6":"P4","P3":"P5","P2":"P6","D1":"D1","D2":"D2","P5":"A1"}
NAME = {"P7":"외인매집","P1":"조용한신고가","P4":"업종붕괴","P6":"깊은이격","P3":"폭락반등",
        "P2":"조정매집","D1":"낙폭과대","D2":"저PBR","P5":"자사주"}
ORDER = ["P7","P1","P4","P6","P3","P2","D1","D2","P5"]
adates = sorted(set(KP.date)|set(KQ.date)); ADI = {d:i for i,d in enumerate(adates)}

def build(R):
    sig=[]
    for rid,(K,hold,stop,pct,mx,cond) in R.items():
        g=K.groupby("ticker",sort=False); ex=g.close.shift(-hold)
        lo=g.low.shift(-1).rolling(hold,min_periods=1).min().shift(-(hold-1))
        X=K[cond.fillna(False)].copy()
        X["rid"],X["hold"]=rid,hold; X["stop"]=stop if stop else np.nan; X["pct"],X["mx"]=pct,mx
        X["exit"]=ex.reindex(X.index); X["low"]=lo.reindex(X.index)
        sig.append(X[["date","ticker","rid","hold","stop","pct","mx","buy","exit","low","cost"]])
    S=pd.concat(sig).dropna(subset=["buy","exit","cost"]); S=S[S.buy>0].copy()
    S["di"]=S.date.map(ADI); return S.sort_values(["di","rid"]).reset_index(drop=True)
S = build(RULES)

# ── 1) 신호 겹침 (±5일) ─────────────────────────────────────────
print("1) 신호 겹침 — 행 규칙의 신호 중, ±5일 안에 열 규칙도 뜬 비율(%)   (대각=신호 수)\n")
by = {rid: {} for rid in ORDER}
for r in S.itertuples():
    by[r.rid].setdefault(r.ticker, []).append(r.di)
for rid in ORDER:
    for t in by[rid]: by[rid][t] = np.sort(by[rid][t])
def overlap(a, b):
    n=hit=0
    for t, ds in by[a].items():
        o = by[b].get(t)
        for d in ds:
            n += 1
            if o is not None:
                j = np.searchsorted(o, d-5)
                if j < len(o) and o[j] <= d+5: hit += 1
    return hit/n*100 if n else np.nan, n
print("  " + " "*10 + "".join(f"{DISP[c]:>6}" for c in ORDER))
for a in ORDER:
    row = ""
    for b in ORDER:
        v, n = overlap(a, b)
        row += f"{n:>6}" if a==b else f"{v:>5.0f}%"
    print(f"  {DISP[a]:<3}{NAME[a]:<7}{row}")

# ── 2) 월별 동조 ────────────────────────────────────────────────
print("\n2) 월별 신호 건수 상관 — 1 에 가까울수록 같은 달에 같이 터진다\n")
S["ym"] = S.date.str[:6]
M = S.groupby(["ym","rid"]).size().unstack(fill_value=0)
M = M.reindex(columns=ORDER, fill_value=0)
C = M.corr()
print("  " + " "*10 + "".join(f"{DISP[c]:>6}" for c in ORDER))
for a in ORDER:
    print(f"  {DISP[a]:<3}{NAME[a]:<7}" + "".join(f"{C.loc[a,b]:>6.2f}" if a!=b else f"{'—':>6}" for b in ORDER))
down = ["P4","P6","P3","D1","D2","P5"]
sub = C.loc[down, down].values; off = sub[~np.eye(len(down),dtype=bool)]
print(f"\n  하락장 규칙 6개끼리 평균 상관 {off.mean():.2f} · 상승장 규칙(P1·P2)과 하락장 규칙 평균 상관 "
      f"{C.loc[['P7','P1'], down].values.mean():.2f}")

# ── 3) 하나씩 빼기 ──────────────────────────────────────────────
def sim(S, ds, seed):
    eq=1.0; op=[]; curve=[]; byrid={}
    lo_i,hi_i=ADI[ds[0]],ADI[ds[-1]]
    byd={i:g for i,g in S[(S.di>=lo_i)&(S.di<=hi_i)].groupby("di")}
    rng=np.random.default_rng(seed)
    for d in ds:
        i=ADI[d]; st=[]
        for p in op:
            if p["ex"]<=i:
                hit=(p["stop"]==p["stop"]) and (p["low"]/p["buy"]-1)*100<=-p["stop"]*100
                r=(-p["stop"]*100-p["cost"]) if hit else ((p["exit"]/p["buy"]-1)*100-p["cost"])
                g=p["amt"]*r/100; eq+=g; byrid[p["rid"]]=byrid.get(p["rid"],0)+g
            else: st.append(p)
        op=st; td=byd.get(i)
        if td is not None:
            td=td.sample(frac=1,random_state=int(rng.integers(1<<31)))
            inv=sum(p["amt"] for p in op)
            for t in td.itertuples():
                nr=sum(1 for p in op if p["rid"]==t.rid); w=eq*t.pct/100
                if nr>=t.mx or inv+w>eq or any(p["tk"]==t.ticker for p in op): continue
                op.append(dict(rid=t.rid,tk=t.ticker,buy=t.buy,exit=t.exit,low=t.low,cost=t.cost,
                               stop=t.stop,amt=w,ex=i+t.hold)); inv+=w
        curve.append(eq)
    Cv=pd.Series(curve); dd=(Cv/Cv.cummax()-1)*100
    return dict(nav=Cv.iloc[-1], mdd=dd.min(), byrid=byrid)
ds = [d for d in adates if d >= "20180101"]
SEEDS = 12
print(f"\n3) 규칙 하나씩 빼기 — 전체 2018~26 · 시드 {SEEDS}회 · 같은 시드 짝지어 비교\n")
full = [sim(S, ds, k) for k in range(SEEDS)]
fnav = np.median([r["nav"] for r in full]); fmdd = np.median([r["mdd"] for r in full])
print(f"  {'구성':<18}{'자산':>8}{'자산 변화':>10}{'낙폭':>8}{'낙폭 변화':>10}{'뺀 규칙의 직접 기여':>20}")
print(f"  {'9규칙 전부':<18}{fnav:>7.2f}배{'':>10}{fmdd:>7.1f}%")
res = []
for rid in ORDER:
    R = [sim(S[S.rid!=rid], ds, k) for k in range(SEEDS)]
    nav = np.median([r["nav"] for r in R]); mdd = np.median([r["mdd"] for r in R])
    direct = np.median([r["byrid"].get(rid,0) for r in full])
    res.append((rid, nav, mdd, direct))
    print(f"  {'-'+DISP[rid]+' '+NAME[rid]:<18}{nav:>7.2f}배{nav-fnav:>+9.2f}배{mdd:>7.1f}%{mdd-fmdd:>+9.1f}%p{direct:>+18.2f}")
print("\n  읽는 법: '자산 변화' 가 '직접 기여' 보다 훨씬 작으면(0 근처) 그 규칙이 잡는 종목·자리를 다른 규칙이")
print("  대신 잡는다는 뜻 — 중복이다. 빼도 자산이 안 줄고 낙폭이 좋아지면 빼는 게 낫다.")
