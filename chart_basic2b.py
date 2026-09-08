# -*- coding: utf-8 -*-
"""강의 2편 후속 — 월봉 12평이 진 이유를 파고, 강사가 실제로 예로 든 조건으로 다시 잰다.

1차(chart_basic2.py)에서 월봉 12평 시스템은 전 종목 동일가중 기준으로 항상보유에
전구간 -1.3~-2.1%p/월 뒤졌고 낙폭도 더 깊었다. 강사의 주장과 정반대다. 반박 가능성 셋:
  ⓐ 그가 든 예는 삼성전자·넷플릭스·비트코인 — **대형 우량주**다. 잡주까지 넣어 진 것 아닌가.
  ⓑ 그가 든 또 다른 예는 **지수 자체**(코스피·코스닥 월봉). 개별주가 아니라 지수 타이밍이다.
  ⓒ 낙폭이 더 깊은 건 위에 남은 소수 종목에 몰려서일 수 있다 — 보유 종목 수를 본다.
셋 다 확인한다. 지수 타이밍은 무위험 현금 0% 가정.
"""
import io, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
import FinanceDataReader as fdr

BASE = Path(__file__).parent

def load(f):
    K = pd.read_pickle(BASE / "data" / f).sort_values(["ticker", "date"]).reset_index(drop=True)
    K["pref"] = ~K.ticker.str.endswith("0")
    return K

KP = load("panel_kp.pkl"); KQ = load("panel_kq.pkl")

def base(K, amt=3):
    return ((~K.pref) & (K.close >= 1000) & (~K.dil.fillna(False)) & (K.amt20.fillna(0) >= amt))

def mdd(c):
    v = (1 + c / 100).cumprod()
    return float((v / v.cummax() - 1).min() * 100)

def monthly(K, topn=None):
    Z = K[base(K)].copy()
    Z["m"] = Z.date.str[:6]
    last = Z.groupby(["ticker", "m"], sort=False).tail(1).copy().sort_values(["ticker", "m"])
    g = last.groupby("ticker", sort=False)
    last["ma12"] = g.close.transform(lambda s: s.rolling(12, min_periods=12).mean())
    last["P"] = last.buy
    last["Pn"] = g.P.shift(-1)
    last["mret"] = (last.Pn / last.P - 1) * 100
    last["above"] = last.close > last.ma12
    last["mn"] = g.m.shift(-1)
    last = last.dropna(subset=["mret", "ma12", "mn"])
    if topn:                                   # 그 달 시총 상위 N 만 (대형 우량주 한정)
        last = last[last.groupby("m").marcap.rank(ascending=False, method="first") <= topn]
    return last

def curve(M, cost=1.15):
    rows = []
    for mn, g in M.groupby("mn"):
        on = g[g.above]
        rows.append((mn, on.mret.mean() if len(on) else 0.0, g.mret.mean(), len(on), len(g)))
    C = pd.DataFrame(rows, columns=["m", "sys", "bh", "non", "nall"]).sort_values("m")
    sw = M.assign(prev=M.groupby("ticker").above.shift(1)).dropna(subset=["prev"])
    tr = sw.groupby("mn").apply(lambda g: (g.above != g.prev).mean() * cost)
    C["sys"] = C.sys - C.m.map(tr).fillna(0)
    return C

PER = (("학습 2016~22", "201601", "202212"), ("검증 2023~26", "202301", "209912"),
       ("스트레스 2005~15", "200501", "201512"), ("전구간 2005~26", "200501", "209912"))

def show(C, tag):
    print(f"\n[{tag}] 월 {len(C)}개 · 보유 종목수 중앙 {C.non.median():.0f}/{C.nall.median():.0f} "
          f"· 보유비율 {(C.non / C.nall).mean() * 100:.0f}%")
    for pn, lo, hi in PER:
        z = C[(C.m >= lo) & (C.m <= hi)]
        if len(z) < 12: continue
        s = (1 + z.sys / 100).prod(); b = (1 + z.bh / 100).prod(); yr = len(z) / 12
        print(f"  {pn:<16} 12평 {s:>7.2f}배(연{(s ** (1 / yr) - 1) * 100:>6.1f}%) 낙폭{mdd(z.sys):>5.0f}%  |  "
              f"항상보유 {b:>7.2f}배(연{(b ** (1 / yr) - 1) * 100:>6.1f}%) 낙폭{mdd(z.bh):>5.0f}%  |  "
              f"초과 {z.sys.mean() - z.bh.mean():+.2f}%p/월")

