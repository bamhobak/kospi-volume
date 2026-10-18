# -*- coding: utf-8 -*-
"""제안 12개 중 지금 잴 수 있는 10개 (2026-10-18) — H0354~H0363.
 1 연기금 매집      — flow11 pens 60일 누적 ÷ 시총 상위 · 고점 -15% 안 · 외인+기관(연기금 뺀) 60일 조용 → 다음날 시가 60일
 2 신용 손바뀜      — KIS 융자잔고 20일 -10%↓ & 20일 수익 > 0 & 60일선 위(처음 켜진 날) → 20·60일
 3 소각·밸류업 공시 — DART '주식소각결정'·'기업가치제고계획' → 다음날 시가 20·60일 · 해마다
 5 [조용한 신고가] 이벤트화 — P1 조건 & 고점 -3/-5% 안에 '처음' 진입(지난 20일은 밖) · 규칙 단위 + 계좌(P1 바꿔 끼움)
 6 식은 채로 진입    — P1·P7 신호를 3일 거래량 ÷ 20일 평균 ≤ 1 로 쪼갬 · 규칙 단위 + 계좌(식은 것만)
 7 미장 따라잡기 스윙 — 전이표 짝(56개 미장 ETF·대형주)이 52주 신고가 '처음' → 다음 국장 거래일 종가, 국장 종목이 고점 -15%↓면 매수 5·20·40일
 9·10 상승 전환 초기 — 코스피 1년 고점 -20%↓ 뒤 60일선 첫 회복일 → 하락 구간 낙폭 10분위별 30·60일(가장 덜 빠진 10% = 10번)
11 지수 덮개(상승장)  — 계좌 놀고 있는 현금의 w(50·100%)를 코스피200 에, 전날 지수 > 60일선일 때만(매일 판정)
12 초대형주 상대강도  — 매달 첫 거래일 코스피 시총 상위 20 중 60일 수익 상위 3·5 동일가중 vs 코스피200
초과 = 같은 날 유니버스(거래대금 상위 40%) 같은 보유 평균 대비 · 비용 0.43(스윙) · 구간 옛날 ~15 · 학습 16~22 · 검증 23~.
    python research/ideas12_1018.py
"""
import sys, os, sqlite3
from pathlib import Path
BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "research" / "factory")); sys.path.insert(0, str(BASE / "research"))
import numpy as np, pandas as pd
import FinanceDataReader as fdr
import ideas5_1018 as I5

P, cell, table, per, PER = I5.P, I5.cell, I5.table, I5.per, I5.PER
OUT = I5.OUT


def dedup(X, K, gap=20):
    X = X.sort_values(["ticker", "date"]); keep = []; last = {}
    for i, tk in zip(X.index, X.ticker.values):
        dn = K.at[i, "di"]
        if tk in last and dn - last[tk] < gap: continue
        last[tk] = dn; keep.append(i)
    return X.loc[keep]


def with_basket(nm, X, cols):
    return [(nm, X), (nm + " [날 바구니]", X.groupby("date")[cols].mean().reset_index())]


def part1(K):
    P("\n## 1 연기금 매집")
    c = sqlite3.connect(f"file:{BASE / 'data' / 'investor.db'}?mode=ro", uri=True)
    F = pd.read_sql("SELECT ticker, date, pens, frgn, fin, ins, tru, pef, bank, ofin FROM flow11", c).sort_values(["ticker", "date"])
    F["inst_x"] = F[["fin", "ins", "tru", "pef", "bank", "ofin"]].sum(axis=1)
    g = F.groupby("ticker")
    F["p60"] = g.pens.transform(lambda s: s.rolling(60, min_periods=40).sum())
    F["o60"] = (g.frgn.transform(lambda s: s.rolling(60, min_periods=40).sum()) + g.inst_x.transform(lambda s: s.rolling(60, min_periods=40).sum()))
    Z = K[K.date >= "20180101"].merge(F[["ticker", "date", "p60", "o60"]], on=["ticker", "date"], how="left")
    Z["mc"] = np.where(Z.marcap > 1e9, Z.marcap, Z.marcap * 1e8)
    Z["pr"] = Z.p60 / Z.mc; Z["orr"] = (Z.o60 / Z.mc).abs()
    Z["q_pr"] = Z.groupby("date").pr.rank(pct=True); Z["q_or"] = Z.groupby("date").orr.rank(pct=True)
    Z = Z.set_index(Z.index)
    rows = []
    for nm, m in (("연기금 60일 ÷ 시총 상위 5% · 고점 -15% 안 · 외인+기관 조용(하위 50%)", (Z.q_pr >= 0.95) & (Z.fromhi >= -15) & (Z.q_or <= 0.5)),
                  ("연기금 상위 5% · 고점 -15% 안(조용 조건 없음)", (Z.q_pr >= 0.95) & (Z.fromhi >= -15)),
                  ("연기금 상위 1% · 고점 -15% 안 · 조용", (Z.q_pr >= 0.99) & (Z.fromhi >= -15) & (Z.q_or <= 0.5))):
        X = Z.loc[m & Z.uni, ["date", "ticker", "x20", "x60", "di"]]
        X = X.sort_values(["ticker", "date"]); keep = []; last = {}
        for i, tk, dn in zip(X.index, X.ticker.values, X.di.values):
            if tk in last and dn - last[tk] < 60: continue
            last[tk] = dn; keep.append(i)
        rows += with_basket(nm, X.loc[keep], ["x20", "x60"])
    table("다음날 시가 매수 · 같은 날 유니버스 대비 초과(같은 종목 60일 안 재신호 빼고)", rows, ["x60", "x20"], ["60일", "20일"])


