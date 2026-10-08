# -*- coding: utf-8 -*-
"""핫한 섹터 × 거래량 튐 / 외국인 매수 — 신호 다음날을 **장초반 · 오후 2시 이후 · 종가**로 나눠 본다 (2026-10-08 사용자 "장초반 체크하고 2시 이후 흐름 한 번 더 보고 종가 체크").
신호 = sector_day.py 와 같음(sector_day_sig.pkl). 다음날 장중 = 1분봉 단면(m1_panel_KR · 지금 거래대금 상위 1,000 · 2022-12~).
구간 수익(비용 전): 장초반 시가→10:00 · 낮 10:00→14:00 · 오후 14:00→종가 · 하루 시가→종가 · 밤 종가→다음날 시가.
전략(비용 뒤):
  ① 시가 매수 → 종가(지금 방식) 0.23%
  ② 장초반 확인: 10:00 가격이 시가 위면 10:00 매수 → 종가 0.28%
  ③ 장초반 확인 반대: 10:00 가 시가 아래(눌림)면 10:00 매수 → 종가 0.28%
  ④ 2시 이후: 14:00 가 시가 위(그날 강함)면 14:00 매수 → 종가 0.28%
  ⑤ 2시 이후 반대: 14:00 가 시가 아래면 14:00 매수 → 종가 0.28%
  ⑥ 종가 확인: 그날 시가→종가 플러스로 끝난 걸 종가 단일가 매수 → 다음날 시가 0.23%
견줌 = 같은 날 패널 안 아무 종목의 같은 구간 평균.
    python research/sector_day_m1.py
"""
import sys, time
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(BASE))
from verdict import log_trials
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    t0 = time.time()
    S = pd.read_pickle(ROOT / "cache" / "sector_day_sig.pkl").rename(columns={"n_date": "date"})
    M = pd.read_pickle(ROOT / "cache" / "m1_panel_KR.pkl")[["ticker", "date", "o", "c", "pc", "p1000", "p1400", "no", "amt20"]]
    M = M[M.pc.notna() & ((M.o / M.pc - 1).abs() < 0.29)]
    seg = lambda a, b: (M[b] / M[a] - 1) * 100
    M["s_open"] = seg("o", "p1000"); M["s_mid"] = seg("p1000", "p1400"); M["s_pm"] = seg("p1400", "c"); M["s_day"] = seg("o", "c"); M["s_night"] = seg("c", "no")
    M["st1"] = M.s_day - 0.23
    M["st2"] = np.where(M.p1000 > M.o, seg("p1000", "c") - 0.28, np.nan)
    M["st3"] = np.where(M.p1000 < M.o, seg("p1000", "c") - 0.28, np.nan)
    M["st4"] = np.where(M.p1400 > M.o, seg("p1400", "c") - 0.28, np.nan)
    M["st5"] = np.where(M.p1400 < M.o, seg("p1400", "c") - 0.28, np.nan)
    M["st6"] = np.where(M.c > M.o, M.s_night - 0.23, np.nan)
    COLS = ["s_open", "s_mid", "s_pm", "s_day", "s_night", "st1", "st2", "st3", "st4", "st5", "st6"]
    BM = M.groupby("date")[COLS].mean()
    J = S.merge(M, on=["ticker", "date"], how="inner")
    P("# 핫한 섹터 신호 다음날 — 장초반 · 오후 2시 이후 · 종가 · %s" % time.strftime("%Y-%m-%d")); P("")
    P("- 신호 %s건 중 1분봉 있는 다음날 %s건(지금 상위 1,000 종목만) · 2022-12~ · 구간은 비용 전, 전략은 비용 뒤 · 괄호 = 같은 날 아무 종목 대비" % (f"{len(S):,}", f"{len(J):,}")); P("")
    groups = [("핫한 섹터 · 아무 종목", J.inhot), ("핫한 섹터 · 거래량 2배↑", J.inhot & J.V2), ("핫한 섹터 · 거래량 3배↑", J.inhot & J.V3),
              ("핫한 섹터 · 외국인↑", J.inhot & J.F), ("핫한 섹터 · 거래량 2배↑ & 외국인↑", J.inhot & J.V2 & J.F),
              ("섹터 무관 · 거래량 3배↑", J.V3), ("섹터 무관 · 외국인↑", J.F)]
    for k in [c for c in J.columns if c.startswith("S_")]:
        groups.append(("[%s] · 거래량 2배↑" % k[2:], J[k] & J.V2)); groups.append(("[%s] · 외국인↑" % k[2:], J[k] & J.F))
    P("## 구간별 흐름(비용 전 평균 · 괄호 = 아무 종목 대비)"); P("")
    P("| 무리 | 건수 | 장초반 시가→10시 | 낮 10→14시 | 오후 14시→종가 | 하루 시가→종가 | 밤 종가→다음 시가 |"); P("|---|---|---|---|---|---|---|")
    for lab, m in groups:
        z = J[m.fillna(False)]
        if len(z) < 30: continue
        b = BM.reindex(z.date)
        cell = lambda c: "%+.2f (%+.2f)" % (z[c].mean(), (z[c].values - b[c].values).mean())
        P("| %s | %d | %s | %s | %s | %s | %s |" % (lab, len(z), cell("s_open"), cell("s_mid"), cell("s_pm"), cell("s_day"), cell("s_night")))
    P("")
    P("## 사고파는 때를 바꾸면(비용 뒤 · 학습 22.12~24 / 검증 25~ · 건수)"); P("")
    P("| 무리 | ① 시가→종가 | ② 10시 강하면 10시→종가 | ③ 10시 눌리면 10시→종가 | ④ 14시 강하면 14시→종가 | ⑤ 14시 약하면 14시→종가 | ⑥ 양봉 마감 종가→다음 시가 |"); P("|---|---|---|---|---|---|---|")
    for lab, m in groups:
        z = J[m.fillna(False)]
        if len(z) < 30: continue
        cells = []
        for c in ("st1", "st2", "st3", "st4", "st5", "st6"):
            a_ = z[(z.date <= "20241231")][c].dropna(); b_ = z[(z.date >= "20250101")][c].dropna()
            cells.append("%+.2f / %+.2f (%d)" % (a_.mean() if len(a_) else np.nan, b_.mean() if len(b_) else np.nan, len(a_) + len(b_)))
        P("| %s | %s |" % (lab, " | ".join(cells)))
    allb = M[M.date >= "20221201"]
    P("| (아무 종목) | %s |" % " | ".join("%+.2f / %+.2f" % (allb[allb.date <= "20241231"][c].mean(), allb[allb.date >= "20250101"][c].mean()) for c in ("st1", "st2", "st3", "st4", "st5", "st6")))
    P(""); P("(%.1f분)" % ((time.time() - t0) / 60))
    log_trials("sector_day_m1_%s" % time.strftime("%Y%m%d"), len(groups) * 6)
    (ROOT / "reports" / ("sector_day_m1_%s.md" % time.strftime("%Y%m%d"))).write_text("\n".join(OUT) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