print("=" * 104)
print("ⓐ 대형 우량주 한정 — 강사가 든 예(삼성전자급)로 좁히면 달라지나")
print("=" * 104)
for K, mk in ((KP, "코스피"), (KQ, "코스닥")):
    for n in (100, 300, None):
        M = monthly(K, n)
        show(curve(M), f"{mk} 시총상위 {n if n else '전체'}")

print("\n" + "=" * 104)
print("ⓑ 지수 자체에 월봉 12평 — 코스피·코스닥·나스닥·비트코인 (현금 0%)")
print("=" * 104)
for code, nm, start in (("KS11", "코스피", "1990-01-01"), ("KQ11", "코스닥", "1997-01-01"),
                        ("IXIC", "나스닥", "1985-01-01"), ("US500", "S&P500", "1985-01-01"),
                        ("BTC/KRW", "비트코인", "2014-01-01")):
    try:
        D = fdr.DataReader(code, start)
    except Exception as e:
        print(f"  {nm}: 데이터 없음 ({e})"); continue
    D = D[D.Close > 0].copy()
    D["m"] = D.index.strftime("%Y%m")
    M = D.groupby("m").Close.last().to_frame("c")
    M["ma12"] = M.c.rolling(12, min_periods=12).mean()
    M["r"] = M.c.pct_change().shift(-1) * 100          # 이 달 말 판정 → 다음 달 수익
    M["on"] = (M.c > M.ma12)
    M = M.dropna(subset=["r", "ma12"])
    sw = M.on != M.on.shift(1)
    M["sys"] = np.where(M.on, M.r, 0.0) - sw.astype(float) * 0.30   # 지수 ETF 왕복비용 0.3%
    yr = len(M) / 12
    s = (1 + M.sys / 100).prod(); b = (1 + M.r / 100).prod()
    print(f"  {nm:<8} {M.index[0]}~{M.index[-1]} {len(M):>4}개월 · 보유 {M.on.mean() * 100:>3.0f}% · "
          f"매매 {sw.sum()}회")
    print(f"           12평 {s:>8.2f}배(연{(s ** (1 / yr) - 1) * 100:>6.1f}%) 낙폭{mdd(M.sys):>5.0f}%  |  "
          f"항상보유 {b:>8.2f}배(연{(b ** (1 / yr) - 1) * 100:>6.1f}%) 낙폭{mdd(M.r):>5.0f}%")
    for pn, lo, hi in PER:
        z = M[(M.index >= lo) & (M.index <= hi)]
        if len(z) < 24: continue
        s2 = (1 + z.sys / 100).prod(); b2 = (1 + z.r / 100).prod(); y2 = len(z) / 12
        print(f"           {pn:<14} 12평 {s2:>6.2f}배(연{(s2 ** (1 / y2) - 1) * 100:>6.1f}%) 낙폭{mdd(z.sys):>5.0f}%"
              f"  |  항상보유 {b2:>6.2f}배(연{(b2 ** (1 / y2) - 1) * 100:>6.1f}%) 낙폭{mdd(z.r):>5.0f}%")

print("\n" + "=" * 104)
print("ⓒ 12평이 진 해를 뜯어본다 — 코스피 전체, 2008·2019·2022·2026")
print("=" * 104)
C = curve(monthly(KP))
for y in ("2008", "2019", "2022", "2026"):
    z = C[C.m.str[:4] == y]
    print(f"  {y}  " + " ".join(f"{r.m[4:]}:{r.sys:+.0f}/{r.bh:+.0f}({r.non:.0f}종)" for _, r in z.iterrows()))