def part2(K):
    P("\n## 2 신용 손바뀜")
    c = sqlite3.connect(f"file:{BASE / 'data' / 'kis' / 'market.db'}?mode=ro", uri=True)
    C = pd.read_sql("SELECT date, ticker, loan_rmnd FROM credit", c).sort_values(["ticker", "date"])
    C["cr20"] = (C.loan_rmnd / C.groupby("ticker").loan_rmnd.shift(20) - 1) * 100
    Z = K.merge(C[["ticker", "date", "cr20"]], on=["ticker", "date"], how="left")
    g = Z.groupby("ticker", sort=False)
    Z["r20"] = (Z.close / g.close.shift(20) - 1) * 100
    Z["ma60"] = g.close.transform(lambda s: s.rolling(60).mean())
    on = (Z.cr20 <= -10) & (Z.r20 > 0) & (Z.close > Z.ma60) & (Z.loan_ok if "loan_ok" in Z else True)
    on = on.fillna(False).astype(bool)
    first = on & ~on.groupby(Z.ticker).shift(1, fill_value=False)
    ctrl = ((Z.cr20 >= 10) & (Z.r20 > 0) & (Z.close > Z.ma60)).fillna(False).astype(bool)
    rows = []
    for nm, m in (("신용 20일 -10%↓ & 20일 수익>0 & 60일선 위(처음 켜진 날)", first), ("신용 20일 -20%↓ & 같은 조건", first & (Z.cr20 <= -20)),
                  ("대조: 신용 20일 +10%↑ & 20일 수익>0 & 60일선 위", ctrl & ~ctrl.groupby(Z.ticker).shift(1, fill_value=False))):
        X = Z.loc[m & Z.uni, ["date", "ticker", "x20", "x60"]]
        rows += with_basket(nm, X, ["x20", "x60"])
    table("다음날 시가 매수 · 초과(비용 뒤)", rows, ["x20", "x60"], ["20일", "60일"])
    return Z.loc[first & Z.uni, ["date", "ticker"]]


def part3(K):
    P("\n## 3 자사주 소각·밸류업 공시")
    con = sqlite3.connect(BASE / "data" / "dart" / "disclosures.db")
    D = pd.read_sql("SELECT stock_code AS ticker, rcept_dt AS date, report_nm FROM disclosure WHERE length(stock_code)=6 AND "
                    "(report_nm LIKE '%주식소각결정%' OR replace(report_nm,' ','') LIKE '%기업가치제고계획%') AND report_nm NOT LIKE '%정정%'", con)
    D["kind"] = np.where(D.report_nm.str.contains("소각"), "소각", "밸류업")
    TI = K.groupby("ticker").indices; DT = K.date.to_numpy()
    recs = []
    for r in D.drop_duplicates(["ticker", "date", "kind"]).itertuples():
        ii = TI.get(r.ticker)
        if ii is None: continue
        j = np.searchsorted(DT[ii], r.date)
        if j >= len(ii): continue
        i = ii[j]
        recs.append(dict(date=DT[i], kind=r.kind, x20=K.x20.iat[i], x60=K.x60.iat[i], uni=bool(K.uni.iat[i])))
    R = pd.DataFrame(recs)
    rows = []
    for k in ("소각", "밸류업"):
        Z = R[R.kind == k]
        rows += [("%s 공시 전체" % k, Z), ("  유니버스(거래대금 상위 40%%)만", Z[Z.uni])]
    table("공시 다음날 시가 매수 · 초과(비용 뒤)", rows, ["x20", "x60"], ["20일", "60일"])
    for k in ("소각", "밸류업"):
        Z = R[R.kind == k]; Z = Z.assign(y=Z.date.str[:4])
        P("%s 해마다 20일 초과: %s" % (k, " ".join("%s:%+.1f(%d)" % (y[2:], q.x20.mean(), len(q)) for y, q in Z.groupby("y"))))


