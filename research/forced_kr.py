# -*- coding: utf-8 -*-
"""'남들이 어쩔 수 없이 파는 자리' 국장 6종 (2026-10-15 사용자 "안 잰 것들 다 재봐") — H0339~H0344.

E1 레버리지 ETF 장 마감 재조정 — 지수 -2%↓ 날 대형주(시총 상위 200·코스닥 150)는 마감 직전 기계적 매도 → 종가 → 다음날 시가 되돌림?
   레버리지 ETF 없던 2005~2009 와 비교(코스피 레버리지 2010-02 · 코스닥150 레버리지 2015-12).
E2 선물·옵션 만기일 — 매달 둘째 목요일(휴장이면 앞 거래일) · 분기(3·6·9·12월) 동시만기 → 대형주 종가 매수 → 다음날 시가·종가.
E3 관리종목 지정(사유 발생) — 펀드 규약상 보유 불가 → 기계적 정리 → 지정 공시 뒤 1·5·10·20일째 매수 20·60일 보유.
E4 분기말 손실 종목 정리 — 분기 수익 -20%↓ & 분기 마지막 3일 기관 순매도 → 분기 마지막 날 종가 매수 5·10·20일
   (대조: 분기말 아닌 달 말 같은 조건).
E5 환율 급등일 외인 기계적 매도 — 원·달러 +1%↑ 날 외인 비중 상위 대형주 중 그날 외인 순매도 → 종가 매수 1·5·20일 (대조: 평소 외인 순매도).
E6 감사 시즌 투매 — 3월 한 달 -20%↓ & 적자(PER ≤ 0 또는 없음) 소형주 → 4월 첫 거래일 시가 매수 20·60일
   (대조: 10월 한 달 같은 조건 → 11월 첫날) · 상장폐지는 마지막 가격으로(생존 편향 없이).
잣대: 같은 날 유니버스(국장 전 종목 주가 1천원↑·우선주 제외) 같은 보유 평균 대비 초과 · 이벤트 바구니(같은 날 신호 평균) 단위 t값도.
비용: 데이 0.23 · 스윙 0.23 + 미끄러짐 0.2. 구간 옛날 ~15 · 학습 16~22 · 검증 23~.
    python research/forced_kr.py
"""
import sys, glob, sqlite3
from pathlib import Path
import numpy as np, pandas as pd
import FinanceDataReader as fdr

BASE = Path(__file__).resolve().parent.parent
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))
PER = [("옛날", "20050101", "20151231"), ("학습", "20160101", "20221231"), ("검증", "20230101", "20991231")]
CD, CS = 0.23, 0.43


def load():
    A = pd.read_pickle(BASE / "data" / "kr_scan.pkl")[["date", "ticker", "open", "high", "low", "close", "volume", "marcap", "PER", "mk", "pref", "amt20"]]
    A = A[(A.close >= 1000) & (~A.pref.fillna(False))].sort_values(["ticker", "date"]).reset_index(drop=True)
    A["cap"] = np.where(A.marcap > 1e9, A.marcap / 1e8, A.marcap)
    g = A.groupby("ticker", sort=False)
    pc = g.close.shift(1)
    lim = np.where(A.date < "20150615", 0.16, 0.31)
    seam = (((A.close / pc - 1).abs() > lim) | ((A.open / pc - 1).abs() > lim)).to_numpy()
    tk = A.ticker.to_numpy(); bad = np.zeros(len(A), bool)
    for i in np.flatnonzero(seam):
        lo, hi = max(i - 60, 0), min(i + 60, len(A) - 1); bad[lo:hi + 1] |= (tk[lo:hi + 1] == tk[i])
    A["bad"] = bad
    # 앞으로 수익(시가·종가 기준) — 상장폐지면 마지막 종가
    A["n_open"] = g.open.shift(-1); A["n_close"] = g.close.shift(-1)
    A["on"] = (A.n_open / A.close - 1) * 100                      # 오늘 종가 → 내일 시가
    A["cc1"] = (A.n_close / A.close - 1) * 100                    # 오늘 종가 → 내일 종가
    last = g.close.transform("last")
    for h in (5, 10, 20, 60):
        fc = g.close.shift(-h).fillna(last)
        A["c%d" % h] = (fc / A.close - 1) * 100                   # 오늘 종가 매수 → h일 뒤 종가
        fo = g.close.shift(-h).fillna(last)
        A["o%d" % h] = (fo / A.n_open - 1) * 100                  # 내일 시가 매수 → h일 뒤 종가(대략)
    for c in ["on", "cc1"] + ["c%d" % h for h in (5, 10, 20, 60)] + ["o%d" % h for h in (5, 10, 20, 60)]:
        A[c] = A[c].clip(-95, 300)
        A["x_" + c] = A[c] - A[c].where(~A.bad).groupby(A.date).transform("mean")
    A["rk_kp"] = A[A.mk == "KOSPI"].groupby("date").cap.rank(ascending=False)
    A["rk_kq"] = A[A.mk == "KOSDAQ"].groupby("date").cap.rank(ascending=False)
    return A


