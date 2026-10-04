# -*- coding: utf-8 -*-
"""미장 데이 — 실적 발표 반응일 장중 (2026-10-04, 사용자 "응 돌려봐").
반응일 = 장 마감 뒤(16시~) 발표면 다음 거래일 · 장 전(~9:30) 발표면 그날 (뉴욕 시각). 장중 발표는 뺀다.
반응일 시가에 사서 종가에 판다(비용 0.25%). 서프라이즈(%)와 그날 갭(시가 ÷ 전날 종가 — 장전 거래로 미리 보인다)으로 나눈다.
비교: 같은 날 유니버스(거래대금 상위 40%) 시가→종가 평균 — 미장 장중은 원래 비용 뒤 -0.24%.
⚠ 실적 자료(yfinance analyst/earn_*.pkl)는 **지금 상장된 4,673종목뿐** — 하루짜리라 생존 편향이 작지만 0 은 아니다.
    python research/us_earn_day.py
"""
import glob, sys, time
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(BASE))
from verdict import log_trials
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))
COST = 0.25
PER = (("학습 16~22", "20160101", "20221231"), ("검증 23~", "20230101", "20991231"), ("참고 08~15", "20080101", "20151231"))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    t0 = time.time()
    A = pd.read_pickle(BASE / "data" / "us_scan_full.pkl")[["ticker", "date", "close", "rawclose", "buy", "amt20", "volume"]]
    A = A[A.rawclose >= 3].sort_values(["ticker", "date"]).reset_index(drop=True)
    g = A.groupby("ticker", sort=False)
    A["open"] = g.buy.shift(1); A["pc"] = g.close.shift(1)
    A["oc"] = (A.close / A.open - 1) * 100 - COST
    A["gapd"] = (A.open / A.pc - 1) * 100
    A["co"] = (g.buy.shift(0) / A.close - 1) * 100            # 그날 종가 → 다음날 시가(참고)
    A["uni"] = A.groupby("date").amt20.rank(pct=True) >= 0.60
    A = A[A.oc.notna() & A.oc.abs().lt(80)]
    cal = np.array(sorted(A.date.unique()))
    # 실적 → 반응일
    E = pd.concat([pd.read_pickle(f) for f in sorted(glob.glob(str(BASE / "data/us/analyst/earn_*.pkl")))], ignore_index=True)
    E = E.dropna(subset=["Reported EPS", "Surprise(%)"]).rename(columns={"Surprise(%)": "sur"})
    ts = pd.to_datetime(E["Earnings Date"], utc=True).dt.tz_convert("America/New_York")
    E["d"] = ts.dt.strftime("%Y%m%d"); E["hr"] = ts.dt.hour + ts.dt.minute / 60
    E = E[(E.hr >= 16) | (E.hr < 9.5)]
    pos = np.searchsorted(cal, E.d.to_numpy())
    after = (E.hr >= 16).to_numpy()
    idx = np.where(after, pos + (cal[np.minimum(pos, len(cal) - 1)] == E.d.to_numpy()), pos)
    ok = idx < len(cal)
    E = E[ok].copy(); E["rd"] = cal[idx[ok]]
    E = E.drop_duplicates(["ticker", "rd"])
    J = E[["ticker", "rd", "sur"]].rename(columns={"rd": "date"}).merge(A, on=["ticker", "date"], how="inner")
    J = J[J.uni]
    bm = A[A.uni].groupby("date").oc.mean()
    J["ex"] = J.oc - J.date.map(bm)
    P("# 미장 데이 — 실적 반응일 시가→종가 · %s" % time.strftime("%Y-%m-%d")); P("")
    P("- 실적 발표 %s건 → 유니버스(거래대금 상위 40%%) 안 반응일 %s건 · 비용 %.2f%%" % (f"{len(E):,}", f"{len(J):,}", COST)); P("")
    def row(lab, Z):
        out = []
        for nm, a, b in PER:
            z = Z[(Z.date >= a) & (Z.date <= b)]
            if len(z) < 80: out.append("-"); continue
            yp = (z.groupby(z.date.str[:4]).oc.mean() > 0).sum(); ny = z.date.str[:4].nunique()
            out.append("%d건 · 평균 %+.2f · 중앙 %+.2f · 승률 %.0f%% · 시장 대비 %+.2f · %d/%d해" % (len(z), z.oc.mean(), z.oc.median(), (z.oc > 0).mean() * 100, z.ex.mean(), yp, ny))
        P("| %s | %s | %s | %s |" % (lab, out[0], out[1], out[2]))
    P("| 무리 | 학습 16~22 | 검증 23~ | 참고 08~15 |"); P("|---|---|---|---|")
    n = 0
    row("실적 반응일 전체", J); n += 1
    for lab, m in (("서프라이즈 +20%↑", J.sur >= 20), ("서프라이즈 +10~20%", J.sur.between(10, 20)), ("서프라이즈 0~10%", J.sur.between(0, 10)),
                   ("서프라이즈 마이너스", J.sur < 0), ("서프라이즈 -20%↓", J.sur <= -20)):
        row(lab, J[m]); n += 1
    P(""); P("| 서프라이즈 × 반응일 갭 | 학습 16~22 | 검증 23~ | 참고 08~15 |"); P("|---|---|---|---|")
    for sl, sm in (("서프 +", J.sur > 0), ("서프 +10%↑", J.sur >= 10), ("서프 −", J.sur < 0)):
        for gl, gm in (("갭 +5%↑", J.gapd >= 5), ("갭 +2~5%", J.gapd.between(2, 5)), ("갭 -2~+2%", J.gapd.between(-2, 2)), ("갭 -5~-2%", J.gapd.between(-5, -2)), ("갭 -5%↓", J.gapd <= -5)):
            row("%s & %s" % (sl, gl), J[sm & gm]); n += 1
    P(""); P("| 갭만(서프라이즈 무관) | 학습 | 검증 | 참고 |"); P("|---|---|---|---|")
    for gl, gm in (("갭 +10%↑", J.gapd >= 10), ("갭 +5~10%", J.gapd.between(5, 10)), ("갭 -5~-10%", J.gapd.between(-10, -5)), ("갭 -10%↓", J.gapd <= -10)):
        row(gl, J[gm]); n += 1
    log_trials("us_earn_day_%s" % time.strftime("%Y%m%d"), n)
    J.to_pickle(ROOT / "cache" / "us_earn_day.pkl")
    P(""); P("(칸 %d · %.0f분)" % (n, (time.time() - t0) / 60))
    (ROOT / "reports" / ("us_earn_day_%s.md" % time.strftime("%Y%m%d"))).write_text("\n".join(OUT) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
