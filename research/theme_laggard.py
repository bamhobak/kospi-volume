# -*- coding: utf-8 -*-
"""상승장 테마(업종) 후발주 — 같은 테마가 평균 많이 올랐는데 본인은 덜 오른 종목을 산다 (2026-10-24 사용자
"상승장에서 같은 테마가 평균 오른거 대비해서 적게 오른 종목들 매수 실측해봐").

H0238(업종 안 후발주 · 국면 조건 없음 · 대장주 3개 기준)은 2단계 기각. 이번엔
  ① 상승장(코스피 종가 > 60일선 — portfolio.py dn60 의 반대)만
  ② 그 종목이 든 테마/업종의 **본인 뺀 평균** N일 수익 대비 덜 오름(여러 테마면 가장 센 테마)
테마 = 네이버 2026-08-28 구성을 과거에 씌움(뒤늦은 눈 편향 — 지금 남은 종목·지금 붙은 테마) → 업종(KSIC up, 그날 자료)판을 같이 낸다.
매매: 신호 다음날 시가 → h 거래일 뒤 종가(패널 n{h} — 비용·미끄러짐·폐지 포함). 같은 종목 보유 중 재매수 없음.
견줌: ① 같은 날 유니버스(거래대금 상위 40%) 아무 종목 같은 보유 평균 → 초과
      ② 같은 날 같은 강세 무리에서 **따라 오른** 종목(본인 ≥ 평균 -2%p)  ③ 같은 후발 조건을 하락장에서
구간: 참고 2010~15 / 학습 2016~22 / 검증 2023~ (학습 시작 2016 — learning-start-2016).
    python research/theme_laggard.py
"""
import sys, time
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(BASE))
from verdict import log_trials
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))
HS = (5, 10, 20, 40, 60)
PER = (("참고", "20100101", "20151231"), ("학습", "20160101", "20221231"), ("검증", "20230101", "20991231"))


def bull_map():
    cp = ROOT / "cache" / "ks11.pkl"
    if cp.exists():
        IX = pd.read_pickle(cp)
    else:
        import FinanceDataReader as fdr
        IX = fdr.DataReader("KS11", "2004-06-01")[["Close"]]
    IX = IX.copy()
    IX["ma60"] = IX.Close.rolling(60).mean()
    d = IX.index.strftime("%Y%m%d")
    return dict(zip(d, IX.Close > IX.ma60)), d.max()