def part5_6(ns):
    P("\n## 5 [조용한 신고가] 이벤트화 · 6 식은 채로 진입")
    KP = ns["KP"]; RULES = ns["RULES"]
    g = KP.groupby("ticker", sort=False)
    KP["v3r"] = g.volume.transform(lambda s: s.rolling(3).mean()) / g.volume.transform(lambda s: s.shift(3).rolling(20, min_periods=15).mean())
    cond = RULES["P1"][5].fillna(False)
    hold = RULES["P1"][1]
    ex = g.close.shift(-hold)
    ret = (ex / KP.buy - 1) * 100 - KP.cost
    out = {}
    for x in (3, 5):
        inz = (KP.fromhi >= -x).astype(float)
        prev_out = inz.groupby(KP.ticker).transform(lambda s: s.shift(1).rolling(20, min_periods=20).max()).fillna(1) == 0
        inz = inz.astype(bool)
        out[x] = cond & inz & prev_out
    S = ns["S"].copy(); S["ret"] = (S.exit / S.buy - 1) * 100 - S.cost
    rows = [("[조용한 신고가] 지금", S[S.rid == "P1"][["date", "ret"]])]
    for x in (3, 5):
        rows.append(("이벤트: 고점 -%d%% 안 처음 진입 & P1 조건" % x, pd.DataFrame({"date": KP.date[out[x]], "ret": ret[out[x]]}).dropna()))
    table("규칙 단위 40일 보유(비용 뒤, 돈 무한)", rows, ["ret"], ["40일"])
    # 6 식은 채로
    S = S.merge(KP[["ticker", "date", "v3r"]], on=["ticker", "date"], how="left")
    rows = []
    for rid in ("P1", "P7"):
        Z = S[S.rid == rid]
        rows += [("[%s] 3일 거래량 ≤ 20일 평균(식음)" % rid, Z[Z.v3r <= 1][["date", "ret"]]), ("[%s] > 20일 평균" % rid, Z[Z.v3r > 1][["date", "ret"]])]
    table("6 식은 채로 — 규칙 단위(비용 뒤)", rows, ["ret"], ["보유 끝"])
    # 계좌
    sim = ns["simulate"]; S0 = ns["S"]
    def st(C):
        yrs = len(C) / 252; return "%.2f배 · 연 %.1f%% · 낙폭 %.1f%%" % (C.nav.iloc[-1], (C.nav.iloc[-1] ** (1 / yrs) - 1) * 100, ((C.nav / C.nav.cummax()) - 1).min() * 100)
    res = [("지금 그대로", sim(1.0, 1.0, quiet=True)[0])]
    v3 = S0.merge(KP[["ticker", "date", "v3r"]], on=["ticker", "date"], how="left").v3r.values
    for nm, keep in (("P1·P7 식은 것만", ~(S0.rid.isin(["P1", "P7"]).values & ~(v3 <= 1))), ("P7 만 식은 것만", ~((S0.rid == "P7").values & ~(v3 <= 1)))):
        ns["S"] = S0[keep]; res.append((nm, sim(1.0, 1.0, quiet=True)[0]))
    # P1 바꿔 끼우기(이벤트 -5%)
    X = KP[out[5]].copy()
    X["rid"] = "P1"; X["hold"] = hold; X["stop"] = np.nan; X["trail"] = np.nan; X["pct"] = RULES["P1"][3]; X["mx"] = RULES["P1"][4]
    X["exit"] = ex.reindex(X.index); X["low"] = np.nan
    X = X[["date", "ticker", "name", "mk", "rid", "hold", "stop", "trail", "pct", "mx", "buy", "exit", "low", "cost", "amt20"]].dropna(subset=["buy", "exit", "cost"])
    X["di"] = X.date.map(ns["DI"])
    Snew = pd.concat([S0[S0.rid != "P1"], X]).sort_values(["di", "amt20"], ascending=[True, False], kind="stable").reset_index(drop=True)
    ns["S"] = Snew; res.append(("P1 → 이벤트판(-5%)", sim(1.0, 1.0, quiet=True)[0]))
    ns["S"] = S0
    P("\n계좌(portfolio.py 9규칙): " + " · ".join("%s %s" % (n, st(c)) for n, c in res))


