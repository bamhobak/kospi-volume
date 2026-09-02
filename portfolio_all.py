# -*- coding: utf-8 -*-
"""제약 없는 전량 매수 시뮬레이션 — 신호가 나오면 무조건, 모두, 같은 금액으로 산다.

portfolio.py 는 '계좌 100 · 종목당 N% · 규칙당 최대 M종목' 제약을 걸어 실제로는
신호의 81~93% 를 못 샀다. 그 제약은 임의로 정한 것이므로 여기서는 없앤다.
자금 무한, 동시 보유 무제한, 종목당 같은 금액.

수익률 곡선: 매일 '그날 보유 중인 모든 포지션의 일간 수익률 평균' 을 쌓는다
(동일가중 · 보유 중인 것이 없는 날은 현금). 이래야 낙폭을 제대로 잴 수 있다.
손절이 있는 규칙은 보유 중 저가가 손절선에 닿은 날 청산한다.
"""
import io, sys
from pathlib import Path
import numpy as np, pandas as pd

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
BASE = Path(__file__).parent
src = (BASE / "portfolio.py").read_text(encoding="utf-8")
head = src.split("# 신호를 한 표로 모은다")[0]
ns = {"__file__": str(BASE / "portfolio.py")}
class _Sink(io.TextIOWrapper):
    def write(self, *a, **k): return 0
real = sys.stdout; sys.stdout = _Sink(io.BytesIO(), encoding="utf-8")
exec(compile(head, "portfolio.py", "exec"), ns)
sys.stdout = real
KP, KQ, RULES, IX = ns["KP"], ns["KQ"], ns["RULES"], ns["IX"]
base, dn60, up60 = ns["base"], ns["dn60"], ns["up60"]
NAME = {"P1": "조용한 신고가", "P2": "조정매집", "P3": "폭락반등", "P4": "업종붕괴 이탈",
        "P5": "자사주 낙폭", "P6": "깊은 이격", "P7": "외인 매집",
        "D1": "낙폭과대", "D2": "저PBR 낙폭"}
dates = sorted(set(KP.date) | set(KQ.date)); DI = {d: i for i, d in enumerate(dates)}
ND = len(dates)

# 종목별 일별 종가·저가 배열 (di 인덱스)
PX, LO = {}, {}
for K in (KP, KQ):
    K = K.assign(di=K.date.map(DI))
    for tk, gg in K.groupby("ticker", sort=False):
        if tk in PX: continue
        c = np.full(ND, np.nan); l = np.full(ND, np.nan)
        c[gg.di.values] = gg.close.values; l[gg.di.values] = gg.low.values
        PX[tk] = c; LO[tk] = l
print(f"가격 패널 {len(PX):,}종목 · {ND}거래일")

def signals(rules):
    out = []
    for rid, (K, hold, stop, pct, mx, cond) in rules.items():
        X = K[cond.fillna(False)].copy()
        X["rid"] = rid; X["hold"] = hold
        X["stop"] = stop * 100 if stop else np.nan     # portfolio.py 는 0.15 처럼 비율로 둔다
        X["di"] = X.date.map(DI)
        out.append(X[["date", "ticker", "rid", "hold", "stop", "buy", "cost", "di"]])
    S = pd.concat(out).dropna(subset=["buy", "cost"])
    S = S[S.buy > 0].sort_values(["di", "rid"])
    # 같은 규칙·같은 종목이 보유기간 안에 다시 걸리면 재진입 불가(중복 신호 제거)
    keep, last = [], {}
    for rid, t, i, h, ix in zip(S.rid.values, S.ticker.values, S.di.values, S.hold.values, S.index):
        k = (rid, t)
        if last.get(k, -10**9) >= i: continue
        last[k] = i + h; keep.append(ix)
    return S.loc[keep].reset_index(drop=True)

