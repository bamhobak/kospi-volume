# -*- coding: utf-8 -*-
"""핫한 섹터 × 거래량 튐 / 외국인 매수 비율↑ — **스윙**으로 (2026-10-08 사용자 "스윙매매로 바꾸면?", H0309 후속).
신호는 sector_day.py 와 같다(테마 = 네이버 2026-08-28 구성을 과거에 씌움 · 핫한 섹터 = 테마 동일가중 20일 수익 상위 10%).
매매: 신호 다음날 시가 매수 → 5·10·20·40·60거래일 뒤 종가(패널 n{h} — 비용·미끄러짐 0.58~1.38% 반영, 폐지 포함).
견줌 = 같은 날 유니버스(거래대금 상위 40%) 아무 종목 같은 보유 평균 → 초과. 같은 종목은 보유 중 다시 안 산다.
기간 2018~22 / 2023~ (외국인 자료 2018~).
    python research/sector_swing.py
"""
import sqlite3, sys, time
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(BASE))
from verdict import log_trials
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))
NAMED = {"건설": ["건설 대표주", "건설 중소형", "건설기계"], "우주항공": ["우주항공산업(누리호/인공위성 등)", "항공기부품", "UAM(도심항공모빌리티)"],
         "방산": ["방위산업/전쟁 및 테러"], "조선": ["조선", "조선기자재"], "원전": ["원자력발전"],
         "전력": ["전력설비", "전력저장장치(ESS)", "스마트그리드(지능형전력망)"], "로봇": ["피지컬 AI/휴머노이드 로봇", "로봇(산업용/협동로봇 등)", "지능형로봇/인공지능(AI)"]}
