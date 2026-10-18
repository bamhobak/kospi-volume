# -*- coding: utf-8 -*-
"""제안 5개 실측 (2026-10-18 사용자 "이것들 실측할 수 있는 거 해볼래") — H0349~H0353.

A 하락장 신고가 — 코스피가 1년 고점 대비 -20/-25%↓인데 본인은 52주 고점 근처(fromhi ≥ -5/-10) · 거래량 침체.
  ① [조용한 신고가](P1) 신호를 국면(코스피 고점 대비)별로 쪼갬 ② 넓은 판(kr_scan 유니버스) 20·60일 초과.
B [갭 하락 조용주](T1) 하락장 깊이별 — 코스피 1년 고점 대비 0/-10/-20/-30/-40% 구간별 건당·승률 + 날 바구니·하루 몰림.
C 내부자 + 자사주 동시 — 20일 안 내부자 순매수(ins20>0) & 자사주 취득·신탁 공시 → 다음날 시가 20·60일, 하락장(60일선 아래)만도.
  대조: 자사주만·내부자만. [자사주 낙폭](P5)·[자사주 신탁 급락](P8) ±5일 겹침.
D 미장 폭락 다음 날 국장 데이 — 나스닥 전날 -2/-3%↓ · 갭 하락 · 전이표 잔차 하위(예상보다 더 빠짐) · 작은 종목 → 시가→종가. T1 겹침.
E 신용 급증 후 급감 경고등 — KIS 융자잔고율 drop(60일평균/250일평균) > 1.5 & rise(5일/60일) < 0.3 이 신호일에 켜진 규칙 신호를 빼면?
  규칙별 건당(돈 무한) + 계좌 시뮬(portfolio.py simulate) 둘 다.
    python research/ideas5_1018.py
"""
import sys, os, glob, sqlite3
from pathlib import Path
BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "research" / "factory")); sys.path.insert(0, str(BASE / "research"))
import numpy as np, pandas as pd
import FinanceDataReader as fdr

OUT = []
def P(s=""):
    OUT.append(s); sys.__stdout__.write(s + "\n"); sys.__stdout__.flush()
PER = [("옛날", "20050101", "20151231"), ("학습", "20160101", "20221231"), ("검증", "20230101", "20991231")]
per = lambda d: np.where(d <= "20151231", "옛날", np.where(d <= "20221231", "학습", "검증"))


def cell(x, n=8):
    x = pd.Series(x).dropna()
    if len(x) < n: return "%d건" % len(x)
    t = x.mean() / (x.std(ddof=1) / np.sqrt(len(x))) if x.std() > 0 else 0
    return "%d · %+.2f · %.0f%% · t%.1f" % (len(x), x.mean(), (x > 0).mean() * 100, t)


def table(title, rows, cols, head):
    P("\n### " + title)
    P("| 판 | " + " | ".join("%s 옛날 | 학습 | 검증" % h for h in head) + " |"); P("|---" * (1 + 3 * len(head)) + "|")
    for nm, Z in rows:
        Z = Z.assign(p=per(Z.date.astype(str).values)); cs = []
        for c in cols:
            for p, _, _ in PER: cs.append(cell(Z.loc[Z.p == p, c]))
        P("| %s | %s |" % (nm, " | ".join(cs)))


# ── 코스피 국면 ──
IX = fdr.DataReader("KS11", "2003-01-01"); IX = IX[IX.Close > 0]
IX["date"] = IX.index.strftime("%Y%m%d")
IX["dd"] = (IX.Close / IX.Close.rolling(250, min_periods=60).max() - 1) * 100
IX["below60"] = IX.Close < IX.Close.rolling(60).mean()
DD = dict(zip(IX.date, IX.dd)); B60 = dict(zip(IX.date, IX.below60))


def portfolio_ns():
    src = (BASE / "portfolio.py").read_text(encoding="utf-8").split("# @@ANALYSIS")[0]
    src = src.replace('sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")', "")
    cwd = os.getcwd(); os.chdir(BASE)
    ns = {"__file__": str(BASE / "portfolio.py"), "__name__": "pf"}
    exec(compile(src, "portfolio.py", "exec"), ns)
    os.chdir(cwd)
    return ns


