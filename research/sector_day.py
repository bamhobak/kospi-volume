# -*- coding: utf-8 -*-
"""국장 데이 — 핫한 섹터(테마) 안에서 거래량이 튀거나 외국인 매수 비중이 오른 종목, 다음날 시가 매수 → 종가 매도 (2026-10-08 사용자).
섹터 = 네이버 테마(data/sector.csv, 2026-08-28 한 번 찍은 구성 — ⚠ 지금 구성을 과거에 씌운다: 과거 편입 안 된 종목·사라진 종목은 빠진다 → 최근 2023~ 위주로 본다).
  이름 지정 섹터: 건설(건설 대표주·중소형·건설기계) · 우주항공(우주항공산업·항공기부품·UAM) · 방산(방위산업/전쟁) · 반도체(반도체 7개 테마) ·
                  조선(조선·조선기자재) · 원전(원자력발전) · 전력(전력설비·ESS·스마트그리드) · 로봇(로봇 3개)
  '핫한 섹터' (날마다 · 그날까지 정보로) = 테마 동일가중 20일 수익률 상위 10% 테마
종목 조건(신호일 t 종가까지 정보):
  V 거래량 튐: 그날 거래량 ≥ 20일 평균 3배 (2배 판도)
  F 외국인 매수 비율 오름: 외국인 순매수 ÷ 그날 거래대금 ≥ 5% 이고 20일 평균보다 높음 (flow11 2018~)
매매: t+1 시가 단일가 매수 → t+1 종가 단일가 매도 · 비용 0.23% · 견줌 = 같은 날 유니버스(거래대금 상위 40%) 시가→종가 평균
기간: 2018~22 / 2023~ (외국인 자료가 2018~).
    python research/sector_day.py
"""
import sqlite3, sys, time
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(BASE))
from verdict import log_trials
import oc_day as O
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))
COST = 0.23
NAMED = {"건설": ["건설 대표주", "건설 중소형", "건설기계"], "우주항공": ["우주항공산업(누리호/인공위성 등)", "항공기부품", "UAM(도심항공모빌리티)"],
         "방산": ["방위산업/전쟁 및 테러"], "조선": ["조선", "조선기자재"], "원전": ["원자력발전"],
         "전력": ["전력설비", "전력저장장치(ESS)", "스마트그리드(지능형전력망)"], "로봇": ["피지컬 AI/휴머노이드 로봇", "로봇(산업용/협동로봇 등)", "지능형로봇/인공지능(AI)"]}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    t0 = time.time()
    A, _ = O.build("KR")
    A = A[A.date >= "20170601"].sort_values(["ticker", "date"]).reset_index(drop=True)
    S = pd.read_csv(BASE / "data/sector.csv", dtype=str); S = S[S.kind == "theme"]
    NAMED["반도체"] = sorted({g for g in S.gname if "반도체" in g})
    g = A.groupby("ticker", sort=False)
    A["r1"] = (A.close / g.close.shift(1) - 1) * 100
    A["vmul"] = A.volume / g.volume.transform(lambda s: s.shift(1).rolling(20, min_periods=15).mean())
    A["amt"] = A.close * A.volume
    c = sqlite3.connect("file:" + str(BASE / "data" / "investor.db") + "?mode=ro", uri=True)
    F = pd.read_sql("SELECT ticker, date, frgn FROM flow11 WHERE date >= '20170601'", c)
    A = A.merge(F, on=["ticker", "date"], how="left")
    A["fr"] = A.frgn / A.amt.replace(0, np.nan) * 100
    A["fr20"] = A.groupby("ticker", sort=False).fr.transform(lambda s: s.shift(1).rolling(20, min_periods=10).mean())
    # 테마 지수(동일가중 하루 수익) → 20일 수익 → 날마다 상위 10%
    M = S[["gname", "ticker"]].merge(A[["ticker", "date", "r1"]], on="ticker")
    TI = M.groupby(["gname", "date"]).r1.mean().reset_index().sort_values(["gname", "date"])
    TI["r20"] = TI.groupby("gname").r1.transform(lambda s: ((1 + s / 100).rolling(20, min_periods=15).apply(np.prod, raw=True) - 1) * 100)
    TI["hot"] = TI.groupby("date").r20.rank(pct=True) >= 0.9
    hot = TI[TI.hot][["gname", "date"]]
    hotpair = hot.merge(S[["gname", "ticker"]], on="gname")[["ticker", "date"]].drop_duplicates()
    hotpair["inhot"] = True
    A = A.merge(hotpair, on=["ticker", "date"], how="left"); A["inhot"] = A.inhot.fillna(False).astype(bool)
    # 다음날 시가→종가
    A = A.sort_values(["ticker", "date"]).reset_index(drop=True)
    g = A.groupby("ticker", sort=False)
    A["n_oc"] = (g.close.shift(-1) / g.open.shift(-1) - 1) * 100
    A["n_date"] = g.date.shift(-1); A["n_uni"] = g.uni.shift(-1)
    A["n_gap"] = (g.open.shift(-1) / A.close - 1) * 100
    A = A[A.n_oc.notna() & (A.n_gap.abs() < 29)]
    bm = A[A.n_uni == True].groupby("n_date").n_oc.mean()
    A["ret"] = A.n_oc - COST; A["ex"] = A.n_oc - A.n_date.map(bm)
    V3, V2 = A.vmul >= 3, A.vmul >= 2
    Fx = (A.fr >= 5) & (A.fr > A.fr20)
    uni = A.uni
    P("# 국장 데이 — 핫한 섹터 × 거래량 튐 / 외국인 매수 비율 · %s" % time.strftime("%Y-%m-%d")); P("")
    P("- 신호일 다음날 시가 매수 → 그날 종가 매도 · 비용 %.2f%% · 초과 = 같은 날 유니버스 시가→종가 평균 대비 · 테마 구성은 2026-08-28 한 장(과거에 씌움)" % COST); P("")
    P("| 무리 | 조건 | 2018~22: 건수·평균·승률·초과 | 2023~: 건수·평균·승률·초과 | 해마다(18~26) |"); P("|---|---|---|---|---|")
    n = 0

    def row(grp, lab, m):
        nonlocal n
        Z = A[m.fillna(False) & uni]
        cells = []
        for a, b in (("20180101", "20221231"), ("20230101", "20991231")):
            z = Z[(Z.date >= a) & (Z.date <= b)]
            cells.append("%d건 %+.2f%% · %.0f%% · %+.2f" % (len(z), z.ret.mean(), (z.ret > 0).mean() * 100, z.ex.mean()) if len(z) >= 10 else "%d건" % len(z))
        yr = Z[Z.date >= "20180101"].groupby(Z.date.str[:4]).ret.mean()
        P("| %s | %s | %s | %s | %s |" % (grp, lab, cells[0], cells[1], " ".join("%+.1f" % v for v in yr.values))); n += 1

    for lab, m in (("아무 종목(견줌)", pd.Series(True, index=A.index)), ("거래량 3배↑", V3), ("거래량 2배↑", V2), ("외국인 매수 비율↑", Fx), ("거래량 2배↑ & 외국인↑", V2 & Fx)):
        row("핫한 섹터(20일 상위 10%)", lab, A.inhot & m)
    for lab, m in (("거래량 3배↑", V3), ("외국인 매수 비율↑", Fx)):
        row("핫한 섹터 밖(견줌)", lab, ~A.inhot & m)
    for sec, gl in NAMED.items():
        tk = set(S[S.gname.isin(gl)].ticker)
        ins = A.ticker.isin(tk)
        for lab, m in (("아무 날", pd.Series(True, index=A.index)), ("거래량 3배↑", V3), ("외국인 매수 비율↑", Fx), ("섹터 핫할 때 & 거래량 2배↑", A.inhot & V2), ("섹터 핫할 때 & 외국인↑", A.inhot & Fx)):
            row("[%s] %d종목" % (sec, len(tk)), lab, ins & m)
    # 장중 흐름(sector_day_m1.py)용 — 신호와 다음날 날짜를 남긴다
    keep = A[uni & (A.n_date >= "20221201")].copy()
    keep["V2"], keep["V3"], keep["F"] = V2[keep.index], V3[keep.index], Fx[keep.index]
    for sec, gl in NAMED.items(): keep["S_" + sec] = keep.ticker.isin(set(S[S.gname.isin(gl)].ticker))
    keep[["ticker", "n_date", "inhot", "V2", "V3", "F"] + ["S_" + k for k in NAMED]].to_pickle(ROOT / "cache" / "sector_day_sig.pkl")
    P(""); P("(칸 %d · %.1f분)" % (n, (time.time() - t0) / 60))
    log_trials("sector_day_%s" % time.strftime("%Y%m%d"), n)
    (ROOT / "reports" / ("sector_day_%s.md" % time.strftime("%Y%m%d"))).write_text("\n".join(OUT) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
