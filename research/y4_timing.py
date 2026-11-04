# -*- coding: utf-8 -*-
"""1억 1년 — 시장 전체 타이밍 새로 찾기(2026-11-05 사용자 "1 2번 해봐" 중 2번).
코스피(KS11, 배당 빼고)를 들고 있을지 현금일지 — 오늘 종가에 아는 값으로 정하고 내일 종가까지 그대로(바꿀 때 0.1%).
기존 지수 덮개(60일선 ±3%)와 지수 자체 추세(이동평균 거리·모멘텀)는 안 쓴다.
신호(전부 오늘 종가 무렵까지 아는 값, 미장은 '어제 밤' 까지):
  vol20·vol5/60(지수 변동성) · br20·br50(20·50일선 위 종목 비율) · ad10(10일 오른/내린 종목 수 비) · nh20(20일 신고가 − 신저가 종목 비)
  sv(시장 공매도 거래 비중 5일) · fx20(원/달러 20일 변화) · vix(VIX) · vixc(VIX 5일 변화) · sp1(S&P 어제 등락) · sp20(S&P 20일 등락)
  ff5·ff20(시장 외인 순매수 5·20일 ÷ 시장 거래대금, 2018~) · dow(요일) · tom(월말 2일+월초 3일) · win(11~4월)
조건 = 신호가 찾기 구간 분포의 30·50·70% 아래/위(문턱은 찾기 구간에서만 정함) · 하나 또는 둘(AND) — 그날 들고 있음
찾기 2005~2022(외인 신호는 2018~): 샤프 − 그냥 들고 있기 샤프 ≥ 0.15 · 들고 있는 날 ≥ 30% · 1년 바꾸기 ≤ 30번
확인 2023-01~2025-10: 샤프가 그냥 들고 있기보다 높고 연 수익 > 0
고르기 = 두 구간 샤프 우위 중 작은 쪽이 가장 큰 것 · 굴리기 2025-11-05~2026-11-04
    python research/y4_timing.py
"""
import sys, sqlite3, itertools
from pathlib import Path
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
import FinanceDataReader as fdr

LEARN, VALID, RUN = ("20050101", "20221231"), ("20230101", "20251031"), ("20251104", "20261103")   # 정하는 날 기준 — 받는 등락은 11-05~11-04
SWC = 0.10
CACHE = BASE / "data" / "y4_sig.pkl"
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))