def run(rules, label):
    S = signals(rules)
    daily = [[] for _ in range(ND)]     # 날짜별 보유 포지션의 그날 수익률
    recs = []
    for t in S.itertuples():
        c, lo = PX.get(t.ticker), LO.get(t.ticker)
        if c is None: continue
        i0 = t.di + 1                                    # 다음날 시가 매수 → 그날부터 보유
        i1 = min(t.di + t.hold, ND - 1)
        if i0 > i1: continue
        stop_px = t.buy * (1 - t.stop / 100) if t.stop == t.stop else None
        prev = t.buy; tot = 1.0; ended = i1
        for i in range(i0, i1 + 1):
            px = c[i]
            if px != px: continue
            if stop_px is not None and lo[i] == lo[i] and lo[i] <= stop_px:
                r = stop_px / prev - 1                   # 손절가에 청산
                daily[i].append(r); tot *= 1 + r; ended = i; break
            r = px / prev - 1
            daily[i].append(r); tot *= 1 + r; prev = px
        ret = (tot - 1) * 100 - t.cost                   # 비용은 진입 시 1회
        recs.append({"rid": t.rid, "date": t.date, "yr": t.date[:4], "r": ret, "hold_end": ended})
    R = pd.DataFrame(recs)
    nav = [1.0]
    for i in range(ND):
        m = np.mean(daily[i]) if daily[i] else 0.0
        nav.append(nav[-1] * (1 + m))
    C = pd.DataFrame({"date": dates, "nav": nav[1:]})
    yrs = ND / 252
    dd = (C.nav / C.nav.cummax() - 1) * 100
    dl = C.nav.pct_change().dropna()
    inv = np.mean([1 if daily[i] else 0 for i in range(ND)]) * 100
    npos = np.mean([len(daily[i]) for i in range(ND)])
    print(f"  {label:<18} {len(R):>5}건 {C.nav.iloc[-1]:>7.2f}배 연{(C.nav.iloc[-1]**(1/yrs)-1)*100:>7.2f}% "
          f"낙폭{dd.min():>7.1f}% 샤프{dl.mean()/dl.std()*np.sqrt(252):>6.2f} "
          f"승률{(R.r>0).mean()*100:>4.0f}% 거래당{R.r.mean():>+6.2f}% 중앙{R.r.median():>+6.2f}% "
          f"보유일{inv:>3.0f}% 평균{npos:>5.1f}종목")
    return R, C

print(f"\n{'='*150}\n## 제약 없는 전량 매수 (동일가중 · 자금 무한)\n{'='*150}")
print(f"  {'설정':<18} {'신호':>7} {'최종':>9} {'연수익':>10} {'최대낙폭':>10} {'샤프':>8} "
      f"{'승률':>6} {'거래당':>9} {'중앙':>9} {'보유일':>6} {'동시보유':>9}")
RB, CB = run(RULES, "현재(fromlo 적용)")
NOF = dict(RULES)
_, h, s, p, m, c = RULES["P7"]
import re
NOF["P7"] = (KP, h, s, p, m, base(KP, 30) & up60(KP) & (KP["cap조"] >= 1) & (KP["cap조"] < 10)
             & (KP.fw20 >= 1) & (KP.ow60 < 0.4) & (KP.r16 >= 100) & (KP.r16 < 150) & (KP.fromhi >= -15))
RA, CA = run(NOF, "fromlo 없음(이전)")

print(f"\n## 규칙별 (제약 없음 · 현재 설정)")
print(f"  {'규칙':<16} {'신호':>6} {'승률':>6} {'거래당':>9} {'중앙':>9} {'최악':>9}")
for rid in ["P1", "P2", "P3", "P4", "P5", "P6", "P7", "D1", "D2"]:
    z = RB[RB.rid == rid]
    if not len(z): continue
    print(f"  [{NAME[rid]}]{'':<{max(0,13-len(NAME[rid]))}} {len(z):>6} {(z.r>0).mean()*100:>5.0f}% "
          f"{z.r.mean():>+8.2f}% {z.r.median():>+8.2f}% {z.r.min():>+8.1f}%")
print(f"\n  전체{'':<12} {len(RB):>6} {(RB.r>0).mean()*100:>5.0f}% {RB.r.mean():>+8.2f}% "
      f"{RB.r.median():>+8.2f}% {RB.r.min():>+8.1f}%")

print(f"\n## 연도별 (제약 없음 · 현재 설정)")
print(f"  {'연도':<6} {'신호':>6} {'승률':>6} {'거래당':>9} {'계좌수익':>10}")
for y in [str(x) for x in range(2018, 2027)]:
    z = RB[RB.yr == y]; cy = CB[CB.date.str[:4] == y]
    if not len(z): continue
    ry = (cy.nav.iloc[-1] / cy.nav.iloc[0] - 1) * 100 if len(cy) else np.nan
    print(f"  {y:<6} {len(z):>6} {(z.r>0).mean()*100:>5.0f}% {z.r.mean():>+8.2f}% {ry:>+9.2f}%")

kk = IX[(IX.date >= dates[0]) & (IX.date <= dates[-1])]
bh = kk.Close.iloc[-1] / kk.Close.iloc[0]; yrs = ND / 252
print(f"\n  코스피 매수후보유    {bh:>7.2f}배 연{(bh**(1/yrs)-1)*100:>7.2f}% "
      f"낙폭{((kk.Close/kk.Close.cummax())-1).min()*100:>7.1f}%")
