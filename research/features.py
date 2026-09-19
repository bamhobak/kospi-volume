# -*- coding: utf-8 -*-
"""**재료 붙이기** — 연구 패널(kr_scan.pkl)에 없는 보유 데이터를 (종목, 날짜)로 붙인다 (2026-09-19).

명세에 "features": ["q_pens20", "sb_chg20"] 처럼 적으면 run_spec 이 여기서 가져다 붙이고,
axis_scan 은 전부 붙여서 축별로 훑는다.

⚠ **시차가 전부다.** 재료가 실제로 공개되는 시점보다 먼저 쓰면 미래참조가 된다([[lookahead-surv]]).
  lag = 그 재료를 몇 거래일 늦춰 붙이나. 매수는 다음날 시가이므로 '그날 장 마감 뒤 확정' 이면 0.
    · 투자자별 순매수(investor.db flow11·flow) — 장 마감 뒤 확정 → 0
    · 공매도 잔고(krx short_balance) — **T+2 공시** → 2
    · 공매도 거래 비중(krx short_volume) — 당일 장 마감 뒤 → 0
    · 밸류(krx fundamental) — 당일 종가 기준 → 0
    · 내부자 신고(dart insider.db tx, 공시일 rcept_dt) — 장중 공시는 그날 못 산다 → 1
    · 외인 지분율(kospi/kosdaq daily) → 0
  대차(toss lending 2021~)·신용(toss credit 2023~)은 학습 구간이 거의 없어 뺐다.

모든 창(20일·60일)은 **원천 자료의 거래일**로 먼저 계산하고 붙인다 — 패널은 1,000원 미만 행을
걸러 날짜가 비기 때문이다.
"""
import sqlite3
from pathlib import Path
import numpy as np, pandas as pd

BASE = Path(__file__).resolve().parent.parent
D = BASE / "data"
FLOW11 = ["fin", "ins", "tru", "pef", "bank", "ofin", "pens", "etc", "indiv", "frgn", "ofrgn"]
FLOW11_KO = {"fin": "금융투자", "ins": "보험", "tru": "투신", "pef": "사모", "bank": "은행", "ofin": "기타금융",
             "pens": "연기금", "etc": "기타법인", "indiv": "개인", "frgn": "외국인", "ofrgn": "기타외국인"}


def _q(db, sql):
    c = sqlite3.connect("file:%s?mode=ro" % (D / db), uri=True)
    try:
        return pd.read_sql(sql, c)
    finally:
        c.close()


def _roll(df, col, n, how="sum"):
    return getattr(df.groupby("ticker", sort=False)[col].rolling(n, min_periods=n), how)().reset_index(level=0, drop=True)


# ── 로더: (ticker, date, 원천 열...) 를 돌려준다. 창 계산은 원천 거래일로. ─────────────────
def load_flow11():
    F = _q("investor.db", "SELECT ticker, date, %s FROM flow11" % ", ".join(FLOW11))
    F = F.sort_values(["ticker", "date"]).reset_index(drop=True)
    F["org"] = F[["fin", "ins", "tru", "pef", "bank", "ofin", "pens"]].sum(axis=1, min_count=1)
    out = F[["ticker", "date"]].copy()
    for t in FLOW11 + ["org"]:
        out["_f%s20" % t] = _roll(F, t, 20)
        out["_f%s5" % t] = _roll(F, t, 5)
    return out


def load_short_balance():
    S = _q("krx_daily.db", "SELECT ticker, date, bal_qty, bal_rto FROM short_balance")
    S = S.sort_values(["ticker", "date"]).reset_index(drop=True)
    g = S.groupby("ticker", sort=False)
    out = S[["ticker", "date"]].copy()
    out["sb_rto"] = S.bal_rto
    out["sb_chg20"] = S.bal_rto - g.bal_rto.shift(20)
    m60 = _roll(S, "bal_qty", 60, "mean")
    out["sb_rel60"] = S.bal_qty / m60.replace(0, np.nan)
    return out