def per(d):
    return np.where(d <= "20151231", "옛날", np.where(d <= "20221231", "학습", "검증"))


def cell(x):
    x = x.dropna()
    if len(x) < 8: return "%d건" % len(x)
    t = x.mean() / (x.std(ddof=1) / np.sqrt(len(x))) if x.std() > 0 else 0
    return "%d · %+.2f · %.0f%% · t%.1f" % (len(x), x.mean(), (x > 0).mean() * 100, t)


def table(title, E, cols, head):
    """E: 행마다 이벤트(바구니) — date, 그리고 cols 값들. 구간별 평균·승률·t."""
    P("\n### " + title)
    P("| 판 | " + " | ".join("%s 옛날 | 학습 | 검증" % h for h in head) + " |")
    P("|---" * (1 + 3 * len(head)) + "|")
    for nm, Z in E:
        Z = Z.assign(p=per(Z.date.values))
        cs = []
        for c in cols:
            for p, _, _ in PER: cs.append(cell(Z.loc[Z.p == p, c]))
        P("| %s | %s |" % (nm, " | ".join(cs)))


def basket(A, m, cols):
    """신호를 같은 날끼리 평균 → 날 단위 표본."""
    return A.loc[m & ~A.bad].groupby("date")[cols].mean().reset_index()


def e1(A):
    P("\n## E1 레버리지 ETF 장 마감 재조정 — 지수 크게 빠진 날 대형주 종가 → 다음날 (칸: 날 수 · 평균% · 승률 · t)")
    ix = {}
    for code in ("KS11", "KQ11"):
        X = fdr.DataReader(code, "2004-06-01"); X = X[X.Close > 0]
        ix[code] = dict(zip(X.index.strftime("%Y%m%d"), X.Close.pct_change() * 100))
    A["ixr"] = np.where(A.mk == "KOSPI", A.date.map(ix["KS11"]), A.date.map(ix["KQ11"]))
    big = np.where(A.mk == "KOSPI", A.rk_kp <= 200, A.rk_kq <= 150)
    small = np.where(A.mk == "KOSPI", A.rk_kp > 300, A.rk_kq > 300)
    rows = []
    for nm, m in (("지수 -2%↓ 날 · 대형(코스피200·코스닥150 근사)", (A.ixr <= -2) & big), ("지수 -2%↓ 날 · 소형(300위 밖)", (A.ixr <= -2) & small),
                  ("지수 -3%↓ 날 · 대형", (A.ixr <= -3) & big), ("지수 +2%↑ 날 · 대형(반대 방향 확인)", (A.ixr >= 2) & big),
                  ("평소(지수 ±1% 안) · 대형", (A.ixr.abs() < 1) & big)):
        B = basket(A, pd.Series(m, index=A.index).fillna(False), ["on", "cc1"]); B["on"] -= CD; B["cc1"] -= CD
        rows.append((nm, B))
    table("대형 바구니: 종가 매수 → 다음날 시가(비용 0.23 뒤) / 다음날 종가", rows, ["on", "cc1"], ["→시가", "→종가"])
    P("※ 옛날 구간 2005~2009 는 레버리지 ETF 없던 때(2010-02 코스피 레버리지 상장) — 효과가 ETF 때문이면 2010 뒤에만 커야 함")
    B = basket(A, pd.Series((A.ixr <= -2) & big, index=A.index).fillna(False), ["on"])
    B["era"] = np.where(B.date < "20100201", "ETF 전 2005~10.01", np.where(B.date < "20160101", "ETF 초기 2010~15", "ETF 큼 2016~"))
    P("| 시기 | 날 수 | 종가→시가 평균(비용 전) | 승률 |"); P("|---|---|---|---|")
    for e, q in B.groupby("era"): P("| %s | %d | %+.2f | %.0f%% |" % (e, len(q), q.on.mean(), (q.on > 0).mean() * 100))


