# -*- coding: utf-8 -*-
"""핫한 섹터 — 사장님 대화 반영 (2026-10-08, H0309·H0310 후속):
  "거래량이 튄다고 무조건 오르는 건 아니니까 튀면서 올라가는 것들을 체크" → 거래량 늘면서 상승
  "장초반에 바로 갭으로 올라가는 것들도 있고" → 다음날 시가 갭 상승
  "섹터별로 대장주 2등주 이렇게도 나뉘고" → 테마 안 시가총액 1위·2위 / 그날 거래대금 1위
신호일 t 종가까지 정보(갭만 t+1 시가 — 시가 단일가에 사는 것으로 가정, 실제론 예상체결가로 걸러야 함).
  튀면서 오름 VU  = 거래량 ≥ 20일 평균 2배 & 그날 +3%↑ & 고가 근처 마감(위 30%)
  세게 튀며 오름 VU5 = 거래량 3배↑ & +5%↑ & 고가 근처
  튀는데 내림 VD  = 거래량 2배↑ & 그날 하락 마감 (견줌)
  갭 G2 / G4      = 다음날 시가 ≥ 전일 종가 +2% / +4% (29% 미만)
  대장 L1 / 2등 L2 = 핫한 테마(20일 상위 10%) 안 그날 시가총액 순위 1 / 2 (여러 테마면 가장 높은 순위) · 거래대금 1위 A1
매매: 데이 = t+1 시가 → t+1 종가(비용 0.23) · 스윙 = t+1 시가 → t+h 종가(패널 n{h}, 비용 0.58~1.38 반영)
초과 = 같은 날 유니버스(거래대금 상위 40%) 같은 매매 평균 대비. 테마 구성 = 2026-08-28 한 장(과거에 씌움).
    python research/sector_leader.py
"""
import sqlite3, sys, time
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(BASE))
from verdict import log_trials
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))
HS = (5, 20, 60)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    t0 = time.time()
    A = pd.read_pickle(BASE / "data/kr_scan.pkl")
    A = A[A.date >= "20170601"][["ticker", "date", "open", "high", "low", "close", "volume", "amt20", "marcap"] + [f"n{h}" for h in HS]].copy()
    A = A.sort_values(["ticker", "date"]).reset_index(drop=True)
    g = A.groupby("ticker", sort=False)
    A["r1"] = (A.close / g.close.shift(1) - 1) * 100
    A["clv"] = (A.close - A.low) / (A.high - A.low).replace(0, np.nan)
    A["vmul"] = A.volume / g.volume.transform(lambda s: s.shift(1).rolling(20, min_periods=15).mean())
    A["ngap"] = (g.open.shift(-1) / A.close - 1) * 100
    A["noc"] = (g.close.shift(-1) / g.open.shift(-1) - 1) * 100
    A["amt"] = A.close * A.volume
    A = A[(A.r1.abs().fillna(0) < 31) & (A.ngap.abs().fillna(0) < 29)]
    A["uni"] = A.groupby("date").amt20.rank(pct=True) >= 0.6
    c = sqlite3.connect("file:" + str(BASE / "data" / "investor.db") + "?mode=ro", uri=True)
    F = pd.read_sql("SELECT ticker, date, frgn FROM flow11 WHERE date >= '20170601'", c)
    A = A.merge(F, on=["ticker", "date"], how="left")
    A["fr"] = A.frgn / A.amt.replace(0, np.nan) * 100
    A = A.sort_values(["ticker", "date"]).reset_index(drop=True)
    A["fr20"] = A.groupby("ticker", sort=False).fr.transform(lambda s: s.shift(1).rolling(20, min_periods=10).mean())
    # 테마 지수 → 핫한 테마 → 그 안 순위
    S = pd.read_csv(BASE / "data/sector.csv", dtype=str); S = S[S.kind == "theme"][["gname", "ticker"]].drop_duplicates()
    M = S.merge(A[["ticker", "date", "r1", "marcap", "amt"]], on="ticker")
    TI = M.groupby(["gname", "date"]).r1.mean().reset_index().sort_values(["gname", "date"])
    TI["r20"] = TI.groupby("gname").r1.transform(lambda s: ((1 + s / 100).rolling(20, min_periods=15).apply(np.prod, raw=True) - 1) * 100)
    TI["hot"] = TI.groupby("date").r20.rank(pct=True) >= 0.9
    H = M.merge(TI[TI.hot][["gname", "date"]], on=["gname", "date"])
    H["mrank"] = H.groupby(["gname", "date"]).marcap.rank(ascending=False, method="first")
    H["arank"] = H.groupby(["gname", "date"]).amt.rank(ascending=False, method="first")
    R = H.groupby(["ticker", "date"]).agg(mrank=("mrank", "min"), arank=("arank", "min")).reset_index()
    A = A.merge(R, on=["ticker", "date"], how="left")
    A = A[(A.date >= "20180101") & A.ngap.notna()].reset_index(drop=True)
    A["inhot"] = A.mrank.notna()
    A["dayr"] = A.noc - 0.23
    bm_day = A[A.uni].groupby("date").noc.mean()
    A["dayx"] = A.noc - A.date.map(bm_day)
    BM = {h: A[A.uni].groupby("date")[f"n{h}"].mean() for h in HS}
    di = {d: i for i, d in enumerate(sorted(A.date.unique()))}; A["di"] = A.date.map(di)

    VU = (A.vmul >= 2) & (A.r1 >= 3) & (A.clv >= 0.7)
    VU5 = (A.vmul >= 3) & (A.r1 >= 5) & (A.clv >= 0.7)
    VD = (A.vmul >= 2) & (A.r1 < 0)
    G2, G4 = A.ngap >= 2, A.ngap >= 4
    L1, L2, L3 = A.mrank == 1, A.mrank == 2, A.mrank >= 3
    A1 = A.arank == 1
    Fx = (A.fr >= 5) & (A.fr > A.fr20)
    hot = A.inhot

    def swing(m, h):
        Z = A[m & A.uni & A[f"n{h}"].notna()].sort_values("di")
        keep, last = [], {}
        for t, i, ix in zip(Z.ticker.values, Z.di.values, Z.index):
            if last.get(t, -10 ** 9) >= i: continue
            last[t] = i + h; keep.append(ix)
        Z = Z.loc[keep]
        return Z[f"n{h}"], Z[f"n{h}"] - Z.date.map(BM[h]), Z.date

    groups = [
        ("핫한 섹터 · 아무 종목(견줌)", hot),
        ("핫한 섹터 · 거래량 튀는데 내림", hot & VD),
        ("핫한 섹터 · **튀면서 오름**", hot & VU),
        ("핫한 섹터 · 세게 튀며 오름(3배·+5%)", hot & VU5),
        ("핫한 섹터 · 다음날 갭 +2%↑", hot & G2),
        ("핫한 섹터 · 다음날 갭 +4%↑", hot & G4),
        ("핫한 섹터 · **대장주**(시총 1위)", hot & L1),
        ("핫한 섹터 · **2등주**(시총 2위)", hot & L2),
        ("핫한 섹터 · 3등 이하", hot & L3),
        ("핫한 섹터 · 그날 거래대금 1위", hot & A1),
        ("대장주 & 튀면서 오름", hot & L1 & VU),
        ("2등주 & 튀면서 오름", hot & L2 & VU),
        ("3등 이하 & 튀면서 오름", hot & L3 & VU),
        ("대장·2등 & 튀면서 오름", hot & (L1 | L2) & VU),
        ("튀면서 오름 & 다음날 갭 +2%↑", hot & VU & G2),
        ("대장·2등 & 다음날 갭 +2%↑", hot & (L1 | L2) & G2),
        ("대장·2등 & 튀면서 오름 & 갭 +2%↑", hot & (L1 | L2) & VU & G2),
        ("튀면서 오름 & 외국인↑", hot & VU & Fx),
        ("대장·2등 & 튀면서 오름 & 외국인↑", hot & (L1 | L2) & VU & Fx),
        ("섹터 무관 · 튀면서 오름(견줌)", VU),
        ("섹터 무관 · 다음날 갭 +2%↑(견줌)", G2),
    ]
    P("# 핫한 섹터 — 튀면서 오름 · 장초반 갭 · 대장주/2등주 · %s" % time.strftime("%Y-%m-%d")); P("")
    P("- 칸 = 평균(초과) · 2018~22 / 2023~ · 데이 = 다음날 시가→종가 비용 0.23 · 스윙 = 다음날 시가→h일 종가 패널 비용 · 초과 = 같은 날 아무 종목(유니버스) 대비 · 같은 종목 보유 중 재매수 없음"); P("")
    P("| 무리 | 건수(데이) | 데이 승률 | 데이 | 스윙 5일 | 스윙 20일 | 스윙 60일 |"); P("|---|---|---|---|---|---|---|")
    n = 0; yrs = {}
    for lab, m in groups:
        m = m.fillna(False) & A.uni
        z = A[m]; a = z[z.date <= "20221231"]; b = z[z.date >= "20230101"]
        if len(a) < 20 or len(b) < 20:
            P("| %s | %d | - | 표본 적음 | | | |" % (lab, len(z))); continue
        cells = ["%+.2f(%+.2f) / %+.2f(%+.2f)" % (a.dayr.mean(), a.dayx.mean(), b.dayr.mean(), b.dayx.mean())]
        for h in HS:
            r, x, d = swing(m, h); n += 1
            ia, ib = d <= "20221231", d >= "20230101"
            cells.append("%+.1f(%+.1f) / %+.1f(%+.1f)" % (r[ia].mean(), x[ia].mean(), r[ib].mean(), x[ib].mean()))
            if h == 20: yrs[lab] = (x.groupby(d.str[:4]).mean(), (r > 0).mean())
        n += 1
        P("| %s | %d | %.0f%% | %s |" % (lab, len(z), (z.dayr > 0).mean() * 100, " | ".join(cells)))
    P(""); P("## 스윙 20일 해마다 초과 · 승률"); P("")
    P("| 무리 | 승률 | " + " | ".join(str(y) for y in range(2018, 2027)) + " |"); P("|---|---|" + "---|" * 9)
    for lab, (yr, w) in yrs.items():
        P("| %s | %.0f%% | %s |" % (lab, w * 100, " | ".join("%+.1f" % yr.get(str(y), np.nan) for y in range(2018, 2027))))
    P(""); P("(칸 %d · %.1f분)" % (n, (time.time() - t0) / 60))
    log_trials("sector_leader_%s" % time.strftime("%Y%m%d"), n)
    (ROOT / "reports" / ("sector_leader_%s.md" % time.strftime("%Y%m%d"))).write_text("\n".join(OUT) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
