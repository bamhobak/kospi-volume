# -*- coding: utf-8 -*-
"""장중 대형주·ETF 아이디어 실측 (2026-10-25 사용자 "위 중에 테스트 해볼수 있는거 해보자").

자료: research/cache/m1_daysum.parquet(m1_daysum.py — 1분봉 2022-12~ 종목·날짜 요약) · kr_scan(업종·갭 — 전이표 짝 찾기용)
  ① 장 마감 레버리지 재조정  — KODEX200(069500) 14:30 까지 전날 종가 대비 ±θ 면 그 방향으로 14:30(15:00) → 종가.
                               내린 날 방향은 인버스 ETF 대신 KODEX200 반대 수익으로 근사(인버스 1분봉 없음). 비용 0.05%.
  ③ 전이 잔차 장중 수렴(대형주) — 공장 전이표(transfer.fit_year — 해마다 지난 2년 kr_scan 갭으로 짝·베타, 미래 안 봄)
                               예상 갭보다 더 빠져 열린 대형주를 시가(09:05) 매수 → 종가.
  ④ 대형주 짝 장중 수렴     — 2023 일간 수익 상관 상위 20쌍(대형 80종목 안). 10:00(11:00) 까지 전날 종가 대비 벌어짐이
                               지난 60일 같은 벌어짐의 z ≥ 2 면 뒤처진 쪽을 그 시각 매수 → 종가.
  ⑤ 업종 대비 시가 괴리      — 대형주 시가 갭이 같은 업종(KSIC up) 다른 대형주 평균 갭보다 θ%p 더 빠짐 → 시가(09:05) 매수 → 종가.
  ⑦ 오전 주문 쏠림          — 09:01~10:00 (오른 봉 거래량 - 내린 봉 거래량)/전체 ≥ +θ → 10:00 매수 → 종가.
                               대조 = 같은 날 같은 첫 1시간 수익 3분위의 대형주 평균(가격 돌파와 분리).
대형주 = 그날 전 20일 평균 거래대금 상위 100(kr_scan 에 있는 종목만 — ETF 제외). 주식 비용 왕복 0.23%(2026 매도세 0.20 + 수수료).
구간: 학습 2022-12~2024 / 검증 2025~ (T1 과 같은 나눔). 칸 = 비용 뒤 평균 %(승률 · 건수).
    python research/intraday_ideas.py
"""
import sys, time
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(BASE)); sys.path.insert(0, str(ROOT / "factory"))
from verdict import log_trials
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))
CK, CE = 0.23, 0.05
TR, VA = ("20221201", "20241231"), ("20250101", "20991231")
NCELL = [0]


def fit_year_safe(T, U, Y, NR):
    """transfer.fit_year 와 같은 계산 — 상관이 전부 빈 종목에서 idxmax 가 NaN 을 내 멈추는 것만 건너뛴다(공장 코드는 그대로 둔다)."""
    a, b = "%d0101" % (Y - 2), "%d1231" % (Y - 1)
    Z = U[(U.date >= a) & (U.date <= b)][["ticker", "date", "gap"]]
    if Z.empty: return {}
    G = Z.pivot(index="date", columns="ticker", values="gap")
    X = NR.reindex(G.index)[T.US].astype(float)
    ok = X.notna().sum() >= 200
    X = X.loc[:, ok[ok].index]
    if X.shape[1] == 0: return {}
    out = {}
    Xm = X - X.mean()
    for t in G.columns:
        y = G[t]; m = y.notna()
        if m.sum() < 120: continue
        yy = y[m] - y[m].mean(); XX = Xm[m].fillna(0)
        cov = (XX.mul(yy, axis=0)).sum() / (m.sum() - 1)
        var = (XX ** 2).sum() / (m.sum() - 1)
        corr = (cov / np.sqrt(var * yy.var())).dropna()
        if corr.empty: continue
        j = corr.idxmax()
        if not np.isfinite(corr[j]) or corr[j] <= 0.05: continue
        out[t] = (j, float(cov[j] / var[j]), float(corr[j]))
    return out


def cell(x, cost):
    x = pd.Series(x).dropna() - cost
    if len(x) < 15:
        return "%d건" % len(x)
    t = x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))
    return "%+.3f (%d%% · %d · t%.1f)" % (x.mean(), (x > 0).mean() * 100, len(x), t)


