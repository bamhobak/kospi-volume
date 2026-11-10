# -*- coding: utf-8 -*-
"""[갭 하락 조용주] 계열 실전(1주, 10-07~) 성적이 연구 기대(건당 +0.9% 안팎)보다 낮은 이유 쪼개기(2026-11-10 사용자 "둘 다 봐줘").
  (a) 같은 날 연구 정의 T1(실제 KRX 시가 갭 · 지금 그물: 크기 liq ≤ 4/9(11-03~ 2/3) · 갭 순위 ≤ 40% · 어제 거래량 순위 ≤ 30% · 시장 대비 ≤ -1.5)이
      KRX 시가→KRX 종가로 벌었을 몫 — 시장 국면 탓인지
  (b) 실전 체결 중 연구 정의에 안 드는 것(장전 예상 갭 오차·어제 종가 기준 차이)의 몫 · 놓친 진짜 후보
  (c) 규칙별(T1 본체·T2·T3·T4) · (d) 매수가 vs KRX 시가 · 매도가 vs KRX 종가 · (e) 기간·요일·폭락일 몰림
자료: data/day/ledger.json(실전) · data/m1/KR/day(KRX 시가 = 09:01 봉 시가, KRX 종가 = 마지막 봉 종가 — 11-04 삼성 218,000 확인) ·
      data/y1_hist.pkl(유니버스·크기·어제 거래량 순위, 11-04 까지 — 그 뒤 날은 유니버스를 11-04 로 이어 쓰고 거래량 조건은 안 봄)
⚠ 10-30 까지 실전 morning 은 어제 종가를 토스(NXT 20:00 통합) 값으로 썼다 — 11-02 부터 KRX 종가(krx_closes).
    python research/t1_live_gap_1110.py
"""
import json, sys, datetime as dt
from pathlib import Path
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd

COST = 0.23
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))


def krx_days():
    rows = []
    for f in sorted((BASE / "data" / "m1" / "KR" / "day").glob("*.parquet")):
        d = f.stem
        D = pd.read_parquet(f, columns=["t", "ts", "o", "c", "v"])
        D = D[D.v > 0]
        hm = pd.to_datetime(D.ts, unit="s", utc=True).dt.tz_convert("Asia/Seoul").dt.strftime("%H%M")
        D = D.assign(hm=hm.values)
        D = D[(D.hm >= "0901") & (D.hm <= "1531")].sort_values(["t", "ts"])
        g = D.groupby("t")
        first = g.first(); last = g.last()
        X = pd.DataFrame({"oK": first.o, "hm0": first.hm, "cK": last.c}); X["date"] = d
        rows.append(X.reset_index().rename(columns={"index": "t"}))
    K = pd.concat(rows, ignore_index=True)
    K = K[K.hm0 <= "0905"]                                                # 09:05 넘어 첫 체결 = 거래정지·VI 늦은 시가 — 시가로 안 씀
    K = K.sort_values(["t", "date"]); K["pcK"] = K.groupby("t").cK.shift(1); K["pdate"] = K.groupby("t").date.shift(1)
    return K