def part7(K):
    import lab, transfer as TR
    P("\n## 7 미장 따라잡기 스윙 — 전이표 짝이 52주 신고가 처음 → 국장 종목 고점 -15%↓")
    U = lab.hist()[["ticker", "date", "gap"]]
    NR = TR.night_returns(U.date.unique())
    A = pd.read_parquet(TR.UD); Pv = A.pivot(index="date", columns="sym", values="close").sort_index()
    nh = (Pv >= Pv.rolling(250, min_periods=200).max())
    first = nh & ~(nh.shift(1).rolling(20, min_periods=1).max().fillna(0).astype(bool))
    kd = np.array(sorted(K.date.unique()))
    recs = []
    TI = K.groupby("ticker").indices; DT = K.date.to_numpy()
    for Y in range(2016, 2027):
        fit = TR.fit_year(U, Y, NR)
        if not fit: continue
        for t, (sym, b, cr) in fit.items():
            if sym not in first.columns: continue
            evs = first.index[first[sym] & (first.index >= "%d0101" % Y) & (first.index <= "%d1231" % Y)]
            ii = TI.get(t)
            if ii is None: continue
            for ud in evs:
                j = np.searchsorted(DT[ii], ud, side="right")            # 뉴욕 날짜 다음 국장 거래일 종가에 매수(c 계열)
                if j >= len(ii): continue
                i = ii[j]
                recs.append(dict(date=DT[i], ticker=t, sym=sym, cr=cr, fromhi=K.fromhi.iat[i], x5=K.xc5.iat[i], x20=K.xc20.iat[i], x40=K.xc40.iat[i], uni=bool(K.uni.iat[i])))
    R = pd.DataFrame(recs)
    rows = [("짝 신고가 처음 · 국장 종목 고점 -15%↓", R[(R.fromhi <= -15) & R.uni]), ("짝 신고가 처음 · 국장 종목 고점 -15% 안(이미 따라감)", R[(R.fromhi > -15) & R.uni]),
            ("짝 신고가 처음 · 고점 -15%↓ · 상관 0.3↑", R[(R.fromhi <= -15) & R.uni & (R.cr >= 0.3)])]
    rows += [(nm + " [날 바구니]", Z.groupby("date")[["x5", "x20", "x40"]].mean().reset_index()) for nm, Z in rows[:1]]
    table("다음 국장 거래일 종가 매수 · 초과(비용 뒤)", rows, ["x20", "x5", "x40"], ["20일", "5일", "40일"])
    if len(R): P("짝 쏠림(상위 5): " + " ".join("%s %d" % (s, n) for s, n in R[(R.fromhi <= -15) & R.uni].sym.value_counts().head(5).items()))