def load_short_volume():
    S = _q("krx_daily.db", "SELECT ticker, date, vol_rto FROM short_volume")
    S = S.sort_values(["ticker", "date"]).reset_index(drop=True)
    out = S[["ticker", "date"]].copy()
    out["sv_rto5"] = _roll(S, "vol_rto", 5, "mean")
    m60 = _roll(S, "vol_rto", 60, "mean")
    out["sv_rel60"] = out.sv_rto5 / m60.replace(0, np.nan)
    return out


def load_fundamental():
    F = _q("krx_daily.db", "SELECT ticker, date, per, pbr, eps, bps, div FROM fundamental")
    F = F.sort_values(["ticker", "date"]).reset_index(drop=True)
    g = F.groupby("ticker", sort=False)
    out = F[["ticker", "date"]].copy()
    out["ey"] = np.where(F.per > 0, 100.0 / F.per, np.nan)            # 이익수익률(%) — 적자는 비움
    out["divy"] = F["div"]                                           # 배당수익률(%)
    e0 = g.eps.shift(250)
    out["eps_g"] = np.where(e0 > 0, (F.eps / e0 - 1) * 100, np.nan)   # 1년 EPS 증가율 — 전년 흑자만
    b0 = g.bps.shift(250)
    out["bps_g"] = np.where(b0 > 0, (F.bps / b0 - 1) * 100, np.nan)
    return out


def load_insider(dates):
    """공시일 기준 60거래일 매수·매도 신고 건수(보통주). 공시일이 휴일이면 다음 거래일로."""
    T = _q("dart/insider.db", "SELECT ticker, rcept_dt AS date, delta FROM tx WHERE kind='보통주' AND delta IS NOT NULL")
    T = T[T.ticker.notna() & (T.delta != 0)]
    cal = pd.Series(sorted(dates))
    pos = np.searchsorted(cal.values, T.date.values)
    ok = pos < len(cal)
    T = T[ok].assign(date=cal.values[pos[ok]])
    T["b"] = (T.delta > 0).astype(int); T["s"] = (T.delta < 0).astype(int)
    daily = T.groupby(["ticker", "date"])[["b", "s"]].sum().reset_index()
    return daily                                                      # 60일 합은 패널에 붙인 뒤 계산


def load_foreign_ratio():
    F = pd.concat([_q(db, "SELECT ticker, date, foreign_ratio fr FROM daily WHERE foreign_ratio IS NOT NULL")
                   for db in ("kospi.db", "kosdaq.db")]).drop_duplicates(["ticker", "date"])
    F = F.sort_values(["ticker", "date"]).reset_index(drop=True)
    out = F[["ticker", "date"]].copy()
    out["fr_chg20"] = F.fr - F.groupby("ticker", sort=False).fr.shift(20)
    return out


# ── 재료 목록: 이름 → (설명, 로더, 시차, 시작) ───────────────────────────────────────
GROUPS = {
    "flow11": (load_flow11, 0, "2018"),
    "short_balance": (load_short_balance, 2, "2016-07"),
    "short_volume": (load_short_volume, 0, "2005"),
    "fundamental": (load_fundamental, 0, "2005"),
    "foreign_ratio": (load_foreign_ratio, 0, "2005(코스닥 2018)"),
}
DESC = {}
for t in FLOW11 + ["org"]:
    ko = FLOW11_KO.get(t, "기관 합계")
    DESC["q_%s20" % t] = ("flow11", "%s 20일 순매수 ÷ 20일 거래대금(%%)" % ko)
    DESC["q_%s5" % t] = ("flow11", "%s 5일 순매수 ÷ 5일 거래대금(%%)" % ko)
DESC.update({
    "sb_rto": ("short_balance", "공매도 잔고 비율(%)"),
    "sb_chg20": ("short_balance", "공매도 잔고 비율 20일 변화(%p)"),
    "sb_rel60": ("short_balance", "공매도 잔고 수량 ÷ 60일 평균"),
    "sv_rto5": ("short_volume", "공매도 거래 비중 5일 평균(%)"),
    "sv_rel60": ("short_volume", "공매도 거래 비중 5일 ÷ 60일"),
    "ey": ("fundamental", "이익수익률 100/PER(%) — 적자 제외"),
    "divy": ("fundamental", "배당수익률(%)"),
    "eps_g": ("fundamental", "EPS 1년 증가율(%) — 전년 흑자만"),
    "bps_g": ("fundamental", "BPS 1년 증가율(%)"),
    "ins_b60": ("insider", "내부자 매수 신고 60일 건수(보통주)"),
    "ins_s60": ("insider", "내부자 매도 신고 60일 건수"),
    "ins_net60": ("insider", "내부자 매수−매도 신고 60일"),
    "fr_chg20": ("foreign_ratio", "외인 지분율 20일 변화(%p)"),
})
LAG = {"flow11": 0, "short_balance": 2, "short_volume": 0, "fundamental": 0, "insider": 1, "foreign_ratio": 0}