def main():
    K = krx_days()
    days = sorted(K.date.unique()); prev = dict(zip(days[1:], days[:-1]))
    K = K[K.pdate == K.date.map(prev)]                                    # 바로 전 거래일 종가가 있는 줄만
    H = pd.read_pickle(BASE / "data" / "y1_hist.pkl")[["ticker", "date", "liq", "q_vm", "rgap", "q_gap", "gap"]]
    H = H[H.date >= "20261001"]
    last = H.date.max()
    rows = []
    for d in days:
        if d < "20261007": continue
        h = H[H.date == d] if d <= last else H[H.date == last].assign(date=d, q_vm=np.nan, rgap=np.nan, q_gap=np.nan, gap=np.nan)
        if h.empty: continue
        k = K[K.date == d].rename(columns={"t": "ticker"})
        z = h.merge(k[["ticker", "oK", "cK", "pcK"]], on="ticker", how="inner")
        z = z[z.pcK >= 1000]
        z["gK"] = (z.oK / z.pcK - 1) * 100
        z = z[z.gK.abs() < 30]
        z["mgK"] = z.gK.median(); z["relK"] = z.gK - z.mgK; z["qgK"] = z.gK.rank(pct=True)
        z["retK"] = (z.cK / z.oK - 1) * 100 - COST
        rows.append(z)
    U = pd.concat(rows, ignore_index=True)
    L = np.where(U.date >= "20261103", 2 / 3, 4 / 9)
    vmok = (U.q_vm.fillna(0) <= 0.30)                                      # 11-05~ 은 거래량 조건 모름(통과로 둠)
    U["pick"] = (U.liq <= L) & (U.qgK <= 0.40) & vmok & (U.relK <= -1.5)
    U["pick_int"] = (U.liq <= L) & (U.q_gap <= 0.40) & vmok & (U.rgap <= -1.5)   # 어제 종가 = 통합(fdr/네이버, 09-14~ NXT) 기준 — 11-04 까지만
    # ── 실전 체결 ──
    Lg = json.load(open(BASE / "data" / "day" / "ledger.json", encoding="utf-8"))["orders"]
    buys = [o for o in Lg if o.get("side") == "BUY" and o.get("rid", "T1") in ("T1", "T2", "T3", "T4") and (o.get("fq") or 0) > 0 and o.get("date", "") >= "20261007"]
    sells = [o for o in Lg if o.get("side") == "SELL" and (o.get("fq") or 0) > 0]
    by_pos = {}
    for s in sells:
        if s.get("posId"): by_pos.setdefault(s["posId"], []).append(s)
    T = []
    for b in buys:
        pid = (b.get("pos") or {}).get("id")
        ss = by_pos.get(pid) or [s for s in sells if s["t"] == b["t"] and s.get("date", "") >= b["date"] and s.get("rid", "T1") == b.get("rid", "T1")][:1]
        if not ss: continue
        q = sum(float(s["fq"]) for s in ss); sap = sum(float(s["fq"]) * float(s["ap"]) for s in ss) / q
        T.append(dict(date=b["date"], ticker=b["t"], name=b.get("name"), rid=b.get("rid", "T1"), bap=float(b["ap"]), sap=sap, sdate=min(s["date"] for s in ss),
                      intra=bool(b.get("intraday")), lim=b.get("lim"), pc_live=b.get("pc")))
    T = pd.DataFrame(T)
    T["ret"] = (T.sap / T.bap - 1) * 100 - COST
    T = T.merge(U[["ticker", "date", "oK", "cK", "pcK", "mgK", "relK", "qgK", "q_vm", "liq", "pick", "pick_int", "retK", "rgap"]], on=["ticker", "date"], how="left")
    T["bslip"] = (T.bap / T.oK - 1) * 100; T["sslip"] = (T.sap / T.cK - 1) * 100
    T.loc[T.sdate != T.date, "sslip"] = np.nan
    f = lambda z: "%d건 · %+.2f%% · 승 %.0f%% · 중앙 %+.2f" % (len(z), z.mean(), (z > 0).mean() * 100, z.median()) if len(z) else "0건"
    P("실전 [갭 하락 조용주] 계열 체결 %d건(매도까지 맺힌 것) · %s~%s · 건당(비용 뒤) %s" % (len(T), T.date.min(), T.date.max(), f(T.ret)))
    P("KRX 시가·종가 붙은 것 %d건\n" % T.oK.notna().sum())
    P("## (a) 같은 날 연구 정의 T1 (실제 KRX 시가 갭, KRX 시가→종가, 비용 뒤)\n")
    R = U[U.pick]
    P("| 구간 | 연구 T1 건당(종목 평균) | 날 바구니 평균 | 날 수 | 실전 건당 |"); P("|---|---|---|---|---|")
    for nm, lo, hi in (("10-07~10-30 (어제 종가 = 토스 통합)", "20261007", "20261030"), ("11-02~11-10 (어제 종가 = KRX)", "20261102", "20261110"), ("전체", "20261007", "20261110")):
        r = R[(R.date >= lo) & (R.date <= hi)]; t = T[(T.date >= lo) & (T.date <= hi)]
        P("| %s | %s | %+.2f%% | %d | %s |" % (nm, f(r.retK), r.groupby("date").retK.mean().mean() if len(r) else np.nan, r.date.nunique(), f(t.ret)))
    ri = U[U.pick_int & (U.date <= last)]
    P("\n어제 종가를 통합(NXT 20:00) 값으로 쟀다면(11-04 까지): %s · KRX 기준 같은 기간 %s · 두 정의 겹침 %d건" % (
        f(ri.retK), f(R[R.date <= last].retK), len(set(zip(ri.ticker, ri.date)) & set(zip(R[R.date <= last].ticker, R[R.date <= last].date)))))
    P("\n## (b) 실전 체결이 연구 정의에 드나\n")
    P("| 구분 | 실전 체결 손익 | 같은 종목 KRX 시가→종가 |"); P("|---|---|---|")
    for nm, m in (("연구 T1 에 듦", T.pick == True), ("안 듦 — 실제 시장 대비 > -1.5", (T.pick != True) & (T.relK > -1.5)),
                  ("안 듦 — 시장 대비는 됐는데 갭·거래량·크기 조건 밖", (T.pick != True) & (T.relK <= -1.5)), ("KRX 자료 없음", T.relK.isna())):
        z = T[m]; P("| %s | %s | %s |" % (nm, f(z.ret), f(z.retK.dropna())))
    # 왜 시장 대비 > -1.5 인데 지정가에 사졌나 — 지정가 = 실전 어제 종가 × (1 + 장전 예상 시장 갭 − 1.5%p)
    mg = {}
    for d in T.date.unique():
        try: mg[d] = json.load(open(BASE / "data" / "day" / ("snap_%s.json" % d), encoding="utf-8")).get("mgap")
        except Exception: mg[d] = None
    Z = T.dropna(subset=["oK", "pcK", "lim", "pc_live"]).copy()
    Z["mg_exp"] = Z.date.map(mg).astype(float)
    Z["pc_diff"] = (Z.pc_live.astype(float) / Z.pcK - 1) * 100                 # 실전 어제 종가 − KRX 종가
    Z["mg_err"] = Z.mg_exp - Z.mgK                                              # 장전 예상 시장 갭 − 실제
    Z["thrK"] = (Z.lim.astype(float) / Z.pcK - 1) * 100 - Z.mgK                 # 이 지정가가 실제로 뜻한 '시장 대비' 문턱
    bad = Z[(Z.pick != True) & (Z.relK > -1.5)]
    P()
    P("시장 대비 > -1.5 인데 사진 %d건 — 지정가가 실제로 뜻한 문턱 중앙 %+.2f%%p(목표 -1.5) · 실전 어제 종가가 KRX 종가보다 중앙 %+.2f%%(10월 %+.2f · 11월 %+.2f) · 장전 예상 시장 갭 오차 중앙 %+.2f%%p" % (
        len(bad), bad.thrK.median(), bad.pc_diff.median(), bad[bad.date < "20261101"].pc_diff.median(), bad[bad.date >= "20261101"].pc_diff.median(), bad.mg_err.median()))
    for nm, lo, hi in (("10월(토스 통합 종가)", "20261007", "20261030"), ("11월(KRX 종가)", "20261102", "20261110")):
        z = Z[(Z.date >= lo) & (Z.date <= hi)]
        P("· %s: 체결 %d · 그중 실제 시장 대비 > -1.5 %.0f%% · 실전 어제 종가−KRX 종가 |중앙| %.2f%% · 지정가 실제 문턱 중앙 %+.2f%%p" % (
            nm, len(z), (z.relK > -1.5).mean() * 100, z.pc_diff.abs().median(), z.thrK.median()))
    keys = set(zip(T.ticker, T.date))
    miss = R[[(a, b) not in keys for a, b in zip(R.ticker, R.date)]]
    P("\n연구 T1 이었는데 실전에서 안 산 것: %s (전체 연구 T1 %d건 중)" % (f(miss.retK), len(R)))
    P("\n## (c) 규칙별 실전\n")
    for rid, z in T.groupby("rid"): P("· %s: %s · 연구 T1 에 든 비율 %.0f%%" % (rid, f(z.ret), (z.pick == True).mean() * 100))
    P("\n## (d) 체결가\n")
    z = T.dropna(subset=["bslip"])
    P("· 매수가 vs KRX 시가: 중앙 %+.2f%% · 평균 %+.2f%% · 시가보다 1%%↑ 싸게 산 것(장중 체결) %d건 · 장중 표시 %d건" % (z.bslip.median(), z.bslip.mean(), (z.bslip < -1).sum(), T.intra.sum()))
    z2 = T.dropna(subset=["sslip"])
    P("· 매도가 vs KRX 종가(같은 날 판 것): 중앙 %+.2f%% · 평균 %+.2f%% · 1%%↑ 차이 %d건" % (z2.sslip.median(), z2.sslip.mean(), (z2.sslip.abs() > 1).sum()))
    P("· 다음 날 이후 판 것(이월) %d건: %s" % ((T.sdate != T.date).sum(), f(T[T.sdate != T.date].ret)))
    P("· 실전 손익 − 같은 종목 KRX 시가→종가 = 평균 %+.2f%%p (체결가 몫)" % (T.ret - T.retK).mean())
    P("\n## (e) 날짜별(실전 건당 · 연구 T1 건당)\n")
    a = T.groupby("date").ret.agg(["count", "mean"]); b = R.groupby("date").retK.agg(["count", "mean"])
    m = U.groupby("date").gK.median()
    D = a.join(b, how="outer", lsuffix="_실전", rsuffix="_연구").join(m.rename("시장갭"))
    P("| 날 | 실전 건 | 실전 건당 | 연구 건 | 연구 건당 | 시장 갭 |"); P("|---|---|---|---|---|---|")
    for d, r in D.iterrows():
        P("| %s | %s | %s | %s | %s | %+.1f |" % (d[4:], "" if pd.isna(r.count_실전) else int(r.count_실전), "" if pd.isna(r.mean_실전) else "%+.2f" % r.mean_실전,
          "" if pd.isna(r.count_연구) else int(r.count_연구), "" if pd.isna(r.mean_연구) else "%+.2f" % r.mean_연구, r.시장갭 if r.시장갭 == r.시장갭 else 0))
    T.to_pickle(BASE / "data" / "day" / "t1_live_gap_1110.pkl")
    (ROOT / "t1_live_gap_1110.out").write_text("\n".join(OUT), encoding="utf-8")


if __name__ == "__main__":
    main()
