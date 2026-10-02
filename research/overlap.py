# -*- coding: utf-8 -*-
"""B — 규칙 겹침 (2026-10-03, 사용자: a b c 다 해줘).
같은 종목에 **다른 규칙이 최근 5거래일 안(같은 날 포함)** 이미 신호를 냈으면 '겹침'. 미래 신호는 안 본다(매수 시점에 아는 것만).
규칙마다 겹친 거래 vs 안 겹친 거래 수익(비용 차감)을 견준다 — 규칙끼리 보유일이 달라 섞으면 안 되므로 규칙 안에서 비교.
z = (겹침 평균 − 규칙 전체 평균) ÷ (같은 건수 무작위 표본의 표준오차). 학습 ~2022 · 검증 2023~.
    python research/overlap.py
"""
import pickle, sys, time
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(BASE))
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))


def mark(S, cal, W=5):
    pos = {d: i for i, d in enumerate(cal)}
    S = S.copy(); S["ix"] = S.date.map(pos)
    S = S.dropna(subset=["ix"]); S["ix"] = S.ix.astype(int)
    by = {t: g[["ix", "rid"]].values for t, g in S.groupby("ticker")}
    ov, ovf = [], []
    for t, i, rid in zip(S.ticker, S.ix, S.rid):
        g = by[t]
        past = g[(g[:, 0] <= i) & (g[:, 0] >= i - W) & (g[:, 1] != rid)]
        fut = g[(g[:, 0] > i) & (g[:, 0] <= i + W) & (g[:, 1] != rid)]
        ov.append(len(set(past[:, 1]))); ovf.append(len(set(fut[:, 1])))
    S["ov"] = ov; S["ovf"] = ovf
    return S


def table(S, mk):
    rows = []
    rng = np.random.default_rng(0)
    for rid, g in S.groupby("rid"):
        for per, z in (("학습", g[g.date <= "20221231"]), ("검증", g[g.date >= "20230101"])):
            k = z[z.ov >= 1]; s = z[z.ov == 0]
            if len(z) < 20:
                continue
            se = z.r.std() / np.sqrt(max(len(k), 1)) * np.sqrt(max(1 - len(k) / len(z), 0))
            rows.append(dict(mk=mk, rid=rid, per=per, n=len(z), nk=len(k), m=z.r.mean(), mk_=k.r.mean() if len(k) else np.nan,
                             ms=s.r.mean(), wk=(k.r > 0).mean() * 100 if len(k) else np.nan, ws=(s.r > 0).mean() * 100,
                             medk=k.r.median() if len(k) else np.nan, meds=s.r.median(),
                             z=(k.r.mean() - z.r.mean()) / se if len(k) >= 5 and se > 0 else np.nan))
    return pd.DataFrame(rows)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    t0 = time.time()
    import rule_scan as RS
    real = sys.stdout
    K = RS.kr_signals(); sys.stdout = real
    K = K[["date", "ticker", "rid", "r"]]
    A = pd.read_pickle(BASE / "data" / "us_scan.pkl")[["date"]] if False else None
    Ucal = None
    U = pickle.load(open(BASE / "data" / "sector_drop_us_sig.pkl", "rb"))["S"].copy()
    U["r"] = U.ret.astype(float)
    if U.r.abs().median() < 1:
        U["r"] = U.r * 100
    U = U[["date", "ticker", "rid", "r"]]
    kcal = sorted(K.date.unique()); ucal = sorted(U.date.unique())
    # 달력은 신호 날짜가 아니라 거래일이어야 — 패널 거래일
    try:
        import run_spec as R
        Ak, _, _ = R.load_market("KR"); kcal = sorted(Ak.date.unique()); del Ak
        Au, _, _ = R.load_market("US"); ucal = sorted(Au.date.unique()); del Au
    except Exception as e:
        print("달력 대체", e)
    K = mark(K, kcal); U = mark(U, ucal)
    pd.to_pickle((K, U), ROOT / "cache" / "overlap.pkl")
    P("# B — 규칙 겹침 · %s" % time.strftime("%Y-%m-%d")); P("")
    for mk, S in (("국장", K), ("미장", U)):
        P("## %s — 신호 %d건 · 최근 5일 안 다른 규칙 신호가 있던 것 %d건(%.1f%%) · 뒤 5일 안 다른 규칙이 따라온 것 %.1f%%" % (
            mk, len(S), (S.ov >= 1).sum(), (S.ov >= 1).mean() * 100, (S.ovf >= 1).mean() * 100)); P("")
        T = table(S, mk)
        P("| 규칙 | 기간 | 전체 건수 | 겹침 건수 | 겹침 평균 · 중앙 · 승률 | 단독 평균 · 중앙 · 승률 | z |"); P("|---|---|---|---|---|---|---|")
        f = lambda v: "%+.2f" % v if v == v else "-"
        for _, x in T.iterrows():
            P("| %s | %s | %d | %d | %s · %s · %s | %s · %s · %.0f%% | %s |" % (
                x.rid, x.per, x.n, x.nk, f(x.mk_), f(x.medk), ("%.0f%%" % x.wk) if x.wk == x.wk else "-", f(x.ms), f(x.meds), x.ws,
                ("%.1f" % x.z) if x.z == x.z else "-"))
        # 묶음: 전 규칙 합쳐 규칙별 평균을 빼고(규칙 효과 제거) 겹침 효과
        S = S.copy(); S["rr"] = S.r - S.groupby("rid").r.transform("mean")
        P("")
        P("| 묶음(규칙 평균 뺀 수익) | 학습 겹침 · 단독 | 검증 겹침 · 단독 | 겹침 규칙 수 2↑ 학습 · 검증 |"); P("|---|---|---|---|")
        tr = S[S.date <= "20221231"]; va = S[S.date >= "20230101"]
        P("| 겹침 효과 | %+.2f (%d) · %+.2f | %+.2f (%d) · %+.2f | %+.2f (%d) · %+.2f (%d) |" % (
            tr[tr.ov >= 1].rr.mean(), (tr.ov >= 1).sum(), tr[tr.ov == 0].rr.mean(), va[va.ov >= 1].rr.mean(), (va.ov >= 1).sum(),
            va[va.ov == 0].rr.mean(), tr[tr.ov >= 2].rr.mean(), (tr.ov >= 2).sum(), va[va.ov >= 2].rr.mean(), (va.ov >= 2).sum()))
        P("")
    P("(%.0f분)" % ((time.time() - t0) / 60))
    (ROOT / "reports" / ("overlap_%s.md" % time.strftime("%Y%m%d"))).write_text("\n".join(OUT) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
