# -*- coding: utf-8 -*-
"""[외인 매집] 추가매수 — 계좌 관점 검증.

규칙 단위 평균으로는 추가분이 최초분보다 나았다(754건 +17.34%, 게이트 6개 통과).
그러나 추가매수는 공짜가 아니다. 같은 돈으로 살 수 있었던 '다른 신규 신호' 를
포기하고, 60거래일짜리 자리를 하나 더 오래 붙잡는다. 그래서 계좌로 재야 한다.

지난번 [업종붕괴 이탈] 에서 배운 것: 자리 제한이 빡빡하면 무엇이든 좋아 보인다
(자리 제한 착시). 그래서 비중·자리를 여러 조합으로 돌려 결과가 유지되는지 본다.
그리고 같은 날 여러 신호 중 무엇이 체결되냐는 순서 운이므로 여러 번 섞어 중앙값을 쓴다.

사용: python addbuy_port.py
"""
import io, sys, gc
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

# ── [외인 매집] 의 '신호 연속 유지 + 이익 중' 을 추가매수 신호로 만든다 ──
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
FIRST = pd.Series(stk == 1, index=KP.index)      # 최초 신호만 (지금 우리가 사는 것)
print(f"  [외인 매집] 신호행 {int(c.sum()):,} · 최초 {int(FIRST.sum()):,} · 추가후보 {int(ADD.sum()):,}\n")

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
    """seed 를 주면 같은 날 신호 순서를 섞는다 — 어떤 게 체결되냐는 운이다."""
    eq = 1.0; op = []; curve = []; wins = []
    by = {i: g for i, g in S.groupby("di")}
    rng = np.random.default_rng(seed) if seed is not None else None
    for i, d in enumerate(ds):
        st = []
        for p in op:
            if p["ex"] <= i:
                hit = (p["stop"] == p["stop"]) and (p["low"] / p["buy"] - 1) * 100 <= -p["stop"] * 100
                r = (-p["stop"] * 100 - p["cost"]) if hit else ((p["exit"] / p["buy"] - 1) * 100 - p["cost"])
                eq += p["amt"] * r / 100; wins.append(r > 0)
            else: st.append(p)
        op = st; td = by.get(i)
        if td is not None:
            if rng is not None: td = td.sample(frac=1, random_state=int(rng.integers(1 << 31)))
            inv = sum(p["amt"] for p in op)
            for t in td.itertuples():
                nr = sum(1 for p in op if p["rid"] == t.rid); w = eq * t.pct / 100
                if nr >= t.mx or inv + w > eq: continue
                if t.rid == "P7add":
                    # 추가매수는 그 종목을 [외인 매집] 으로 이미 들고 있을 때만, 종목당 한 번만
                    if not any(p["tk"] == t.ticker and p["rid"] == "P7" for p in op): continue
                    if any(p["tk"] == t.ticker and p["rid"] == "P7add" for p in op): continue
                elif any(p["tk"] == t.ticker for p in op): continue
                op.append(dict(rid=t.rid, tk=t.ticker, buy=t.buy, exit=t.exit, low=t.low,
                               cost=t.cost, stop=t.stop, amt=w, ex=i + t.hold)); inv += w
        curve.append(eq)
    C = pd.Series(curve); dd = (C / C.cummax() - 1) * 100
    yrs = len(ds) / 246
    return dict(nav=C.iloc[-1], cagr=(C.iloc[-1] ** (1 / yrs) - 1) * 100,
                mdd=dd.min(), win=np.mean(wins) * 100 if wins else np.nan, n=len(wins))

def run(R, tag, seeds=15):
    S = build(R)
    rs = [sim(S, adates, seed=k) for k in range(seeds)]
    med = lambda k: float(np.median([r[k] for r in rs]))
    print(f"  {tag:<34} 연{med('cagr'):>6.2f}% · 자산 {med('nav'):>5.2f}배 · 낙폭 {med('mdd'):>6.1f}% "
          f"· 승률 {med('win'):>4.1f}% · 거래 {med('n'):>5.0f}건")
    return dict(cagr=med('cagr'), nav=med('nav'), mdd=med('mdd'), win=med('win'), n=med('n'))

print("  ── 현재 vs 추가매수 (자산은 시작 1.0 배수, 순서 운 15회 중앙값) ──")
A = run(RULES, "현재 (추가매수 없음)")
OUT = {}
for pct, mx in ((4, 5), (2, 5), (4, 3), (2, 3)):
    R = dict(RULES); R["P7add"] = (KP, 60, None, pct, mx, ADD)
    OUT[(pct, mx)] = run(R, f"추가매수 비중 {pct}% · 최대 {mx}종목")
print()
print("  ── 자리 제한 착시 점검: 계좌 전체 비중을 키우고 줄여도 결론이 같은가 ──")
for scale, nm in ((0.5, "전 규칙 비중 ×0.5 (자리 여유 많음)"), (1.5, "전 규칙 비중 ×1.5 (자리 빡빡)")):
    R0 = {k: (v[0], v[1], v[2], v[3] * scale, v[4], v[5]) for k, v in RULES.items()}
    a = run(R0, f"{nm} — 현재")
    R1 = dict(R0); R1["P7add"] = (KP, 60, None, 4 * scale, 5, ADD)
    b = run(R1, f"{nm} — 추가매수")
    print(f"      → 수익금 {'개선' if b['nav'] > a['nav'] else '악화'} "
          f"({(b['nav']-a['nav'])*100:+.1f}%p) · 낙폭 {b['mdd']-a['mdd']:+.1f}%p\n")
print("  ── 판정 ──")
for (pct, mx), b in OUT.items():
    d = (b["nav"] - A["nav"]) * 100
    ok = b["nav"] > A["nav"] and b["mdd"] >= A["mdd"] - 2
    print(f"    {'✅' if ok else '❌'} 비중{pct}%·최대{mx}종목: 수익금 {d:+.1f}%p · "
          f"낙폭 {b['mdd']-A['mdd']:+.1f}%p · 승률 {b['win']-A['win']:+.1f}%p")
print("\n  ※ 수익금이 늘어도 낙폭이 2%p 넘게 나빠지면 채택하지 않는다 — 우리는 안정성 우선이다.")
