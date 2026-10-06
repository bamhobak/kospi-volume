# -*- coding: utf-8 -*-
"""국장 — 외국인 매수가 최근 5일 평균의 5배로 뛴 다음날, 시가 단일가 매수 → 그날 종가 단일가 매도 (2026-10-07 사용자).
자료: investor.db flow11(KRX 투자자별 **순매수 금액**, 2018~) — 총매수 금액은 없어서 순매수로 세 가지로 정의한다:
  A 순매수 ≥ 5 × 직전 5일 순매수 평균 (평균 > 0 일 때만)
  B 순매수 > 0 & ≥ 5 × 직전 5일 |순매수| 평균  (평소 외국인 손바뀜 크기 대비 — 평균이 음수·0 이어도 됨)
  C 순매수 > 0 & ≥ 5 × 직전 5일 순매수 중 플러스만의 평균(매수한 날 기준, 0 이면 제외)
각각 거래대금 20일 평균 대비 순매수 0.5%↑ / 2%↑ (너무 작은 금액 거르기)와 그날 주가(오름/내림) · 유니버스(거래대금 상위 40%) 안팎으로 나눠 본다.
비용 0.23%(단일가끼리). 초과 = 같은 날 유니버스 시가→종가 평균 대비. 학습 2018~22 / 검증 2023~. 참고로 5일 보유(다음날 시가 → 5일째 종가).
    python research/frgn5x.py
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


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    t0 = time.time()
    A, _ = O.build("KR")
    A = A[A.date >= "20180101"].copy()
    c = sqlite3.connect("file:" + str(BASE / "data" / "investor.db") + "?mode=ro", uri=True)
    F = pd.read_sql("SELECT ticker, date, frgn FROM flow11 WHERE date >= '20171101'", c).sort_values(["ticker", "date"])
    g = F.groupby("ticker", sort=False).frgn
    F["m5"] = g.transform(lambda s: s.shift(1).rolling(5, min_periods=5).mean())
    F["a5"] = g.transform(lambda s: s.abs().shift(1).rolling(5, min_periods=5).mean())
    F["p5"] = g.transform(lambda s: s.clip(lower=0).shift(1).rolling(5, min_periods=5).sum() / (s.shift(1) > 0).rolling(5, min_periods=5).sum().replace(0, np.nan))
    # 신호일(t) 값 → 다음 **거래일**(시장 달력) 줄에 붙인다 — A 는 걸러진 줄이 있어 종목별 shift 로는 하루가 어긋날 수 있다
    cal = np.array(sorted(A.date.unique())); nxt = dict(zip(cal[:-1], cal[1:]))
    S = F.merge(A[["ticker", "date", "r1t", "amt20"]], on=["ticker", "date"], how="inner")
    S["date"] = S.date.map(nxt); S = S.dropna(subset=["date"])
    S = S.rename(columns={k: "s_" + k for k in ("frgn", "m5", "a5", "p5", "r1t", "amt20")})
    A = A.sort_values(["ticker", "date"]).reset_index(drop=True)
    A = A.merge(S, on=["ticker", "date"], how="left")
    gA = A.groupby("ticker", sort=False)
    # 5일 보유 참고(다음날 시가 → 그 날 포함 5거래일째 종가)
    A["c5"] = gA.close.shift(-4)
    A["ret"] = A.oc - COST
    A["ret5"] = (A.c5 / A.open - 1) * 100 - COST - 0.12                # 스윙 비용(대략) 더
    bm = A[A.uni].groupby("date").oc.mean(); A["ex"] = A.oc - A.date.map(bm)
    bm5 = ((A.c5 / A.open - 1) * 100)[A.uni].groupby(A.date[A.uni]).mean(); A["ex5"] = (A.c5 / A.open - 1) * 100 - A.date.map(bm5)
    rel = A.s_frgn / (A.s_amt20 * 1e8) * 100                           # 순매수 ÷ 20일 평균 거래대금(%)
    sig = {"A 순매수 ≥ 5×5일 평균(평균>0)": (A.s_m5 > 0) & (A.s_frgn >= 5 * A.s_m5),
           "B 순매수 ≥ 5×5일 |순매수| 평균": (A.s_frgn > 0) & (A.s_frgn >= 5 * A.s_a5),
           "C 순매수 ≥ 5×5일 매수한 날 평균": (A.s_frgn > 0) & (A.s_p5 > 0) & (A.s_frgn >= 5 * A.s_p5)}
    P("# 외국인 순매수 5배 뛴 다음날 시가→종가 · %s" % time.strftime("%Y-%m-%d")); P("")
    P("- 국장 2018~ (flow11 순매수 금액) · 비용 %.2f%% · 초과 = 같은 날 유니버스(거래대금 상위 40%%) 시가→종가 평균 대비 · 학습 2018~22 / 검증 2023~" % COST)
    P("- 5일 보유 칸은 참고(비용 0.35%)"); P("")
    P("| 조건 | 무리 | 학습 18~22: 건수·평균·승률·초과 | 검증 23~: 건수·평균·승률·초과 | 해마다 플러스 | 5일 보유(학습/검증 · 초과) |"); P("|---|---|---|---|---|---|")
    n = 0
    for nm, s in sig.items():
        for lab, m in (("전체", s), ("유니버스 안", s & A.uni), ("유니버스 안 & 거래대금 0.5%↑", s & A.uni & (rel >= 0.5)),
                       ("유니버스 안 & 2%↑", s & A.uni & (rel >= 2)), ("유니버스 안 & 그날 주가 오름", s & A.uni & (A.s_r1t > 0)),
                       ("유니버스 안 & 그날 주가 내림", s & A.uni & (A.s_r1t <= 0)), ("유니버스 안 & 그날 +5%↑", s & A.uni & (A.s_r1t >= 5))):
            Z = A[m.fillna(False) & A.ret.notna()]
            if len(Z) < 30: continue
            cells = []
            for a, b in (("20180101", "20221231"), ("20230101", "20991231")):
                z = Z[(Z.date >= a) & (Z.date <= b)]
                cells.append("%d건 %+.2f%% · %.0f%% · %+.2f" % (len(z), z.ret.mean(), (z.ret > 0).mean() * 100, z.ex.mean()) if len(z) else "-")
            yr = Z.groupby(Z.date.str[:4]).ret.mean()
            z5 = Z[Z.ret5.notna()]
            r5 = "%+.2f / %+.2f · %+.2f" % (z5[z5.date < "20230101"].ret5.mean(), z5[z5.date >= "20230101"].ret5.mean(), z5.ex5.mean())
            P("| %s | %s | %s | %s | %d/%d | %s |" % (nm, lab, cells[0], cells[1], int((yr > 0).sum()), len(yr), r5)); n += 1
    allu = A[A.uni & A.ret.notna()]
    P("| (견줌) | 유니버스 아무 종목 | %+.2f%% · %.0f%% | %+.2f%% · %.0f%% | | |" % (
        allu[allu.date < "20230101"].ret.mean(), (allu[allu.date < "20230101"].ret > 0).mean() * 100,
        allu[allu.date >= "20230101"].ret.mean(), (allu[allu.date >= "20230101"].ret > 0).mean() * 100))
    P(""); P("(칸 %d · %.1f분)" % (n, (time.time() - t0) / 60))
    log_trials("frgn5x_%s" % time.strftime("%Y%m%d"), n)
    (ROOT / "reports" / ("frgn5x_%s.md" % time.strftime("%Y%m%d"))).write_text("\n".join(OUT) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