def part_A(S, K):
    P("\n## A 하락장 신고가")
    S = S.copy(); S["dd"] = S.date.map(DD)
    Z = S[S.rid == "P1"]
    rows = [("[조용한 신고가] 전체", Z), ("  코스피 고점 -10%↓", Z[Z.dd <= -10]), ("  -20%↓", Z[Z.dd <= -20]), ("  -25%↓", Z[Z.dd <= -25]), ("  고점 -10% 안(평소)", Z[Z.dd > -10])]
    table("① [조용한 신고가](P1) 신호 국면별 — 보유 40일 수익(비용 뒤, 돈 무한)", rows, ["ret"], ["40일"])
    # ② 넓은 판
    K = K.copy(); K["dd"] = K.date.map(DD)
    rows = []
    for nm, m in (("하락장(-20%↓) · 52주 고점 -5% 안 · 거래량 침체(5일/20일 ≤ 0.8)", (K.dd <= -20) & (K.fromhi >= -5) & (K.vr <= 0.8)),
                  ("하락장(-25%↓) · 고점 -10% 안 · 거래량 침체", (K.dd <= -25) & (K.fromhi >= -10) & (K.vr <= 0.8)),
                  ("하락장(-20%↓) · 고점 -5% 안 · 거래량 무관", (K.dd <= -20) & (K.fromhi >= -5)),
                  ("대조: 평소(-10% 안) · 고점 -5% 안 · 거래량 침체", (K.dd > -10) & (K.fromhi >= -5) & (K.vr <= 0.8))):
        X = K.loc[m & K.uni, ["date", "ticker", "x20", "x60"]]
        # 같은 종목 20일 안 재신호 빼기
        X = X.sort_values(["ticker", "date"]); X["di"] = X.groupby("ticker").cumcount()
        keep = []; last = {}
        for i, (tk, d) in zip(X.index, X[["ticker", "date"]].values):
            dn = K.at[i, "di"]
            if tk in last and dn - last[tk] < 20: continue
            last[tk] = dn; keep.append(i)
        rows.append((nm, X.loc[keep]))
        rows.append((nm + " [날 바구니]", X.loc[keep].groupby("date")[["x20", "x60"]].mean().reset_index()))
    table("② 넓은 판(유니버스 거래대금 상위 40%) — 다음날 시가 매수 20·60일, 같은 날 유니버스 대비 초과(비용 0.43 뒤)", rows, ["x20", "x60"], ["20일", "60일"])


def part_B():
    import lab, feats as FT
    P("\n## B [갭 하락 조용주](T1) 하락장 깊이별 — 시가→종가 비용 뒤")
    H = lab.hist(); T = H[H.t1.fillna(False).astype(bool)][["date", "ticker", "oc", "gap"]].copy()
    T["oc"] -= FT.COST; T["dd"] = T.date.map(DD)
    T["bin"] = pd.cut(T.dd, [-100, -40, -30, -20, -10, 0.01], labels=["-40%↓", "-30~-40", "-20~-30", "-10~-20", "-10% 안"])
    P("| 코스피 1년 고점 대비 | 건수 | 날 수 | 건당 평균 | 승률 | 날 바구니 평균 | 날 승률 | 하루 평균 건수 | 최악의 날 |"); P("|---|---|---|---|---|---|---|---|---|")
    for b, Z in T.groupby("bin", observed=True):
        Bk = Z.groupby("date").oc.mean(); n = Z.groupby("date").size()
        P("| %s | %d | %d | %+.2f | %.0f%% | %+.2f | %.0f%% | %.1f | %+.2f |" % (b, len(Z), len(Bk), Z.oc.mean(), (Z.oc > 0).mean() * 100, Bk.mean(), (Bk > 0).mean() * 100, n.mean(), Bk.min()))
    # 하루 몰림: 그날 건수별
    n = T.groupby("date").size(); Bk = T.groupby("date").oc.mean()
    D = pd.DataFrame({"n": n, "b": Bk})
    D["nb"] = pd.cut(D.n, [0, 5, 10, 20, 40, 999], labels=["1~5", "6~10", "11~20", "21~40", "41↑"])
    P("\n| 그날 T1 건수 | 날 수 | 날 바구니 평균 | 날 승률 | 최악 |"); P("|---|---|---|---|---|")
    for b, q in D.groupby("nb", observed=True):
        P("| %s | %d | %+.2f | %.0f%% | %+.2f |" % (b, len(q), q.b.mean(), (q.b > 0).mean() * 100, q.b.min()))
    # 하루 상한 20(갭 깊은 순) 걸면
    T2 = T.sort_values(["date", "gap"]).groupby("date").head(20)
    P("\n하루 상한 20건(갭 깊은 순) 걸면: 건당 %+.2f(%d건) · 상한 없으면 %+.2f(%d건) · 41건↑ 날만 보면 상한 %+.2f vs 전체 %+.2f" % (
        T2.oc.mean(), len(T2), T.oc.mean(), len(T),
        T2[T2.date.isin(D[D.n > 40].index)].oc.mean(), T[T.date.isin(D[D.n > 40].index)].oc.mean()))


