# -*- coding: utf-8 -*-
"""[외인 매집] 추가매수 — 기간을 갈라 수익금까지 철저히 비교.

앞선 계좌 검증은 전 기간 하나로만 봤다. [외인 매집] 은 상승장 규칙이라
2025~26 대세상승에 기댄 결과일 수 있어, 기간을 넷으로 갈라 다시 잰다.
  전체 2018~26 / 학습 2018~22 / 검증 2023~26 / 붐 제외 (~2024)

비교 방식도 고쳤다. 같은 날 여러 신호 중 무엇이 체결되냐는 운이므로 시드를
여러 개 돌리는데, 앞서는 A 와 B 의 중앙값을 따로 내어 비교했다. 그러면 운이
좋은 쪽이 섞인다. 같은 시드에서 A 와 B 를 짝지어 비교해야 '추가매수를 했을 때
그 세계에서 더 벌었는가' 를 본다.

사용: python addbuy_final.py
"""
import io, sys
from pathlib import Path
import numpy as np, pandas as pd

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
BASE = Path(__file__).parent
src = (BASE / "portfolio.py").read_text(encoding="utf-8")
ns = {"__file__": str(BASE / "portfolio.py")}
real = sys.stdout; sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
exec(compile(src.split("# 신호를 한 표로 모은다")[0], "portfolio.py", "exec"), ns)
sys.stdout = real
KP, KQ, RULES = ns["KP"], ns["KQ"], ns["RULES"]
adates = sorted(set(KP.date) | set(KQ.date)); ADI = {d: i for i, d in enumerate(adates)}

_K, _h, _s, _p, _m, P7 = RULES["P7"]
c = P7.fillna(False).to_numpy()
new_tk = KP.ticker.ne(KP.ticker.shift()).to_numpy(); idx = np.arange(len(c))
base = np.where(~c, idx, -1); base = np.where(new_tk & c, idx - 1, base)
base = np.maximum.accumulate(base)
stk = np.where(c, idx - base, 0)
_fb = pd.Series(np.where(stk == 1, KP.buy.to_numpy(), np.nan), index=KP.index)
first_buy = _fb.groupby([KP.ticker, pd.Series(base, index=KP.index)]).transform("first")
win = (KP.close / first_buy - 1) * 100
ADD = pd.Series(c & (stk >= 2) & (win.fillna(-1).to_numpy() > 0), index=KP.index)

def build(R):
    sig = []
    for rid, (K, hold, stop, pct, mx, cond) in R.items():
        g = K.groupby("ticker", sort=False); ex = g.close.shift(-hold)
        lo = g.low.shift(-1).rolling(hold, min_periods=1).min().shift(-(hold - 1))
        X = K[cond.fillna(False)].copy()
        X["rid"] = rid; X["hold"] = hold; X["stop"] = stop if stop else np.nan
        X["pct"] = pct; X["mx"] = mx
        X["exit"] = ex.reindex(X.index); X["low"] = lo.reindex(X.index)
        sig.append(X[["date","ticker","rid","hold","stop","pct","mx","buy","exit","low","cost"]])
    S = pd.concat(sig).dropna(subset=["buy","exit","cost"]); S = S[S.buy > 0].copy()
    S["di"] = S.date.map(ADI); return S.sort_values(["di","rid"]).reset_index(drop=True)