def signals():
    if CACHE.exists(): return pd.read_pickle(CACHE)
    K = fdr.DataReader("KS11", "2003-06-01"); K = K[K.Close > 0]; K.index = K.index.strftime("%Y%m%d")
    S = pd.DataFrame(index=K.index); S["ret"] = K.Close.pct_change() * 100
    r = S.ret
    S["vol20"] = r.rolling(20).std(); S["vol5_60"] = r.rolling(5).std() / r.rolling(60).std()
    A = pd.read_pickle(BASE / "data" / "y1_kr.pkl")[["ticker", "date", "close", "high", "low", "pref"]]
    A = A[(A.date >= "20030101") & ~A.pref.fillna(False).astype(bool)].sort_values(["ticker", "date"])
    g = A.groupby("ticker").close
    A["a20"] = A.close > g.transform(lambda s: s.rolling(20).mean())
    A["a50"] = A.close > g.transform(lambda s: s.rolling(50).mean())
    A["chg"] = np.sign(g.diff())
    A["h20"] = A.close >= g.transform(lambda s: s.rolling(20).max())
    A["l20"] = A.close <= g.transform(lambda s: s.rolling(20).min())
    A = A[A.close >= 1000]
    D = A.groupby("date").agg(br20=("a20", "mean"), br50=("a50", "mean"), up=("chg", lambda x: (x > 0).sum()), dn=("chg", lambda x: (x < 0).sum()),
                              h20=("h20", "mean"), l20=("l20", "mean"))
    D["ad10"] = D.up.rolling(10).sum() / D.dn.rolling(10).sum().replace(0, np.nan); D["nh20"] = D.h20 - D.l20
    S = S.join(D[["br20", "br50", "ad10", "nh20"]])
    k = sqlite3.connect(BASE / "data" / "krx_daily.db")
    sv = pd.read_sql("SELECT date, AVG(vol_rto) v FROM short_volume GROUP BY date", k).set_index("date").v
    S["sv"] = sv.rolling(5, min_periods=3).mean()
    con = sqlite3.connect(BASE / "data" / "investor.db")
    ff = pd.read_sql("SELECT date, SUM(frgn) f, SUM(ABS(frgn)+ABS(indiv)) a FROM flow11 GROUP BY date", con).set_index("date")
    S["ff5"] = ff.f.rolling(5).sum() / ff.a.rolling(5).sum() * 100; S["ff20"] = ff.f.rolling(20).sum() / ff.a.rolling(20).sum() * 100
    fx = fdr.DataReader("USD/KRW", "2003-06-01"); fx.index = fx.index.strftime("%Y%m%d")
    S["fx20"] = (fx.Close / fx.Close.shift(20) - 1).reindex(S.index, method="ffill") * 100
    def us(sym):                                                           # 한국 날짜 t 에는 미국 날짜 < t 인 마지막 값
        X = fdr.DataReader(sym, "2003-06-01"); X.index = X.index.strftime("%Y%m%d"); X = X.Close
        pos = np.searchsorted(X.index.to_numpy(), S.index.to_numpy(), side="left") - 1
        return pd.Series(np.where(pos >= 0, X.to_numpy()[np.clip(pos, 0, None)], np.nan), index=S.index)
    vix, sp = us("VIX"), us("US500")
    S["vix"] = vix; S["vixc"] = (vix / vix.shift(5) - 1) * 100
    S["sp1"] = sp.pct_change() * 100; S["sp1"] = S.sp1.where(sp.diff() != 0)          # 미장 쉰 날은 비움
    S["sp20"] = (sp / sp.shift(20) - 1) * 100
    dt = pd.to_datetime(S.index)
    S["dow"] = pd.Series(dt.dayofweek.astype(float), index=S.index).shift(-1)            # 내일 요일
    ym = dt.to_period("M"); pos_in = pd.Series(range(len(S)), index=S.index).groupby(ym).rank(method="first")
    cnt = pd.Series(1, index=S.index).groupby(ym).transform("sum")
    nxt = pd.Series(pos_in.to_numpy(), index=S.index)
    S["tom"] = pd.Series((((cnt - nxt) <= 1) | (nxt <= 2)).astype(float).to_numpy(), index=S.index).shift(-1)   # 내일이 월말 2일·월초 3일
    S["win"] = pd.Series(dt.month.isin([11, 12, 1, 2, 3, 4]).astype(float), index=S.index).shift(-1)   # 내일이 11~4월
    S.to_pickle(CACHE); return S


def perf(pos, ret, lo, hi):
    m = (ret.index >= lo) & (ret.index <= hi)
    p = pos[m]; r = ret[m].fillna(0) / 100
    sw = p.diff().abs().fillna(0)
    d = p * r - sw * SWC / 100
    yrs = m.sum() / 250
    cagr = (1 + d).prod() ** (1 / yrs) - 1
    sh = d.mean() / (d.std() + 1e-12) * np.sqrt(250)
    eq = (1 + d).cumprod(); dd = (eq / eq.cummax() - 1).min()
    return dict(cagr=cagr * 100, sh=sh, dd=dd * 100, expo=p.mean() * 100, sw=sw.sum() / yrs)


