# -*- coding: utf-8 -*-
"""**미장 재료 붙이기** — us_scan.pkl 에 없는 보유 데이터를 (종목, 날짜)로 붙인다 (2026-09-19).

⚠ 시차(공개 시점)가 전부다. 매수는 다음날 시가이므로 '그날 장 마감 뒤 공개' 면 0.
    · FINRA 공매도 거래량(data/us/finra, 2019~) — 당일 저녁 공개 → 0
    · FTD 결제 실패(data/us/ftd, 2017.07~) — SEC 가 반월 단위로 **약 2~4주 뒤** 공개 → 25거래일
    · 내부자 Form4(data/us/insider_all.pkl) — **공시일(fdate)** 기준, 2영업일 내 제출 → 0 (공시일 = 신호일)
    · 재무(data/us/fin.pkl) — **제출일(filed)** 다음 거래일부터
  이미 판정이 난 것은 뺐다: 13F(45일 지연)·N-PORT 보유(60일) — 종목 축 없음([[us-new-data-insider-flow]]).

재무 두 축은 학계에 문서화된 이상현상이다.
    · 자산 증가율(asset growth) — 자산을 크게 늘린 회사가 이후 부진(Cooper·Gulen·Schill 2008)
    · 주식 수 증가율(net share issuance) — 주식을 찍어낸 회사가 부진, 자사주로 줄인 회사가 선전
"""
import glob
from pathlib import Path
import numpy as np, pandas as pd

BASE = Path(__file__).resolve().parent.parent
U = BASE / "data" / "us"

DESC = {
    "us_sr5": ("finra", "공매도 거래 비중 5일 평균(%)"),
    "us_sr20": ("finra", "공매도 거래 비중 20일 평균(%)"),
    "us_sr_rel": ("finra", "공매도 거래 비중 5일 ÷ 60일"),
    "us_ftd20": ("ftd", "결제 실패 20일 합 ÷ 20일 거래대금(%) — 25거래일 늦춤"),
    "us_insb60": ("insider", "내부자 장내 매수액 60일 합 ÷ 60일 거래대금(%)"),
    "us_inss60": ("insider", "내부자 장내 매도액 60일 합 ÷ 60일 거래대금(%)"),
    "us_ag": ("fin", "자산 1년 증가율(%) — 제출일 기준"),
    "us_shg": ("fin", "주식 수 1년 증가율(%) — 제출일 기준"),
}


def _roll(df, col, n, how="mean", mp=None):
    return getattr(df.groupby("ticker", sort=False)[col].rolling(n, min_periods=mp or n), how)().reset_index(level=0, drop=True)


def _finra():
    F = pd.concat([pd.read_pickle(f) for f in sorted(glob.glob(str(U / "finra" / "*.pkl")))], ignore_index=True)
    F = F[F.totvol > 0].drop_duplicates(["date", "ticker"], keep="last").sort_values(["ticker", "date"]).reset_index(drop=True)
    F["sr"] = F.shortvol / F.totvol * 100
    out = F[["ticker", "date"]].copy()
    out["us_sr5"] = _roll(F, "sr", 5)
    out["us_sr20"] = _roll(F, "sr", 20, mp=10)
    m60 = _roll(F, "sr", 60, mp=30)
    out["us_sr_rel"] = out.us_sr5 / m60.replace(0, np.nan)
    return out


def _panel_series(A, cal, X, valcol):
    """(ticker, date, 값) 을 전체 거래일 달력 위의 일별 값으로 깐다 — 없는 날은 0."""
    ci = {d: i for i, d in enumerate(cal)}
    X = X[X.date.isin(ci)].copy()
    X["ci"] = X.date.map(ci)
    return X[["ticker", "ci", valcol]]


def _window_sum(A, cal, X, valcol, n, lag):
    """달력 번호로 (lag 만큼 늦춘) n 거래일 창의 합: C(i-lag) − C(i-lag-n). 패널의 빈 날에 안 늘어난다."""
    ci = {d: i for i, d in enumerate(cal)}
    X = _panel_series(A, cal, X, valcol).sort_values(["ticker", "ci"])
    X["cum"] = X.groupby("ticker")[valcol].cumsum()
    Q = pd.DataFrame({"ticker": A.ticker.values, "ci": A.date.map(ci).values, "_r": np.arange(len(A))})
    got = {}
    for tag, sh in (("a", lag), ("b", lag + n)):
        q = Q.assign(ci=Q.ci - sh).dropna(subset=["ci"]).astype({"ci": np.int64}).sort_values("ci")
        m = pd.merge_asof(q, X[["ticker", "ci", "cum"]].sort_values("ci"), on="ci", by="ticker",
                          direction="backward").sort_values("_r")
        got[tag] = pd.Series(m.cum.fillna(0).values, index=m._r.values).reindex(np.arange(len(A))).fillna(0).values
    return got["a"] - got["b"]