def expiry_days(dates):
    D = pd.Series(sorted(set(dates))); dt = pd.to_datetime(D)
    out = {}
    for (y, mth), q in dt.groupby([dt.dt.year, dt.dt.month]):
        first = pd.Timestamp(y, mth, 1); th = first + pd.Timedelta(days=(3 - first.weekday()) % 7 + 7)   # 둘째 목요일
        cand = q[q <= th]
        if len(cand): out[cand.max().strftime("%Y%m%d")] = "분기" if mth in (3, 6, 9, 12) else "월"
    return out


def e2(A):
    P("\n## E2 선물·옵션 만기일 — 대형주 바구니 만기일 종가 매수 (칸: 날 수 · 평균% · 승률 · t)")
    ex = expiry_days(A.date.unique())
    A["exp"] = A.date.map(ex)
    big = (A.mk == "KOSPI") & (A.rk_kp <= 200)
    A["oc"] = (A.close / A.open - 1) * 100
    rows = []
    for nm, m in (("분기 동시만기 · 코스피 대형 200", big & (A.exp == "분기")), ("월 만기 · 코스피 대형 200", big & (A.exp == "월")),
                  ("만기 아닌 날 · 코스피 대형 200(대조)", big & A.exp.isna())):
        B = basket(A, m, ["oc", "on", "cc1", "c5"]); B["on"] -= CD; B["cc1"] -= CD; B["c5"] -= CS
        rows.append((nm, B))
    table("만기일 당일 시가→종가(비용 전) / 종가→다음날 시가 / 다음날 종가 / 5일 (비용 뒤)", rows, ["oc", "on", "cc1", "c5"], ["당일", "→시가", "→종가", "5일"])


def e3(A):
    P("\n## E3 관리종목 지정(사유 발생) — 공시 뒤 k일째 시가 매수 · 같은 날 유니버스 대비 초과(종목 단위, 칸: 건수 · 평균 · 승률 · t)")
    con = sqlite3.connect(BASE / "data" / "dart" / "disclosures.db")
    D = pd.read_sql("SELECT stock_code AS ticker, rcept_dt AS date, report_nm FROM disclosure WHERE length(stock_code)=6 AND report_nm LIKE '%관리종목%'", con)
    D["t"] = D.report_nm.str.replace(r"\s+", "", regex=True)
    real = D.t.str.contains("관리종목지정$|관리종목지정사유발생|내부결산시점관리종목지정|관리종목지정\)$|^관리종목지정사유추가") & ~D.t.str.contains("해제|해소|우려")
    worry = D.t.str.contains("우려") & ~D.t.str.contains("해제|해소")
    TI = A.groupby("ticker").indices
    DT = A.date.to_numpy()
    rows = []
    for nm, m in (("지정·사유 발생", real), ("지정 우려(시총·주가·거래량 미달 예고)", worry)):
        ev = D[m].copy()
        ev["y"] = ev.date.str[:4]; ev = ev.sort_values("date").drop_duplicates(["ticker", "y"])
        for k in (1, 5, 10, 20):
            recs = []
            for r in ev.itertuples():
                ii = TI.get(r.ticker)
                if ii is None: continue
                j = np.searchsorted(DT[ii], r.date)               # 공시일(또는 다음 거래일)이 1일째
                if j + k - 1 >= len(ii): continue
                i = ii[j + k - 1]                                 # k번째 거래일 → 다음날 시가 매수(o 계열)
                if A.bad.iat[i]: continue
                recs.append(dict(date=DT[i], x20=A.x_o20.iat[i] - CS, x60=A.x_o60.iat[i] - CS, r20=A.o20.iat[i] - CS))
            R = pd.DataFrame(recs)
            if len(R): rows.append(("%s · %d일째" % (nm, k), R))
    table("20일 초과 / 60일 초과 / 20일 절대(비용 뒤)", rows, ["x20", "x60", "r20"], ["20일 초과", "60일 초과", "20일 절대"])