def part_C(K):
    P("\n## C 내부자 + 자사주 동시")
    I = pd.read_pickle(BASE / "data" / "insider_feat.pkl")[["ticker", "date", "ins20", "insw20"]]
    con = sqlite3.connect(BASE / "data" / "dart" / "disclosures.db")
    D = pd.read_sql("SELECT stock_code AS ticker, rcept_dt AS date, report_nm FROM disclosure WHERE length(stock_code)=6 AND rcept_dt>='20180101' "
                    "AND (report_nm LIKE '%자기주식취득결정%' OR report_nm LIKE '%자기주식취득신탁계약체결결정%') AND report_nm NOT LIKE '%정정%'", con)
    D["trust"] = D.report_nm.str.contains("신탁")
    K2 = K[K.date >= "20180101"].merge(I, on=["ticker", "date"], how="left")
    K2[["ins20", "insw20"]] = K2[["ins20", "insw20"]].fillna(0)
    TI = K2.groupby("ticker").indices; DT = K2.date.to_numpy()
    rows = {k: [] for k in ("both", "bb", "both_dn", "bb_dn", "ins")}
    for r in D.drop_duplicates(["ticker", "date"]).itertuples():
        ii = TI.get(r.ticker)
        if ii is None: continue
        j = np.searchsorted(DT[ii], r.date)
        if j >= len(ii): continue
        i = ii[j]
        if K2.bad.iat[i]: continue
        ins = K2.ins20.iat[i] > 0
        dn = bool(B60.get(DT[i], False))
        rec = dict(date=DT[i], ticker=r.ticker, x20=K2.x20.iat[i], x60=K2.x60.iat[i], trust=r.trust)
        rows["bb"].append(rec)
        if ins: rows["both"].append(rec)
        if dn: rows["bb_dn"].append(rec)
        if ins and dn: rows["both_dn"].append(rec)
    ins_only = K2[(K2.ins20 > 0) & (K2.groupby("ticker").ins20.shift(1).fillna(0) == 0) & K2.uni & ~K2.bad]
    R = [("자사주 공시(취득·신탁) 전체", pd.DataFrame(rows["bb"])), ("자사주 & 20일 안 내부자 순매수", pd.DataFrame(rows["both"])),
         ("하락장(60일선 아래) 자사주", pd.DataFrame(rows["bb_dn"])), ("하락장 자사주 & 내부자", pd.DataFrame(rows["both_dn"])),
         ("대조: 내부자 순매수 처음 켜진 날(유니버스)", ins_only[["date", "x20", "x60"]])]
    table("공시일 다음날 시가 매수 · 같은 날 유니버스 대비 초과(비용 0.43 뒤)", R, ["x20", "x60"], ["20일", "60일"])
    return pd.DataFrame(rows["both_dn"])


def part_D():
    import lab, feats as FT
    P("\n## D 미장 폭락 다음 날 국장 데이 — 시가→종가 비용 뒤")
    H = lab.hist()[["date", "ticker", "oc", "gap", "tr_res", "q_tr_res", "liq", "t1"]].copy()
    H["oc"] -= FT.COST
    X = fdr.DataReader("IXIC", "2005-01-01"); X = X[X.Close > 0]
    us = (X.Close.pct_change() * 100); us.index = us.index.strftime("%Y%m%d")
    kd = np.array(sorted(H.date.unique())); ud = us.index.values
    prev = {d: us.iloc[np.searchsorted(ud, d) - 1] if np.searchsorted(ud, d) > 0 else np.nan for d in kd}
    H["us"] = H.date.map(prev)
    t1 = H.t1.fillna(False).astype(bool)
    base = (H.gap < 0) & (H.q_tr_res <= 0.1) & (H.liq <= 1 / 3)
    rows = []
    for nm, m in (("나스닥 -3%↓ 다음날 · 갭↓ · 잔차 하위10% · 작은 종목", base & (H.us <= -3)), ("나스닥 -2%↓ 다음날 · 같은 조건", base & (H.us <= -2)),
                  ("  └ T1 아닌 것만(-2%↓)", base & (H.us <= -2) & ~t1), ("대조: 미장 평소(±1%) · 같은 조건", base & (H.us.abs() < 1)),
                  ("나스닥 -2%↓ 다음날 T1(참고)", t1 & (H.us <= -2))):
        Z = H.loc[m, ["date", "oc"]]
        rows.append((nm, Z)); rows.append((nm + " [날 바구니]", Z.groupby("date").oc.mean().reset_index()))
    table("건당 · 날 바구니", rows, ["oc"], ["시가→종가"])
    m2 = base & (H.us <= -2)
    P("\n나스닥 -2%%↓ 다음날 조건 신호 중 T1 과 겹침 %.0f%% (%d / %d)" % ((m2 & t1).sum() / max(m2.sum(), 1) * 100, (m2 & t1).sum(), m2.sum()))