def _fin(A):
    F = pd.read_pickle(U / "fin.pkl").dropna(subset=["filed"])
    F["end"] = F.end.astype(str); F["filed"] = F.filed.astype(str)
    out = []
    for col, name in (("assets", "us_ag"), ("shares", "us_shg")):
        X = F[["ticker", "end", "filed", col]].dropna().sort_values(["ticker", "end", "filed"])
        X = X.drop_duplicates(["ticker", "end"], keep="first")          # 처음 제출된 값(정정 전)
        X["endd"] = pd.to_datetime(X.end, format="%Y%m%d", errors="coerce")
        X = X.dropna(subset=["endd"])
        P = X[["ticker", "endd", col]].rename(columns={col: "prev", "endd": "pend"})
        X["want"] = X.endd - pd.Timedelta(days=365)
        M = pd.merge_asof(X.sort_values("want"), P.sort_values("pend"), left_on="want", right_on="pend",
                          by="ticker", direction="nearest", tolerance=pd.Timedelta(days=45))
        M[name] = np.where(M.prev > 0, (M[col] / M.prev - 1) * 100, np.nan)
        M = M.dropna(subset=[name])[["ticker", "filed", name]]
        out.append(M)
    return out


def attach(A, names=None, cal=None):
    """A(미장 패널)에 재료를 붙인다. A 는 미리 걸러 둬도 된다(창·시차는 전체 달력으로 계산)."""
    want = list(DESC) if names is None else list(names)
    cal = sorted(cal if cal is not None else A.date.unique())
    groups = sorted({DESC[n][0] for n in want})
    n0 = len(A)
    if "finra" in groups:
        X = _finra()
        T = A[["ticker", "date"]].merge(X, on=["ticker", "date"], how="left"); assert len(T) == n0
        for c in ("us_sr5", "us_sr20", "us_sr_rel"):
            A[c] = T[c].values
    amt = A.amt20 * 1e6                                                 # amt20 = 20일 평균 거래대금(백만$)
    if "ftd" in groups:
        X = pd.concat([pd.read_pickle(f) for f in sorted(glob.glob(str(U / "ftd" / "*.pkl")))], ignore_index=True)
        X["v"] = pd.to_numeric(X.ftd, errors="coerce") * pd.to_numeric(X.px, errors="coerce")   # 일부 파일은 글자
        X = X.dropna(subset=["v"]); X["date"] = X.date.astype(str)
        X = X.groupby(["ticker", "date"], as_index=False).v.sum()
        s = _window_sum(A, cal, X, "v", 20, 25)
        A["us_ftd20"] = s / (amt * 20) * 100
        A.loc[A.date < "20170901", "us_ftd20"] = np.nan                 # 자료 시작 전은 0 이 아니라 모름
    if "insider" in groups:
        I = pd.read_pickle(U / "insider_all.pkl")
        I = I[(I.form == "4") & (I.price > 0) & (I.val > 0) & (I.val < 1e8)]
        I = I.rename(columns={"fdate": "date"})
        I["date"] = I.date.astype(str)
        for code, name in (("P", "us_insb60"), ("S", "us_inss60")):
            X = I[I.code == code].groupby(["ticker", "date"], as_index=False).val.sum()
            A[name] = _window_sum(A, cal, X, "val", 60, 0) / (amt * 60) * 100
        A.loc[A.date < "20061001", ["us_insb60", "us_inss60"]] = np.nan
    if "fin" in groups:
        ci = {d: i for i, d in enumerate(cal)}
        for M in _fin(A):
            name = [c for c in M.columns if c.startswith("us_")][0]
            pos = np.searchsorted(np.array(cal), M.filed.values, side="right")   # 제출일 다음 거래일부터
            ok = pos < len(cal)
            M = M[ok].assign(ci=pos[ok]).sort_values("ci")
            M = M.drop_duplicates(["ticker", "ci"], keep="last")
            Q = pd.DataFrame({"ticker": A.ticker.values, "ci": A.date.map(ci).values, "_r": np.arange(len(A))}).sort_values("ci")
            m = pd.merge_asof(Q, M[["ticker", "ci", name]], on="ci", by="ticker", direction="backward",
                              tolerance=400).sort_values("_r")               # 400거래일 넘게 묵은 재무는 버린다
            A[name] = m[name].values
    return [n for n in DESC if DESC[n][0] in groups and (names is None or n in want)]