def part9_10(K):
    P("\n## 9·10 상승 전환 초기 — 코스피 1년 고점 -20%↓ 뒤 60일선 첫 회복")
    IX = I5.IX.copy(); IX["ma60"] = IX.Close.rolling(60).mean()
    ev = []; armed = False; peak_i = None
    for k in range(250, len(IX)):
        if IX.dd.iat[k] <= -20 and not armed:
            armed = True
        if armed and IX.Close.iat[k] > IX.ma60.iat[k] and IX.Close.iat[k - 1] <= IX.ma60.iat[k - 1]:
            w = IX.iloc[max(0, k - 250):k + 1]
            pk = w.Close.idxmax(); tr = IX.loc[pk:IX.index[k]].Close.idxmin()
            ev.append((IX.date.iat[k], pk.strftime("%Y%m%d"), tr.strftime("%Y%m%d"))); armed = False
    P("전환일 %d개: %s" % (len(ev), " ".join(e[0] for e in ev)))
    g = K.groupby("ticker", sort=False)
    last = g.close.transform("last")
    for h in (30, 60):
        f = (g.close.shift(-h).fillna(last) / g.open.shift(-1) - 1) * 100
        K["y%d" % h] = f.clip(-95, 300)
    rows = []
    for d, pk, tr in ev:
        Ksub = K[(K.date >= pk) & (K.date <= d)]
        pc = Ksub[Ksub.date == pk].set_index("ticker").close
        mn = Ksub[(Ksub.date >= pk) & (Ksub.date <= tr)].groupby("ticker").close.min()
        T = K[(K.date == d) & K.uni].set_index("ticker")
        T = T.join((mn / pc - 1).rename("fall") * 100, how="inner").dropna(subset=["fall", "y30", "y60"])
        if len(T) < 50: continue
        T["dec"] = pd.qcut(T.fall.rank(method="first"), 10, labels=False)     # 0 = 가장 많이 빠짐 · 9 = 가장 덜 빠짐
        for h in (30, 60): T["x%d" % h] = T["y%d" % h] - T["y%d" % h].mean()
        rows.append((d, T.groupby("dec")[["x30", "x60"]].mean(), len(T)))
    P("\n| 전환일 | 종목 | 가장 많이 빠진 10% 30일·60일 | 중간(5분위) | 가장 덜 빠진 10%(버틴 종목) 30일·60일 |"); P("|---|---|---|---|---|")
    for d, G, n in rows:
        P("| %s | %d | %+.1f · %+.1f | %+.1f · %+.1f | %+.1f · %+.1f |" % (d, n, G.loc[0, "x30"], G.loc[0, "x60"], G.loc[5, "x30"], G.loc[5, "x60"], G.loc[9, "x30"], G.loc[9, "x60"]))
    if rows:
        M = sum(G for _, G, _ in rows) / len(rows)
        P("| 평균 | | %+.1f · %+.1f | %+.1f · %+.1f | %+.1f · %+.1f |" % (M.loc[0, "x30"], M.loc[0, "x60"], M.loc[5, "x30"], M.loc[5, "x60"], M.loc[9, "x30"], M.loc[9, "x60"]))
        P("가장 많이 빠진 쪽이 이긴 전환 %d/%d (60일 기준) · 2020 빼고 평균: 많이 빠진 %+.1f · 버틴 %+.1f" % (
            sum(G.loc[0, "x60"] > G.loc[9, "x60"] for _, G, _ in rows), len(rows),
            np.mean([G.loc[0, "x60"] for d, G, _ in rows if not d.startswith("2020")]), np.mean([G.loc[9, "x60"] for d, G, _ in rows if not d.startswith("2020")])))