def main():
    S = signals()
    ret = S.ret.shift(-1)                                                   # 오늘 정하면 내일 등락을 받는다
    feats = ["vol20", "vol5_60", "br20", "br50", "ad10", "nh20", "sv", "fx20", "vix", "vixc", "sp1", "sp20", "ff5", "ff20"]
    cats = {"dow": [0, 1, 2, 3, 4], "tom": [1], "win": [1]}
    L = S[(S.index >= LEARN[0]) & (S.index <= LEARN[1])]
    conds = []
    for f in feats:
        for q in (0.3, 0.5, 0.7):
            th = L[f].quantile(q)
            conds.append(("%s ≤ %.3g(찾기 %d%%)" % (f, th, q * 100), (S[f] <= th) & S[f].notna(), f))
            conds.append(("%s ≥ %.3g(찾기 %d%%)" % (f, th, q * 100), (S[f] >= th) & S[f].notna(), f))
    for f, vals in cats.items():
        for v in vals:
            conds.append(("%s = %d" % (f, v), S[f] == v, f)); conds.append(("%s ≠ %d" % (f, v), S[f] != v, f))
    allin = pd.Series(1.0, index=S.index)
    bh = {k: perf(allin, ret, *rng) for k, rng in (("L", LEARN), ("V", VALID), ("R", RUN))}
    bh18 = perf(allin, ret, "20180101", LEARN[1])
    P("그냥 들고 있기: 찾기 연 %+.1f%% 샤프 %.2f 낙폭 %.0f%% · 확인 연 %+.1f%% 샤프 %.2f · (2018~22 샤프 %.2f)" % (
        bh["L"]["cagr"], bh["L"]["sh"], bh["L"]["dd"], bh["V"]["cagr"], bh["V"]["sh"], bh18["sh"]))
    cands = [[c] for c in conds] + [[a, b] for a, b in itertools.combinations(conds, 2) if a[2] != b[2]]
    rows = []
    for cs in cands:
        pos = cs[0][1].copy()
        for c in cs[1:]: pos &= c[1]
        pos = pos.astype(float)
        uses_ff = any(c[2] in ("ff5", "ff20") for c in cs)
        lo = "20180101" if uses_ff else LEARN[0]
        rl = perf(pos, ret, lo, LEARN[1]); base = bh18["sh"] if uses_ff else bh["L"]["sh"]
        if not (rl["sh"] - base >= 0.15 and rl["expo"] >= 30 and rl["sw"] <= 30): continue
        rv = perf(pos, ret, *VALID)
        ok = rv["sh"] > bh["V"]["sh"] and rv["cagr"] > 0
        rows.append((cs, rl, rv, ok, min(rl["sh"] - base, rv["sh"] - bh["V"]["sh"]), pos))
    P("시험 %d칸 · 찾기 통과 %d · 확인 통과 %d" % (len(cands), len(rows), sum(r[3] for r in rows)))
    P("\n| 조건 | 찾기 연·샤프·낙폭·들고 있는 날 | 확인 연·샤프·낙폭 | 통과 |"); P("|---|---|---|---|")
    for cs, rl, rv, ok, sc, _ in sorted(rows, key=lambda x: -x[4])[:15]:
        P("| %s | %+.1f%% · %.2f · %.0f%% · %.0f%% | %+.1f%% · %.2f · %.0f%% | %s |" % (" & ".join(c[0] for c in cs), rl["cagr"], rl["sh"], rl["dd"], rl["expo"],
          rv["cagr"], rv["sh"], rv["dd"], "O" if ok else ""))
    ok_rows = sorted([r for r in rows if r[3]], key=lambda x: -x[4])
    if not ok_rows:
        P("\n확인 통과 0 — 현금"); (ROOT / "y4_timing.out").write_text("\n".join(OUT), encoding="utf-8"); return
    cs, rl, rv, ok, sc, pos = ok_rows[0]
    P("\n**뽑힘: %s**" % " & ".join(c[0] for c in cs))
    rr = perf(pos, ret, *RUN)
    m = (S.index >= RUN[0]) & (S.index <= RUN[1])
    d = pos[m] * ret[m].fillna(0) / 100 - pos[m].diff().abs().fillna(0) * SWC / 100
    eq = 1e8 * (1 + d).cumprod(); bheq = 1e8 * (1 + ret[m].fillna(0) / 100).cumprod()
    P("\n## 굴리기 %s~%s (1억)\n" % RUN)
    P("| 판 | 1년 뒤 | 수익 | 가장 크게 빠진 폭 | 들고 있던 날 |"); P("|---|---|---|---|---|")
    P("| 새로 찾은 타이밍 | %s원 | %+.1f%% | %.1f%% | %.0f%% |" % (f"{eq.iloc[-1]:,.0f}", (eq.iloc[-1] / 1e8 - 1) * 100, rr["dd"], rr["expo"]))
    P("| 참고: 코스피 그냥 들고 있기 | %s원 | %+.1f%% | %.1f%% | 100%% |" % (f"{bheq.iloc[-1]:,.0f}", (bheq.iloc[-1] / 1e8 - 1) * 100, bh["R"]["dd"]))
    M = pd.DataFrame({"timing": eq, "bh": bheq}); M.index = pd.to_datetime(M.index)
    P("\n월말(만원): " + " · ".join("%s %s/%s" % (i.strftime("%y-%m"), f"{a / 1e4:,.0f}", f"{b / 1e4:,.0f}") for i, (a, b) in M.resample("ME").last().iterrows()))
    M.to_pickle(BASE / "data" / "y4_paths.pkl")
    (ROOT / "y4_timing.out").write_text("\n".join(OUT), encoding="utf-8")


if __name__ == "__main__":
    main()