def strongest(M, col, key):
    """M: (key, ticker, date, col) — 같은 날 같은 무리의 본인 뺀 평균(oth). 종목이 여러 무리면 oth 가장 큰 무리."""
    g = M.groupby([key, "date"])[col]
    M = M.assign(s=g.transform("sum"), c=g.transform("size"))
    M = M[M.c >= 5]
    M = M.assign(oth=(M.s - M[col]) / (M.c - 1))
    M = M.sort_values("oth", ascending=False).drop_duplicates(["ticker", "date"])
    return M[["ticker", "date", "oth"]]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    t0 = time.time()
    A = pd.read_pickle(BASE / "data/kr_scan.pkl")
    A = A[A.date >= "20100101"][["ticker", "date", "amt20", "up", "ret10", "ret20"] + [f"n{h}" for h in HS]].copy()
    A["uni"] = A.groupby("date").amt20.rank(pct=True) >= 0.6
    bm, ixlast = bull_map()
    A["bull"] = A.date.map(bm).fillna(False).astype(bool)
    BM = {h: A[A.uni].groupby("date")[f"n{h}"].mean() for h in HS}
    di = {d: i for i, d in enumerate(sorted(A.date.unique()))}
    A["di"] = A.date.map(di)
    S = pd.read_csv(BASE / "data/sector.csv", dtype=str)
    S = S[S.kind == "theme"][["gname", "ticker"]].drop_duplicates()

    # 무리 강세(본인 뺀 평균) — 테마 20·10일, 업종 20·10일
    for W in (20, 10):
        c = f"ret{W}"
        base = A[["ticker", "date", c]].dropna(subset=[c])
        T = strongest(S.merge(base, on="ticker"), c, "gname").rename(columns={"oth": f"th{W}"})
        U = strongest(A[["up", "ticker", "date", c]].dropna(subset=["up", c]), c, "up").rename(columns={"oth": f"up{W}"})
        A = A.merge(T, on=["ticker", "date"], how="left").merge(U, on=["ticker", "date"], how="left")
        P_ = "테마·업종 %d일 강세 계산 %.1f분" % (W, (time.time() - t0) / 60)
        print(P_, flush=True)
    A = A.sort_values(["ticker", "date"]).reset_index(drop=True)

    def trades(m, h):
        Z = A[m.fillna(False) & A.uni & A[f"n{h}"].notna()].sort_values("di")
        keep, last = [], {}
        for t, i, ix in zip(Z.ticker.values, Z.di.values, Z.index):
            if last.get(t, -10 ** 9) >= i:
                continue
            last[t] = i + h
            keep.append(ix)
        Z = Z.loc[keep]
        return Z.assign(ret=Z[f"n{h}"], ex=Z[f"n{h}"] - Z.date.map(BM[h]))

    def cell(Z, a, b):
        z = Z[(Z.date >= a) & (Z.date <= b)]
        if len(z) < 20:
            return "%d건" % len(z), None
        t = z.ex.mean() / (z.ex.std(ddof=1) / np.sqrt(len(z))) if len(z) > 2 else np.nan
        return "%+.2f(%+.2f) %d%% · %d" % (z.ret.mean(), z.ex.mean(), (z.ret > 0).mean() * 100, len(z)), t

    n = 0
    keep_years = {}
    for src, key in (("테마(08-28 구성을 과거에 씌움)", "th"), ("업종(KSIC · 그날 자료)", "up")):
        own20, oth20 = A.ret20, A[key + "20"]
        own10, oth10 = A.ret10, A[key + "10"]
        lag = lambda T, G, own=own20, oth=oth20, floor=True: (oth >= T) & (own <= oth - G) & ((own >= -10) if floor else True)
        groups = [
            ("**기본** 상승장 · 무리 +10%↑ · 본인 10%p↑ 덜 오름", A.bull & lag(10, 10)),
            ("상승장 · 무리 +5%↑ · 5%p↑ 덜", A.bull & lag(5, 5)),
            ("상승장 · 무리 +15%↑ · 10%p↑ 덜", A.bull & lag(15, 10)),
            ("상승장 · 무리 +20%↑ · 15%p↑ 덜", A.bull & lag(20, 15)),
            ("상승장 · 무리 +10%↑ · 15%p↑ 덜", A.bull & lag(10, 15)),
            ("상승장 · 10일 기준 무리 +7%↑ · 7%p↑ 덜", A.bull & lag(7, 7, own10, oth10)),
            ("상승장 · 기본 · 바닥(-10%) 조건 뺌", A.bull & lag(10, 10, floor=False)),
            ("대조 · 같은 후발 조건 **하락장**", ~A.bull & lag(10, 10)),
            ("대조 · 국면 무관 후발", lag(10, 10)),
            ("대조 · 상승장 · 무리 +10%↑에서 **따라 오른** 종목", A.bull & (oth20 >= 10) & (own20 >= oth20 - 2)),
        ]
        P("## %s" % src); P("")
        P("- 칸 = 평균 수익(초과) 승률 · 건수 · 다음날 시가 매수 → h 거래일 뒤 종가 · 비용 뒤 · 초과 = 같은 날 유니버스 같은 보유 평균 대비"); P("")
        P("| 무리 | 보유 | 참고 2010~15 | 학습 2016~22 | 검증 2023~ | 초과 t(학습/검증) |"); P("|---|---|---|---|---|---|")
        for lab, m in groups:
            for h in HS:
                Z = trades(m, h); n += 1
                cs = [cell(Z, a, b) for _, a, b in PER]
                P("| %s | %d일 | %s | %s | %s | %s |" % (lab if h == HS[0] else "", h, cs[0][0], cs[1][0], cs[2][0],
                  "/".join("—" if c[1] is None or not np.isfinite(c[1]) else "%.1f" % c[1] for c in cs[1:])))
                if h in (20, 40) and lab.startswith(("**기본**", "대조 · 상승장")):
                    keep_years[(src, lab, h)] = Z
        P("")
    P("## 해마다 초과(%p) — 기본과 '따라 오른' 대조"); P("")
    yrs = [str(y) for y in range(2010, 2027)]
    P("| 무리 · 보유 | 승률 | " + " | ".join(y[2:] for y in yrs) + " |"); P("|---|---|" + "---|" * len(yrs))
    for (src, lab, h), Z in keep_years.items():
        yr = Z.groupby(Z.date.str[:4]).ex.mean()
        cnt = Z.groupby(Z.date.str[:4]).size()
        P("| %s %s · %d일 | %.0f%% | %s |" % (src[:2], lab.replace("**", "")[:22], h, (Z.ret > 0).mean() * 100,
          " | ".join(("%+.1f" % yr[y]) if y in yr.index and cnt[y] >= 5 else "·" for y in yrs)))
    P(""); P("(패널 끝 %s · 코스피 지수 끝 %s · 칸 %d · %.1f분)" % (A.date.max(), ixlast, n, (time.time() - t0) / 60))
    log_trials("theme_laggard_%s" % time.strftime("%Y%m%d"), n)
    (ROOT / "reports" / ("theme_laggard_%s.md" % time.strftime("%Y%m%d"))).write_text("\n".join(OUT) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