def e4(A, F):
    P("\n## E4 분기말 손실 종목 정리 — 분기 수익 -20%↓ & 마지막 3일 기관 순매도 → 마지막 날 종가 매수 (종목 단위 초과)")
    A["ym"] = A.date.str[:6]
    last_days = A.groupby("ym").date.max()
    me = set(last_days.values)
    A["is_me"] = A.date.isin(me); A["qe"] = A.is_me & A.date.str[4:6].isin(["03", "06", "09", "12"])
    g = A.groupby("ticker", sort=False)
    A["r60"] = (A.close / g.close.shift(60) - 1) * 100
    A = A.merge(F[["ticker", "date", "org3"]], on=["ticker", "date"], how="left")
    rows = []
    for nm, m in (("분기말 · 60일 -20%↓ · 기관 3일 순매도", A.qe & (A.r60 <= -20) & (A.org3 < 0)), ("분기말 · 60일 -20%↓ (기관 무관)", A.qe & (A.r60 <= -20)),
                  ("대조: 분기말 아닌 달 말 · 60일 -20%↓ · 기관 순매도", A.is_me & ~A.qe & (A.r60 <= -20) & (A.org3 < 0)),
                  ("대조: 분기말 아닌 달 말 · 60일 -20%↓ (기관 무관)", A.is_me & ~A.qe & (A.r60 <= -20)),
                  ("대조: 아무 날 · 60일 -20%↓", A.r60 <= -20)):
        R = A.loc[m & ~A.bad, ["date", "x_c5", "x_c10", "x_c20"]].copy()
        for c in ("x_c5", "x_c10", "x_c20"): R[c] -= CS
        rows.append((nm, R))
    table("종가 매수 5·10·20일 초과(비용 뒤)", rows, ["x_c5", "x_c10", "x_c20"], ["5일", "10일", "20일"])
    # 날짜 묶음(분기말 하루 = 표본 1개) — 같은 날 신호가 몰려 t가 부풀지 않게
    brow = []
    for nm, R in rows[1:2] + rows[3:4]:
        B = R.groupby("date")[["x_c5", "x_c10", "x_c20"]].mean().reset_index()
        brow.append((nm + " [날 바구니]", B))
    table("날 바구니(그날 신호 평균 = 표본 1개) 5·10·20일 초과", brow, ["x_c5", "x_c10", "x_c20"], ["5일", "10일", "20일"])
    B = brow[0][1].copy(); B["y"] = B.date.str[:4]
    P("분기말 바구니 5일 초과 해마다(4분기 평균): " + " ".join("%s%+.1f" % (y[2:], v) for y, v in B.groupby("y").x_c5.mean().items()))
    P("분기별(3·6·9·12월) 5일 초과 평균: " + " ".join("%s월 %+.2f(%d)" % (m, q.x_c5.mean(), len(q)) for m, q in B.groupby(B.date.str[4:6])))
    return A


def e5(A, F):
    P("\n## E5 환율 급등일 외인 기계적 매도 — 원·달러 +1%↑ 날, 외인 비중 상위 30% 대형주 중 그날 외인 순매도 → 종가 매수")
    X = fdr.DataReader("USD/KRW", "2004-06-01"); X = X[X.Close > 0]
    fx = dict(zip(X.index.strftime("%Y%m%d"), X.Close.pct_change() * 100))
    A["fx"] = A.date.map(fx)
    big = (A.mk == "KOSPI") & (A.rk_kp <= 200)
    A["q_fr"] = A.groupby("date").fr.rank(pct=True)
    rows = []
    for nm, m in (("환율 +1%↑ · 대형 · 외인 비중 상위30% · 외인 순매도", big & (A.fx >= 1) & (A.q_fr >= 0.7) & (A.frgn < 0)),
                  ("환율 +1.5%↑ · 같은 조건", big & (A.fx >= 1.5) & (A.q_fr >= 0.7) & (A.frgn < 0)),
                  ("대조: 환율 ±0.3% 안 · 같은 조건", big & (A.fx.abs() < 0.3) & (A.q_fr >= 0.7) & (A.frgn < 0))):
        B = basket(A, m.fillna(False), ["x_cc1", "x_c5", "x_c20"])
        B["x_cc1"] -= CD; B["x_c5"] -= CS; B["x_c20"] -= CS
        rows.append((nm, B))
    table("날 바구니 초과: 다음날 종가 / 5일 / 20일 (비용 뒤)", rows, ["x_cc1", "x_c5", "x_c20"], ["1일", "5일", "20일"])


