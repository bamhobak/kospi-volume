# -*- coding: utf-8 -*-
"""물타기 2차 — 거래별이 아니라 **계좌**로 잰다.

1차(mulddagi.py)에서 물타기가 모든 지표에서 원본보다 좋게 나왔다(승률 66.8→74.4%,
평균 12.72→14.89, 최악5% -10.4→-8.6). 그대로 믿으면 안 되는 이유가 셋이다.

 ① 우리 규칙 9개 중 7개가 **낙폭 반등** 규칙이다. 떨어진 걸 사서 반등을 먹는 구조에서
    더 떨어졌을 때 또 사면 좋은 게 당연하다 — '물타기가 좋다' 가 아니라
    '진입 조건이 더 좋은 가격에 한 번 더 성립했다' 에 가깝다.
 ② **비중 2배의 대가**를 안 쟀다. 현금이 묶여 다른 신호를 못 사는 효과가 빠졌다.
 ③ **최악 5% 가 좋아진 건 착시**다. 두 몫 평균이라 분산만 줄었을 뿐 노출이 2배라
    실제 손실 금액은 더 크다. 자리를 줄이며 노출까지 줄여 틀렸던 것과 같은 실수다.

그래서 계좌로 잰다 — 물타기 몫도 **현금을 쓰고 자리를 차지**하게 한다.
비교를 공평하게 하려면 노출을 맞춰야 하므로 세 가지를 나란히 낸다.
  A 원본                     종목당 비중 그대로
  B 물타기(비중 그대로)        -X% 에서 같은 금액을 한 번 더 → 그 종목 노출이 2배가 된다
  C 물타기(비중 절반에서 시작)  처음에 절반만 사고 -X% 에서 나머지 절반 → **노출은 A 와 같다**
C 가 진짜 물어야 할 질문이다: **같은 돈을 한 번에 넣을까, 나눠서 떨어지면 더 넣을까.**

    python mulddagi2.py
"""
import sys, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd

BASE = Path(__file__).parent
src = open(BASE / "portfolio.py", encoding="utf-8").read().split("# @@ANALYSIS")[0]
exec(src.split('"""', 2)[2])

ALL = pd.concat([pd.read_pickle(BASE / "data" / f)[["ticker", "date", "close"]]
                 for f in ("panel_kp.pkl", "panel_kq.pkl")], ignore_index=True)
ALL = ALL.drop_duplicates(["ticker", "date"]).sort_values(["ticker", "date"])
ALL["di"] = ALL.date.map(DI)
CL = {t: g[["di", "close"]].values for t, g in ALL.groupby("ticker", sort=False)}

def prep(th):
    """신호마다 물타기 지점을 미리 찾아 둔다 — (걸렸나, 그때 가격)."""
    hit, px = [], []
    for t in S.itertuples():
        a = CL.get(t.ticker)
        p = a[(a[:, 0] > t.di) & (a[:, 0] <= t.di + t.hold)] if a is not None else None
        h = None
        if p is not None and len(p):
            m = p[p[:, 1] <= t.buy * (1 - th)]
            if len(m): h = float(m[0, 1])
        hit.append(h is not None); px.append(h if h else np.nan)
    z = S.copy(); z["hit"] = hit; z["addpx"] = px
    return z