def credit_flag():
    c = sqlite3.connect(f"file:{BASE / 'data' / 'kis' / 'market.db'}?mode=ro", uri=True)
    C = pd.read_sql("SELECT date, ticker, loan_rmnd_rate AS r FROM credit", c).sort_values(["ticker", "date"])
    g = C.groupby("ticker").r
    m5 = g.transform(lambda s: s.rolling(5, min_periods=4).mean()); m60 = g.transform(lambda s: s.rolling(60, min_periods=40).mean())
    m250 = g.transform(lambda s: s.rolling(250, min_periods=150).mean())
    C["flag"] = (m60 / m250 > 1.5) & (m5 / m60 < 0.3)
    return C.loc[C.flag, ["date", "ticker"]]


def part_E(ns):
    P("\n## E 신용 급증 후 급감 경고등(drop>1.5 & rise<0.3) — 우리 규칙 신호에서 빼면")
    S = ns["S"].copy(); S["ret"] = (S.exit / S.buy - 1) * 100 - S.cost
    F = credit_flag(); F["f"] = True
    # 신호일 전후 5거래일 안에 경고등 → 깃발(5일 동안 유지)
    F["d"] = pd.to_datetime(F.date)
    S["d"] = pd.to_datetime(S.date)
    mm = S.reset_index()[["index", "ticker", "d"]].merge(F[["ticker", "d"]], on="ticker", suffixes=("", "_f"))
    mm = mm[(mm.d_f <= mm.d) & (mm.d_f >= mm.d - pd.Timedelta(days=10))]
    S["flag"] = S.index.isin(mm["index"])
    P("경고등 켜진 날 %d개(종목·날) · 규칙 신호 %d건 중 깃발 %d건" % (len(F), len(S), S.flag.sum()))
    P("| 규칙 | 깃발 건수 · 평균 · 승률 | 나머지 건수 · 평균 · 승률 |"); P("|---|---|---|")
    for rid, Z in S.groupby("rid"):
        a, b = Z[Z.flag], Z[~Z.flag]
        P("| %s | %s | %s |" % (rid, "%d · %+.2f · %.0f%%" % (len(a), a.ret.mean(), (a.ret > 0).mean() * 100) if len(a) else "0",
                                "%d · %+.2f · %.0f%%" % (len(b), b.ret.mean(), (b.ret > 0).mean() * 100)))
    # 계좌
    sim = ns["simulate"]
    full = sim(1.0, 1.0, "지금 그대로", quiet=True)[0]
    ns["S"] = ns["S"][~S.flag.reindex(ns["S"].index).fillna(False).values]
    filt = sim(1.0, 1.0, "경고등 빼고", quiet=True)[0]
    def st(C):
        yrs = len(C) / 252; return C.nav.iloc[-1], C.nav.iloc[-1] ** (1 / yrs) - 1, ((C.nav / C.nav.cummax()) - 1).min() * 100
    a, b = st(full), st(filt)
    P("\n계좌(portfolio.py 9규칙): 지금 %.2f배 · 연 %.1f%% · 낙폭 %.1f%%  →  경고등 빼면 %.2f배 · 연 %.1f%% · 낙폭 %.1f%%" % (a[0], a[1] * 100, a[2], b[0], b[1] * 100, b[2]))


def main():
    ns = portfolio_ns()
    S = ns["S"].copy(); S["ret"] = (S.exit / S.buy - 1) * 100 - S.cost
    # kr_scan 유니버스 패널(A·C 공용)
    import run_spec as RS
    K, uni, _ = RS.load_market("KR")
    K["uni"] = uni.values
    K = K.sort_values(["ticker", "date"]).reset_index(drop=True)
    g = K.groupby("ticker", sort=False)
    K["di"] = g.cumcount()
    K["bad"] = ~K.uni & False
    K["vr"] = g.volume.transform(lambda s: s.rolling(5).mean()) / g.volume.transform(lambda s: s.rolling(20).mean())
    last = g.close.transform("last")
    for h in (20, 60):
        f = (g.close.shift(-h).fillna(last) / g.open.shift(-1) - 1) * 100
        f = f.clip(-95, 300)
        K["x%d" % h] = f - f.where(K.uni).groupby(K.date).transform("mean") - 0.43
    only = sys.argv[1:] or ["A", "B", "C", "D", "E"]
    if "A" in only: part_A(S, K)
    if "B" in only: part_B()
    if "C" in only: part_C(K)
    if "D" in only: part_D()
    if "E" in only: part_E(ns)
    (BASE / "research" / "cache" / "ideas5_1018.out").write_text("\n".join(OUT), encoding="utf-8")


if __name__ == "__main__":
    main()