def _insider_counts(A, cal):
    """A 의 각 행에 '공시일+1 거래일부터 60거래일' 안의 매수·매도 신고 건수를 붙인다.

    패널은 행이 걸러져 날짜가 비므로 행 단위 rolling 을 쓰면 창이 늘어난다. 그래서 **전체 거래일 달력의
    번호**로 센다: 누적 건수 C(i) − C(i−60). 시차 1일은 공시일 번호에 +1 로 준다.
    """
    X = load_insider(cal)
    ci = {d: i for i, d in enumerate(cal)}
    X["ci"] = X.date.map(ci) + LAG["insider"]
    X = X.sort_values(["ticker", "ci"])
    X["cb"] = X.groupby("ticker").b.cumsum(); X["cs"] = X.groupby("ticker").s.cumsum()
    Q = pd.DataFrame({"ticker": A.ticker.values, "ci": A.date.map(ci).values, "_r": np.arange(len(A))})
    out = {}
    for tag, shift in (("now", 0), ("old", 60)):
        q = Q.assign(ci=Q.ci - shift).sort_values("ci")
        m = pd.merge_asof(q, X[["ticker", "ci", "cb", "cs"]].sort_values("ci"), on="ci", by="ticker",
                          direction="backward").sort_values("_r")
        out[tag] = m[["cb", "cs"]].fillna(0).values
    d = out["now"] - out["old"]
    return {"ins_b60": d[:, 0], "ins_s60": d[:, 1], "ins_net60": d[:, 0] - d[:, 1]}


def attach(A, names=None, cal=None):
    """A(패널)에 재료를 붙인다. names=None 이면 전부. 붙인 열 이름 목록을 돌려준다.

    A 는 미리 걸러 둬도 된다(메모리 — 1천만 행에 40열이면 3GB 가 넘는다). 창·시차는 원천 거래일로
    계산하므로 A 의 빈 날짜에 영향받지 않는다. cal = 전체 거래일 달력(내부자 창에 필요, 없으면 A 의 날짜).
    """
    want = list(DESC) if names is None else list(names)
    bad = [n for n in want if n not in DESC]
    if bad:
        raise KeyError("모르는 재료 %s — research/features.py DESC 에서 고를 것" % bad)
    groups = sorted({DESC[n][0] for n in want})
    n0 = len(A); added = []
    for gname in groups:
        if gname == "insider":
            vals = _insider_counts(A, sorted(cal if cal is not None else A.date.unique()))
            for k, v in vals.items():
                A[k] = v
        else:
            X = GROUPS[gname][0]()
            cols = [c for c in X.columns if c not in ("ticker", "date")]
            lag = LAG[gname]
            if lag:                                   # 원천 거래일 기준으로 늦춘다
                X[cols] = X.groupby("ticker", sort=False)[cols].shift(lag)
            T = A[["ticker", "date"]].merge(X, on=["ticker", "date"], how="left")
            assert len(T) == n0
            for c in cols:
                A[c] = T[c].values
        if gname == "flow11":
            amt = A.amt20 * 1e8                                         # amt20 = 20일 평균 거래대금(억)
            for t in FLOW11 + ["org"]:
                A["q_%s20" % t] = A["_f%s20" % t] / (amt * 20) * 100
                A["q_%s5" % t] = A["_f%s5" % t] / (amt * 5) * 100
            A.drop(columns=[c for c in A.columns if c.startswith("_f")], inplace=True)
        added += [n for n in DESC if DESC[n][0] == gname]
    return [n for n in added if n in want or names is None]