def sim(S, ds, seed=None):
    eq = 1.0; op = []; curve = []; wins = []; byrid = {}
    lo_i, hi_i = ADI[ds[0]], ADI[ds[-1]]
    by = {i: g for i, g in S[(S.di >= lo_i) & (S.di <= hi_i)].groupby("di")}
    rng = np.random.default_rng(seed) if seed is not None else None
    for d in ds:
        i = ADI[d]; st = []
        for p in op:
            if p["ex"] <= i:
                hit = (p["stop"] == p["stop"]) and (p["low"] / p["buy"] - 1) * 100 <= -p["stop"] * 100
                r = (-p["stop"] * 100 - p["cost"]) if hit else ((p["exit"] / p["buy"] - 1) * 100 - p["cost"])
                gain = p["amt"] * r / 100; eq += gain; wins.append(r > 0)
                byrid[p["rid"]] = byrid.get(p["rid"], 0.0) + gain
            else: st.append(p)
        op = st; td = by.get(i)
        if td is not None:
            if rng is not None: td = td.sample(frac=1, random_state=int(rng.integers(1 << 31)))
            inv = sum(p["amt"] for p in op)
            for t in td.itertuples():
                nr = sum(1 for p in op if p["rid"] == t.rid); w = eq * t.pct / 100
                if nr >= t.mx or inv + w > eq: continue
                if t.rid == "P7add":
                    if not any(p["tk"] == t.ticker and p["rid"] == "P7" for p in op): continue
                    if any(p["tk"] == t.ticker and p["rid"] == "P7add" for p in op): continue
                elif any(p["tk"] == t.ticker for p in op): continue
                op.append(dict(rid=t.rid, tk=t.ticker, buy=t.buy, exit=t.exit, low=t.low,
                               cost=t.cost, stop=t.stop, amt=w, ex=i + t.hold)); inv += w
        curve.append(eq)
    C = pd.Series(curve); dd = (C / C.cummax() - 1) * 100
    yrs = len(ds) / 246
    return dict(nav=C.iloc[-1], cagr=(C.iloc[-1] ** (1 / yrs) - 1) * 100, mdd=dd.min(),
                win=np.mean(wins) * 100 if wins else np.nan, n=len(wins), byrid=byrid)

PERIODS = [("전체 2018~26", "20180101", "20991231"),
           ("학습 2018~22", "20180101", "20221231"),
           ("검증 2023~26", "20230101", "20991231"),
           ("붐 제외 ~2024", "20180101", "20241231")]
SEEDS = 25
R_ADD = dict(RULES); R_ADD["P7add"] = (KP, 60, None, 4, 5, ADD)
SA, SB = build(RULES), build(R_ADD)

print(f"  기간을 갈라 같은 시드끼리 짝지어 비교 (시드 {SEEDS}회 · 자산은 시작 1.0 배수)\n")
print(f"  {'기간':<14} {'현재 자산':>9} {'추가 자산':>9} {'수익금차':>9} {'이긴 시드':>8} "
      f"{'현재 낙폭':>9} {'추가 낙폭':>9} {'연수익 차':>9}")
VERD = {}
for nm, d0, d1 in PERIODS:
    ds = [d for d in adates if d0 <= d <= d1]
    A = [sim(SA, ds, seed=k) for k in range(SEEDS)]
    B = [sim(SB, ds, seed=k) for k in range(SEEDS)]
    dn = [b["nav"] - a["nav"] for a, b in zip(A, B)]
    winr = np.mean([x > 0 for x in dn]) * 100
    ma, mb = np.median([x["nav"] for x in A]), np.median([x["nav"] for x in B])
    da, db = np.median([x["mdd"] for x in A]), np.median([x["mdd"] for x in B])
    ca, cb = np.median([x["cagr"] for x in A]), np.median([x["cagr"] for x in B])
    print(f"  {nm:<14} {ma:>8.2f}배 {mb:>8.2f}배 {np.median(dn):>+8.2f}배 {winr:>7.0f}% "
          f"{da:>8.1f}% {db:>8.1f}% {cb-ca:>+8.2f}%p")
    VERD[nm] = dict(win=winr, dn=float(np.median(dn)), dmdd=db - da, dcagr=cb - ca)

print("\n  추가매수분이 실제로 번 돈 (규칙별 기여, 전체기간·시드 중앙값 기준 1회)")
b0 = sim(SB, [d for d in adates if d >= "20180101"], seed=0)
tot = sum(b0["byrid"].values())
for rid, v in sorted(b0["byrid"].items(), key=lambda x: -x[1]):
    tag = " ← 추가매수" if rid == "P7add" else ""
    print(f"    {rid:<7} {v:>+7.2f} (계좌 {v/tot*100:>5.1f}%){tag}")

print("\n  ── 판정 ──")
ok = True
for nm, v in VERD.items():
    good = v["dn"] > 0 and v["win"] >= 60 and v["dmdd"] > -2
    ok &= good
    print(f"    {'✅' if good else '❌'} {nm:<14} 수익금 {v['dn']:+.2f}배 · 이긴 시드 {v['win']:.0f}% · "
          f"낙폭 {v['dmdd']:+.1f}%p · 연수익 {v['dcagr']:+.2f}%p")
print(f"\n  {'✅ 네 기간 모두 통과 — 붐 구간에 기댄 결과가 아니다' if ok else '❌ 일부 기간에서 무너진다 — 채택 보류'}")