def row(lab, df, col, cost, ctrl=None):
    """df: d·col(수익 %) — 학습/검증 칸, ctrl 은 같은 잣대 대조열(그날 평균) 이 있으면 초과도"""
    NCELL[0] += 1
    a = df[(df.d >= TR[0]) & (df.d <= TR[1])]; b = df[df.d >= VA[0]]
    s = "| %s | %s | %s |" % (lab, cell(a[col], cost), cell(b[col], cost))
    if ctrl:
        s += " %s | %s |" % (("%+.3f" % (a[col] - a[ctrl]).mean()) if len(a) else "—", ("%+.3f" % (b[col] - b[ctrl]).mean()) if len(b) else "—")
    P(s)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    t0 = time.time()
    D = pd.read_parquet(ROOT / "cache" / "m1_daysum.parquet")
    D = D[D.d >= "20221201"].copy()
    for c in ("o", "c", "pc", "p0905", "p1000", "p1100", "p1430", "p1500", "p1520"):
        D[c] = D[c].astype(float)
    D["gap"] = (D.o / D.pc - 1) * 100
    D = D[D.pc.notna() & (D.nb >= 300)]
    K = pd.read_pickle(BASE / "data/kr_scan.pkl")[["ticker", "date", "up", "gap"]]
    stocks = set(K.ticker.unique())
    UP = K.dropna(subset=["up"]).sort_values("date").drop_duplicates("ticker", keep="last").set_index("ticker").up

    # ───────── ① 장 마감 레버리지 재조정 (KODEX200) ─────────
    E = D[D.t == "069500"].copy()
    E["r1430"] = (E.p1430 / E.pc - 1) * 100
    E["r1500"] = (E.p1500 / E.pc - 1) * 100
    P("# 장중 대형주·ETF 아이디어 실측 · %s" % time.strftime("%Y-%m-%d")); P("")
    P("- 칸 = 비용 뒤 평균 수익 %(승률 · 건수 · t) · 학습 2022-12~2024 / 검증 2025~ · 대조 칸 = 같은 날 대조 대비 차이(비용 전)"); P("")
    P("## ① 장 마감 레버리지 재조정 — KODEX200, 14:30(15:00) 지수 방향으로 → 종가 (비용 0.05%)"); P("")
    P("| 조건 | 학습 | 검증 |"); P("|---|---|---|")
    E["x1430"] = (E.c / E.p1430 - 1) * 100
    E["x1500"] = (E.c / E.p1500 - 1) * 100
    E["x1430b"] = (E.p1520 / E.p1430 - 1) * 100          # 동시호가 빼고 15:20 까지
    row("아무 날 · 14:30 매수 → 종가(대조, 비용 0)", E, "x1430", 0)
    for th in (0.7, 1.0, 1.5):
        for ent, col, rc in (("14:30", "x1430", "r1430"), ("15:00", "x1500", "r1500")):
            up, dn = E[E[rc] >= th], E[E[rc] <= -th]
            both = pd.concat([up.assign(z=up[col]), dn.assign(z=-dn[col])])
            row("±%.1f%% · %s 방향 → 종가 (오른 날 %d·내린 날 %d)" % (th, ent, len(up), len(dn)), both, "z", CE)
            row("　└ 오른 날만 매수", up, col, CE)
            row("　└ 내린 날만 인버스(반대 수익)", dn.assign(z=-dn[col]), "z", CE)
        up = E[E.r1430 >= th]; dn = E[E.r1430 <= -th]
        row("±%.1f%% · 14:30 → 15:20(동시호가 뺌)" % th, pd.concat([up.assign(z=up.x1430b), dn.assign(z=-dn.x1430b)]), "z", CE)
    P("")

    # ───────── 대형주 유니버스 ─────────
    S = D[D.t.isin(stocks)].sort_values(["t", "d"]).copy()
    S["v20"] = S.groupby("t").val.transform(lambda s: s.shift(1).rolling(20, min_periods=15).mean())
    S["vr"] = S.groupby("d").v20.rank(ascending=False)
    S = S[S.vr <= 100].copy()
    S["oc"] = (S.c / S.o - 1) * 100
    S["o5c"] = (S.c / S.p0905 - 1) * 100
    S["x10"] = (S.c / S.p1000 - 1) * 100
    S["x11"] = (S.c / S.p1100 - 1) * 100
    for c_ in ("oc", "o5c", "x10", "x11"):
        S["m_" + c_] = S.groupby("d")[c_].transform("mean")
    P("대형주 %d종목·%d일 · 대조(대형주 아무 날, 비용 뒤): 시가→종가 %s · 10:00→종가 %s" % (S.t.nunique(), S.d.nunique(),
      cell(S.oc, CK), cell(S.x10, CK))); P("")

    # ───────── ③ 전이 잔차 장중 수렴 ─────────
    import transfer as T
    U = K[(K.date >= "20140101")].dropna(subset=["gap"])[["ticker", "date", "gap"]].copy()
    NR = T.night_returns(sorted(set(U.date) | set(S.d)))
    fits = {Y: fit_year_safe(T, U, Y, NR) for Y in range(2023, 2027)}
    U2 = S[["t", "d", "gap"]].rename(columns={"t": "ticker", "d": "date"}).reset_index()
    T.apply_fit(U2, fits, NR)
    S["tr_res"] = U2.set_index("index").tr_res.astype(float)
    P("## ③ 전이 잔차 — 예상 갭(밤사이 짝 미장 × 베타)보다 더 빠져 열린 대형주 → 종가 (짝 있는 행 %d)" % S.tr_res.notna().sum()); P("")
    P("| 조건 | 학습 | 검증 | 초과 학습 | 초과 검증 |"); P("|---|---|---|---|---|")
    for th in (-1.0, -2.0, -3.0):
        z = S[S.tr_res <= th]
        row("잔차 ≤ %.0f%%p · 시가 매수" % th, z, "oc", CK, "m_oc")
        row("잔차 ≤ %.0f%%p · 09:05 매수" % th, z, "o5c", CK, "m_o5c")
    z = S[S.tr_res >= 2.0]
    row("(반대) 잔차 ≥ +2%%p · 시가 매수", z, "oc", CK, "m_oc")
    P("")

    # ───────── ④ 대형주 짝 장중 수렴 ─────────
    top80 = S[(S.d >= "20230101") & (S.d <= "20231231")].groupby("t").val.mean().nlargest(80).index
    R = S[S.t.isin(top80) & (S.d <= "20231231")].assign(r=lambda x: (x.c / x.pc - 1) * 100).pivot(index="d", columns="t", values="r")
    C_ = R.corr(min_periods=150)
    pr = [(a, b, C_.loc[a, b]) for i, a in enumerate(C_.columns) for b in C_.columns[i + 1:] if np.isfinite(C_.loc[a, b])]
    pr = sorted(pr, key=lambda x: -x[2])[:20]
    P("## ④ 대형주 짝 장중 수렴 — 2023 상관 상위 20쌍, 벌어짐 z(지난 60일) ≥ θ 면 뒤처진 쪽 매수 → 종가"); P("")
    P("짝: " + " · ".join("%s-%s(%.2f)" % (a, b, c) for a, b, c in pr)); P("")
    W = S.set_index(["d", "t"])
    trades = {k: [] for k in ("10", "11")}
    for a, b, _ in pr:
        for hh, pcol, xcol in (("10", "p1000", "x10"), ("11", "p1100", "x11")):
            Q = pd.DataFrame({"ra": (W.xs(a, level="t")[pcol] / W.xs(a, level="t").pc - 1) * 100,
                              "rb": (W.xs(b, level="t")[pcol] / W.xs(b, level="t").pc - 1) * 100,
                              "xa": W.xs(a, level="t")[xcol], "xb": W.xs(b, level="t")[xcol]}).dropna().sort_index()
            Q["s"] = Q.ra - Q.rb
            Q["mu"] = Q.s.shift(1).rolling(60, min_periods=40).mean(); Q["sd"] = Q.s.shift(1).rolling(60, min_periods=40).std()
            Q["z"] = (Q.s - Q.mu) / Q.sd
            Q["lag"] = np.where(Q.s < Q.mu, Q.xa, Q.xb)        # 뒤처진 쪽의 그 시각 → 종가
            Q["lead"] = np.where(Q.s < Q.mu, Q.xb, Q.xa)
            Q["pair"] = a + "-" + b
            trades[hh].append(Q.reset_index().rename(columns={"index": "d"}))
    P("| 조건 | 학습 | 검증 | 뒤처진-앞선 학습 | 뒤처진-앞선 검증 |"); P("|---|---|---|---|---|")
    for hh in ("10", "11"):
        Z = pd.concat(trades[hh], ignore_index=True)
        for th in (1.5, 2.0, 2.5, 3.0):
            row("%s:00 · |z| ≥ %.1f · 뒤처진 쪽 매수" % (hh, th), Z[Z.z.abs() >= th], "lag", CK, "lead")
        row("%s:00 · 아무 날 뒤처진 쪽(대조)" % hh, Z, "lag", CK, "lead")
    P("")

    # ───────── ⑤ 업종 대비 시가 괴리 ─────────
    S["up"] = S.t.map(UP)
    g = S.groupby(["d", "up"]).gap
    S["n_up"] = g.transform("size"); S["s_up"] = g.transform("sum")
    S["rel"] = np.where(S.n_up >= 3, S.gap - (S.s_up - S.gap) / (S.n_up - 1), np.nan)
    P("## ⑤ 업종 대비 시가 괴리 — 같은 업종(KSIC) 다른 대형주 평균 갭보다 더 빠져 열림 (업종 3종목↑ 행 %d)" % S.rel.notna().sum()); P("")
    P("| 조건 | 학습 | 검증 | 초과 학습 | 초과 검증 |"); P("|---|---|---|---|---|")
    for th in (-1.5, -2.0, -3.0):
        z = S[S.rel <= th]
        row("업종보다 %.1f%%p↑ 더 빠짐 · 시가 매수" % -th, z, "oc", CK, "m_oc")
        row("업종보다 %.1f%%p↑ 더 빠짐 · 09:05 매수" % -th, z, "o5c", CK, "m_o5c")
    z = S[(S.rel <= -2.0) & (S.tr_res <= -1.0)]
    row("업종 -2%p & 전이 잔차 -1%p 둘 다", z, "oc", CK, "m_oc")
    P("")

    # ───────── ⑦ 오전 주문 쏠림 ─────────
    S["imb"] = (S.uv1.fillna(0) - S.dv1.fillna(0)) / S.tv1.replace(0, np.nan)
    S["r1h"] = (S.p1000 / S.o - 1) * 100
    S["q1h"] = S.groupby("d").r1h.transform(lambda s: pd.qcut(s.rank(method="first"), 3, labels=False) if s.notna().sum() >= 9 else np.nan)
    S["m_q"] = S.groupby(["d", "q1h"]).x10.transform("mean")
    P("## ⑦ 오전 주문 쏠림 — 09:01~10:00 (오른 봉 거래량 - 내린 봉)/전체 · 10:00 매수 → 종가 · 대조 = 같은 날 같은 첫 1시간 수익 3분위"); P("")
    P("| 조건 | 학습 | 검증 | 초과 학습 | 초과 검증 |"); P("|---|---|---|---|---|")
    for th in (0.2, 0.3, 0.4):
        row("쏠림 ≥ +%.1f (사는 쪽)" % th, S[S.imb >= th], "x10", CK, "m_q")
    row("쏠림 ≤ -0.3 (파는 쪽 — 참고)", S[S.imb <= -0.3], "x10", CK, "m_q")
    row("쏠림 ≥ +0.3 & 첫 1시간 수익 하위 3분위(덜 오름)", S[(S.imb >= 0.3) & (S.q1h == 0)], "x10", CK, "m_q")
    P("")
    P("(1분봉 끝 %s · 칸 %d · %.1f분)" % (D.d.max(), NCELL[0], (time.time() - t0) / 60))
    log_trials("intraday_ideas_%s" % time.strftime("%Y%m%d"), NCELL[0])
    (ROOT / "reports" / ("intraday_ideas_%s.md" % time.strftime("%Y%m%d"))).write_text("\n".join(OUT) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
