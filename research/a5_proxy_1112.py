# -*- coding: utf-8 -*-
"""[예상 하회](A5) 과거 전체 재기 준비 — 장전 균형가(eq59) 녹화는 10-12~ 뿐이라, 과거에도 있는 'NXT 장전가'로 대신할 수 있나 (2026-11-12 사용자 "그림자 기간 말고 그 전 과거 전체 실측").
그림자 기간(녹화 있는 날)에서 NXT 거래 종목만 놓고 세 신호를 비교:
  eq   = (08:56 KRX 장전 균형가 − 시가) ÷ 어제 종가     ← 실전 A5
  n850 = (08:50 까지 NXT 마지막 체결 − 시가) ÷ 어제 종가  ← 토스 장전 1분봉으로 과거에도 만들 수 있음(받기 필요)
  n800 = (NXT 장전 첫 체결 − 시가) ÷ 어제 종가          ← 토스 일봉 시가(통합 봉)로 과거에도 이미 있음
각 신호 상위 10%(NXT 종목 안) 시가→종가 비용 뒤 · 서로 겹침 · 순위 상관.
"""
import glob, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(ROOT / "factory")); sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
import auction as AU

COST = 0.23
AD = BASE / "data" / "factory" / "auction"


def m1(d):
    f = BASE / "data" / "m1" / "KR" / "day" / ("%s.parquet" % d)
    if not f.exists(): return None
    X = pd.read_parquet(f, columns=["t", "ts", "o", "c", "v"]); X = X[X.v > 0].sort_values(["t", "ts"]); g = X.groupby("t")
    return pd.DataFrame({"o": g.o.first(), "c": g.c.last()})


def main():
    days = sorted(Path(p).name[3:11] for p in glob.glob(str(AD / "KR_*_am.parquet")))
    allm = sorted(Path(p).stem for p in glob.glob(str(BASE / "data" / "m1" / "KR" / "day" / "*.parquet")))
    rows = []
    for d in days:
        pv = max([x for x in allm if x < d], default=None)
        K, Kp = m1(d), (m1(pv) if pv else None)
        fx = AD / ("KR_%s_nxt.parquet" % d)
        if K is None or Kp is None or not fx.exists(): continue
        F = AU.features(d)
        if F is None or F.empty: continue
        F = F.set_index("ticker")
        X = pd.read_parquet(fx); X = X[X.today & (X.tag <= "085000")].sort_values(["ticker", "ts", "tag"])
        g = X.groupby("ticker")
        nx = pd.DataFrame({"n800": g.price.first(), "n850": g.price.last()})
        for t in nx.index:
            if t not in K.index or t not in Kp.index or t not in F.index: continue
            pc, o, c, e = Kp.c[t], K.o[t], K.c[t], F.eq59.get(t)
            if not (pc and o and c) or pc < 1000 or abs(o / pc - 1) >= 0.29 or not (e == e and e): continue
            rows.append(dict(d=d, t=t, eq=(e - o) / pc * 100, n850=(nx.n850[t] - o) / pc * 100, n800=(nx.n800[t] - o) / pc * 100,
                             ret=(c / o - 1) * 100 - COST))
    A = pd.DataFrame(rows)
    nd = A.d.nunique()
    print("그림자 기간 %d일(%s~%s) · NXT 장전 체결 있는 종목-일 %d · 하루 %.0f종목\n" % (nd, A.d.min(), A.d.max(), len(A), len(A) / nd))
    mkt = A.groupby("d").ret.mean()
    print("시장(이 종목들) 시가→종가 평균 %+.2f%%\n" % mkt.mean())
    print("| 신호 | 건당 | 승률 | 날 바구니 − 시장 | 플러스 날 | 실전(eq) 상위 10%와 겹침 | eq 와 순위 상관 |")
    print("|---|---|---|---|---|---|---|")
    pick = {}
    for k in ("eq", "n850", "n800"):
        q = A.groupby("d")[k].rank(pct=True)
        Z = A[q >= 0.9]; pick[k] = set(zip(Z.d, Z.t))
        bk = Z.groupby("d").ret.mean() - mkt
        rho = A.groupby("d").apply(lambda g: g[k].rank().corr(g["eq"].rank())).mean()
        print("| %s | %+.2f%% | %.0f%% | %+.2f%%p | %d/%d | %.0f%% | %.2f |" % (k, Z.ret.mean(), (Z.ret > 0).mean() * 100, bk.mean(), (bk > 0).sum(), len(bk),
              len(pick[k] & pick.get("eq", set())) / max(len(pick[k]), 1) * 100, rho))
    print("\n하위 10%(뒤집은 쪽) 확인:")
    for k in ("eq", "n850", "n800"):
        q = A.groupby("d")[k].rank(pct=True); Z = A[q <= 0.1]
        print("  %s 하위 10%% 건당 %+.2f%% · 날 바구니 − 시장 %+.2f%%p" % (k, Z.ret.mean(), (Z.groupby("d").ret.mean() - mkt).mean()))
    print("\n날짜별 날 바구니 − 시장 (eq / n850 / n800)")
    for d, g in A.groupby("d"):
        cells = []
        for k in ("eq", "n850", "n800"):
            z = g[g[k].rank(pct=True) >= 0.9]; cells.append("%+.2f" % (z.ret.mean() - g.ret.mean()))
        print("  %s %s" % (d, " / ".join(cells)))
    A.to_pickle(BASE / "data" / "a5_proxy_1112.pkl")


if __name__ == "__main__":
    main()