HS = (5, 10, 20, 40, 60)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    t0 = time.time()
    A = pd.read_pickle(BASE / "data/kr_scan.pkl")
    A = A[A.date >= "20170601"][["ticker", "date", "close", "volume", "amt20", "jw"] + [f"n{h}" for h in HS] if "jw" in A.columns else
          ["ticker", "date", "close", "volume", "amt20"] + [f"n{h}" for h in HS]].copy()
    A = A.sort_values(["ticker", "date"]).reset_index(drop=True)
    A["uni"] = A.groupby("date").amt20.rank(pct=True) >= 0.6
    S = pd.read_csv(BASE / "data/sector.csv", dtype=str); S = S[S.kind == "theme"]
    NAMED["반도체"] = sorted({g for g in S.gname if "반도체" in g})
    g = A.groupby("ticker", sort=False)
    A["r1"] = (A.close / g.close.shift(1) - 1) * 100
    A = A[A.r1.abs().fillna(0) < 31]
    g = A.groupby("ticker", sort=False)
    A["vmul"] = A.volume / g.volume.transform(lambda s: s.shift(1).rolling(20, min_periods=15).mean())
    A["amt"] = A.close * A.volume
    c = sqlite3.connect("file:" + str(BASE / "data" / "investor.db") + "?mode=ro", uri=True)
    F = pd.read_sql("SELECT ticker, date, frgn FROM flow11 WHERE date >= '20170601'", c)
    A = A.merge(F, on=["ticker", "date"], how="left")
    A["fr"] = A.frgn / A.amt.replace(0, np.nan) * 100
    A["fr20"] = A.groupby("ticker", sort=False).fr.transform(lambda s: s.shift(1).rolling(20, min_periods=10).mean())
    M = S[["gname", "ticker"]].merge(A[["ticker", "date", "r1"]], on="ticker")
    TI = M.groupby(["gname", "date"]).r1.mean().reset_index().sort_values(["gname", "date"])
    TI["r20"] = TI.groupby("gname").r1.transform(lambda s: ((1 + s / 100).rolling(20, min_periods=15).apply(np.prod, raw=True) - 1) * 100)
    TI["hot"] = TI.groupby("date").r20.rank(pct=True) >= 0.9
    hp = TI[TI.hot][["gname", "date"]].merge(S[["gname", "ticker"]], on="gname")[["ticker", "date"]].drop_duplicates(); hp["inhot"] = True
    A = A.merge(hp, on=["ticker", "date"], how="left"); A["inhot"] = A.inhot.fillna(False).astype(bool)
    A = A.sort_values(["ticker", "date"]).reset_index(drop=True)
    A = A[A.date >= "20180101"]
    BM = {h: A[A.uni].groupby("date")[f"n{h}"].mean() for h in HS}
    V3, V2 = A.vmul >= 3, A.vmul >= 2
    Fx = (A.fr >= 5) & (A.fr > A.fr20)
    di = {d: i for i, d in enumerate(sorted(A.date.unique()))}
    A["di"] = A.date.map(di)

    def trades(m, h):
        Z = A[m.fillna(False) & A.uni & A[f"n{h}"].notna()].sort_values("di")
        keep, last = [], {}
        for t, i, ix in zip(Z.ticker.values, Z.di.values, Z.index):
            if last.get(t, -10 ** 9) >= i: continue
            last[t] = i + h; keep.append(ix)
        Z = Z.loc[keep]
        return Z.assign(ret=Z[f"n{h}"], ex=Z[f"n{h}"] - Z.date.map(BM[h]))

    P("# 핫한 섹터 × 거래량 튐 / 외국인 매수 — 스윙 · %s" % time.strftime("%Y-%m-%d")); P("")
    P("- 다음날 시가 매수 → h 거래일 뒤 종가 · 비용 패널 cost · 초과 = 같은 날 유니버스 같은 보유 평균 대비 · 칸 = 2018~22 / 2023~ 평균(초과) · 건수"); P("")
    P("| 무리 | " + " | ".join("%d일" % h for h in HS) + " |"); P("|---|" + "---|" * len(HS))
    groups = [("핫한 섹터 · 아무 종목", A.inhot), ("핫한 섹터 · 거래량 2배↑", A.inhot & V2), ("핫한 섹터 · 거래량 3배↑", A.inhot & V3),
              ("핫한 섹터 · 외국인↑", A.inhot & Fx), ("핫한 섹터 · 거래량 2배↑ & 외국인↑", A.inhot & V2 & Fx),
              ("섹터 무관 · 거래량 3배↑", V3), ("섹터 무관 · 외국인↑", Fx)]
    for sec, gl in NAMED.items():
        ins = A.ticker.isin(set(S[S.gname.isin(gl)].ticker))
        groups += [("[%s] · 거래량 2배↑" % sec, ins & V2), ("[%s] · 외국인↑" % sec, ins & Fx), ("[%s] · 섹터 핫할 때 아무 날" % sec, ins & A.inhot)]
    n = 0
    for lab, m in groups:
        cells = []
        for h in HS:
            Z = trades(m, h); n += 1
            a = Z[Z.date <= "20221231"]; b = Z[Z.date >= "20230101"]
            cells.append("%+.1f(%+.1f) / %+.1f(%+.1f) · %d" % (a.ret.mean(), a.ex.mean(), b.ret.mean(), b.ex.mean(), len(Z)) if len(a) >= 20 and len(b) >= 20 else "%d건" % len(Z))
        P("| %s | %s |" % (lab, " | ".join(cells)))
    P(""); P("## 해마다(초과 · 승률) — 이름 안 고른 무리만(섹터 이름은 지금 뜬 걸 골라 뒤늦은 눈 섞임)"); P("")
    P("| 무리 · 보유 | 승률 | " + " | ".join(str(y) for y in range(2018, 2027)) + " |"); P("|---|---|" + "---|" * 9)
    for lab, m in (("핫한 섹터 · 아무 종목", A.inhot), ("핫한 섹터 · 외국인↑", A.inhot & Fx), ("핫한 섹터 · 거래량 2배↑ & 외국인↑", A.inhot & V2 & Fx)):
        for h in (20, 40, 60):
            Z = trades(m, h); yr = Z.groupby(Z.date.str[:4]).ex.mean()
            P("| %s · %d일 | %.0f%% | %s |" % (lab, h, (Z.ret > 0).mean() * 100, " | ".join("%+.1f" % yr.get(str(y), np.nan) for y in range(2018, 2027))))
    P(""); P("(칸 %d · %.1f분)" % (n, (time.time() - t0) / 60))
    log_trials("sector_swing_%s" % time.strftime("%Y%m%d"), n)
    (ROOT / "reports" / ("sector_swing_%s.md" % time.strftime("%Y%m%d"))).write_text("\n".join(OUT) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