def part11_12(ns, K):
    P("\n## 11 지수 덮개(상승장) — 계좌 현금의 일부를 코스피200 에, 전날 지수 > 60일선일 때만")
    C = ns["simulate"](1.0, 1.0, quiet=True)[0]
    X = fdr.DataReader("KS200", "2004-01-01"); X = X[X.Close > 0]; X["date"] = X.index.strftime("%Y%m%d")
    X["r"] = X.Close.pct_change(); X["on"] = (X.Close > X.Close.rolling(60).mean()).shift(1).fillna(False)
    C = C.merge(X[["date", "r", "on"]], on="date", how="left").fillna({"r": 0, "on": False})
    C["ra"] = C.nav.pct_change().fillna(0); C["cash"] = (1 - C.expo.shift(1).fillna(0)).clip(0, 1)
    def st(nav, d):
        yrs = len(nav) / 252; s = pd.Series(nav.values, index=d.values)
        yr = s.groupby(s.index.str[:4]).agg(lambda v: v.iloc[-1] / v.iloc[0] - 1) * 100
        return nav.iloc[-1], (nav.iloc[-1] ** (1 / yrs) - 1) * 100, ((nav / nav.cummax()) - 1).min() * 100, yr
    res = {"지금": st(C.nav / C.nav.iloc[0], C.date)}
    for w in (0.5, 1.0):
        r = C.ra + C.cash * w * C.r * C.on - (C.on != C.on.shift(1)).astype(float) * C.cash * w * 0.001
        res["덮개 %d%%" % (w * 100)] = st((1 + r).cumprod(), C.date)
    P("| 판 | 최종 | 연 | 최대 낙폭 |"); P("|---|---|---|---|")
    for k, (m, cg, dd, _) in res.items(): P("| %s | %.2f배 | %+.1f%% | %.1f%% |" % (k, m, cg, dd))
    yrs = sorted(res["지금"][3].index)
    P("\n해마다(지금 / 덮개 50% / 덮개 100%): " + " ".join("%s %+.0f/%+.0f/%+.0f" % (y[2:], res["지금"][3][y], res["덮개 50%"][3][y], res["덮개 100%"][3][y]) for y in yrs))

    P("\n## 12 초대형주 상대강도 — 매달 첫 거래일 코스피 시총 상위 20 중 60일 수익 상위 N 동일가중")
    Kp = K[K.mk == "KOSPI"].copy()
    Kp["cap"] = np.where(Kp.marcap > 1e9, Kp.marcap / 1e8, Kp.marcap)
    g = Kp.groupby("ticker", sort=False); Kp["r60"] = (Kp.close / g.close.shift(60) - 1) * 100
    days = np.array(sorted(Kp.date.unique())); md = pd.Series(days).groupby(pd.Series(days).str[:6]).min().values
    px = Kp.pivot(index="date", columns="ticker", values="close")
    out = {3: [], 5: []}
    for a, b in zip(md[:-1], md[1:]):
        S = Kp[Kp.date == a].nlargest(20, "cap")
        for n in (3, 5):
            pick = S.nlargest(n, "r60").ticker
            r = (px.loc[b, pick] / px.loc[a, pick] - 1).mean() * 100 - 0.23 * 0.6
            out[n].append((a, r))
    X2 = X.set_index("date").Close
    rows = []
    for n in (3, 5):
        R = pd.DataFrame(out[n], columns=["d", "r"])
        R["ix"] = [(X2.asof(b) / X2.asof(a) - 1) * 100 if a in X2.index or True else np.nan for a, b in zip(md[:-1], md[1:])][:len(R)]
        rows.append((n, R))
    P("| 판 | 연복리 · 낙폭(전체) | 2016~22 연 | 2023~ 연 | 2025~26 빼고 연 | 코스피200 같은 기간(전체·2016~22·2023~·붐 빼고) |"); P("|---|---|---|---|---|---|")
    for n, R in rows:
        def cg(s): v = (1 + s / 100).prod(); return (v ** (12 / max(len(s), 1)) - 1) * 100
        eq = (1 + R.r / 100).cumprod(); dd = ((eq / eq.cummax()) - 1).min() * 100
        m16 = (R.d >= "201601") & (R.d < "202301"); m23 = R.d >= "202301"; nob = R.d < "202501"
        P("| 상위 %d | %+.1f%% · %.0f%% | %+.1f%% | %+.1f%% | %+.1f%% | %+.1f / %+.1f / %+.1f / %+.1f |" % (
            n, cg(R.r), dd, cg(R.r[m16]), cg(R.r[m23]), cg(R.r[nob]), cg(R.ix), cg(R.ix[m16]), cg(R.ix[m23]), cg(R.ix[nob])))


def main():
    ns = I5.portfolio_ns()
    import run_spec as RS
    K, uni, _ = RS.load_market("KR")
    K["uni"] = uni.values
    K = K.sort_values(["ticker", "date"]).reset_index(drop=True)
    g = K.groupby("ticker", sort=False)
    K["di"] = g.cumcount()
    last = g.close.transform("last")
    for h in (20, 60):
        f = ((g.close.shift(-h).fillna(last) / g.open.shift(-1) - 1) * 100).clip(-95, 300)
        K["x%d" % h] = f - f.where(K.uni).groupby(K.date).transform("mean") - 0.43
    for h in (5, 20, 40):
        f = ((g.close.shift(-h).fillna(last) / K.close - 1) * 100).clip(-95, 300)
        K["xc%d" % h] = f - f.where(K.uni).groupby(K.date).transform("mean") - 0.43
    for fn, args in ((part1, (K,)), (part2, (K,)), (part3, (K,)), (part5_6, (ns,)), (part7, (K,)), (part9_10, (K,)), (part11_12, (ns, K))):
        try: fn(*args)
        except Exception as ex:
            import traceback; P("\n⚠ %s 실패: %r" % (fn.__name__, ex)); traceback.print_exc()
    (BASE / "research" / "cache" / "ideas12_1018.out").write_text("\n".join(OUT), encoding="utf-8")


if __name__ == "__main__":
    main()