def sim(SS, mode, cash_cap=1.0):
    """mode: 'A' 원본 · 'B' 물타기(비중 그대로) · 'C' 물타기(절반에서 시작).
    물타기 몫도 현금을 쓴다. 규칙별 자리 상한은 **종목 수** 기준이라 추가매수는 자리를 안 먹는다."""
    eq = 1.0; open_pos = []; curve = []; blocked = 0; adds = 0
    byd = {}
    for t in SS.itertuples(): byd.setdefault(t.di, []).append(t)
    for i, d in enumerate(dates):
        still = []
        for p in open_pos:
            if p["exit_di"] <= i:
                eq += p["amt"] * ((p["exit"] / p["buy"] - 1) * 100 - p["cost"]) / 100
                eq += p["amt2"] * ((p["exit"] / p["px2"] - 1) * 100 - p["cost"]) / 100 if p["amt2"] else 0
            else: still.append(p)
        open_pos = still
        # 물타기 실행 — 보유 중인 것 중 오늘 문턱을 밟았고 아직 안 넣은 것
        if mode in ("B", "C"):
            for p in open_pos:
                if p["amt2"] or not p["hit"]: continue
                a = CL.get(p["ticker"])
                if a is None: continue
                row = a[a[:, 0] == i]
                if not len(row) or row[0, 1] > p["buy"] * (1 - p["th"]): continue
                inv = sum(x["amt"] + x["amt2"] for x in open_pos)
                if inv + p["add_amt"] > eq * cash_cap: continue
                p["amt2"] = p["add_amt"]; p["px2"] = p["px2_planned"]; adds += 1
        for t in byd.get(i, []):
            n_rule = sum(1 for p in open_pos if p["rid"] == t.rid)
            base_w = eq * t.pct / 100 * (0.5 if mode == "C" else 1.0)
            inv = sum(x["amt"] + x["amt2"] for x in open_pos)
            if n_rule >= t.mx or inv + base_w > eq * cash_cap or any(
                    p["ticker"] == t.ticker for p in open_pos):
                blocked += 1; continue
            open_pos.append(dict(rid=t.rid, ticker=t.ticker, buy=t.buy, exit=t.exit, cost=t.cost,
                                 amt=base_w, amt2=0.0, px2=np.nan, exit_di=i + t.hold,
                                 hit=bool(t.hit), th=t.th, px2_planned=t.addpx,
                                 add_amt=eq * t.pct / 100 * (0.5 if mode == "C" else 1.0)))
        curve.append((d, eq, sum(x["amt"] + x["amt2"] for x in open_pos) / eq if eq > 0 else 0))
    for p in open_pos:
        eq += p["amt"] * ((p["exit"] / p["buy"] - 1) * 100 - p["cost"]) / 100
        if p["amt2"]: eq += p["amt2"] * ((p["exit"] / p["px2"] - 1) * 100 - p["cost"]) / 100
    C = pd.DataFrame(curve, columns=["date", "nav", "expo"])
    mdd = ((C.nav / C.nav.cummax()) - 1).min() * 100
    r1 = (C.nav / C.nav.shift(252) - 1).min() * 100
    yrs = len(dates) / 252
    return dict(nav=eq, cagr=(eq ** (1 / yrs) - 1) * 100, mdd=mdd, worst1y=r1,
                expo=C.expo.mean() * 100, adds=adds, blocked=blocked)

print(f"\n{'='*112}")
print("물타기를 계좌로 — 물타기 몫도 현금을 쓴다 (국내 9규칙 · 2005~2026)")
print("=" * 112)
print(f"  {'구성':<34}{'최종':>10}{'연':>8}{'최대낙폭':>10}{'최악1년':>9}{'평균노출':>9}{'추가매수':>9}{'막힘':>8}")
for th in (0.05, 0.10, 0.15):
    SS = prep(th); SS["th"] = th
    if th == 0.05:
        a = sim(SS, "A")
        print(f"  {'A 원본 (추가매수 없음)':<34}{a['nav']:>9.2f}배{a['cagr']:>7.2f}%{a['mdd']:>9.1f}%"
              f"{a['worst1y']:>8.1f}%{a['expo']:>8.0f}%{'-':>9}{a['blocked']:>8}")
        print()
    for mode, nm in (("B", "비중 그대로 → 노출 2배"), ("C", "절반에서 시작 → 노출 동일")):
        r = sim(SS, mode)
        print(f"  {f'{mode} 물타기 -{th*100:.0f}% · {nm}':<34}{r['nav']:>9.2f}배{r['cagr']:>7.2f}%"
              f"{r['mdd']:>9.1f}%{r['worst1y']:>8.1f}%{r['expo']:>8.0f}%{r['adds']:>9}{r['blocked']:>8}")
    print()