def e6(A):
    P("\n## E6 감사 시즌 투매 — 3월 한 달 -20%↓ 적자 소형주 → 4월 첫 거래일 종가 매수 (종목 단위 초과 · 폐지는 마지막 가격)")
    A["ym"] = A.date.str[:6]
    g = A.groupby(["ticker", "ym"], sort=False)
    M = g.agg(first_o=("open", "first"), last_c=("close", "last"), cap=("cap", "last"), PER=("PER", "last")).reset_index()
    M["mret"] = (M.last_c / M.first_o - 1) * 100
    M["mm"] = M.ym.str[4:]
    firstday = A.groupby("ym").date.min()
    rows = []
    for nm, mm, cond in (("3월 -20%↓ · 적자 · 시총 하위 절반 → 4월 첫날", "03", "loss"), ("3월 -20%↓ · 흑자(대조)", "03", "profit"),
                         ("10월 -20%↓ · 적자 · 소형 → 11월 첫날(대조)", "10", "loss")):
        S = M[(M.mm == mm) & (M.mret <= -20)].copy()
        S["capq"] = S.groupby("ym").cap.rank(pct=True)
        loss = S.PER.isna() | (S.PER <= 0)
        S = S[(loss & (S.capq <= 0.5)) if cond == "loss" else ~loss]
        S["nym"] = (pd.to_datetime(S.ym + "01") + pd.offsets.MonthBegin(1)).dt.strftime("%Y%m")
        S["bd"] = S.nym.map(firstday)
        R = S.merge(A[["ticker", "date", "x_c20", "x_c60", "c20", "c60"]], left_on=["ticker", "bd"], right_on=["ticker", "date"], how="inner")
        for c in ("x_c20", "x_c60", "c20", "c60"): R[c] -= CS
        rows.append((nm, R[["date", "x_c20", "x_c60", "c60"]]))
    table("20일 초과 / 60일 초과 / 60일 절대 (비용 뒤)", rows, ["x_c20", "x_c60", "c60"], ["20일 초과", "60일 초과", "60일 절대"])


def main():
    A = load()
    fs = sorted(glob.glob(str(BASE / "data" / "20[0-2][0-9]-[01][0-9].csv")))
    F = pd.concat([pd.read_csv(f, usecols=["date", "ticker", "organ", "frgn", "foreign_ratio"], dtype={"ticker": str, "date": str}) for f in fs], ignore_index=True)
    F = F.drop_duplicates(["ticker", "date"]).sort_values(["ticker", "date"])
    F["org3"] = F.groupby("ticker").organ.transform(lambda s: s.rolling(3, min_periods=1).sum())
    A = A.merge(F[["ticker", "date", "frgn", "foreign_ratio"]].rename(columns={"foreign_ratio": "fr"}), on=["ticker", "date"], how="left")
    P("# 강제 매도 자리 국장 6종 — 유니버스 %d줄 %s~%s" % (len(A), A.date.min(), A.date.max()))
    if len(sys.argv) > 1 and sys.argv[1] == "e4":
        e4(A, F); (BASE / "research" / "cache" / "forced_kr_e4.out").write_text("\n".join(OUT), encoding="utf-8"); return
    e1(A); e2(A); e5(A, F)
    A = e4(A, F)
    e6(A)
    e3(A)
    (BASE / "research" / "cache" / "forced_kr.out").write_text("\n".join(OUT), encoding="utf-8")


if __name__ == "__main__":
    main()
