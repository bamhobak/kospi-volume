# -*- coding: utf-8 -*-
"""**미장 축 스캔** — 보유 재료를 하나씩 10등분해 계단을 보고, 계단이면 **바로 통제 점검까지** (2026-09-19).

국내 1차에서 배운 것: 중앙값 잣대는 변동성 큰 종목에 불리해서 '크고 조용한 종목' 과 얽힌 축이 계단처럼
보인다(배당·이익수익률·내부자 건수가 전부 대리 지표였다). 그래서 계단이 나오면 날짜별
**변동성(vol20) 3등분 × 거래대금(amt20) 3등분 = 9칸** 안에서 다시 10등분해 방향이 살아 있는지 본다.
9칸 중 학습 7칸↑ · 검증 5칸↑ 같은 방향(|ρ|≥0.5)이어야 '진짜 축'.

판정 규율은 국내 axis_scan.py 와 같다. 국면 = S&P500 60일선 아래(하락장). 미장 패널은 생존편향이 있다.

    python research/axis_scan_us.py      → research/reports/axis_scan_us_YYYYMMDD.md
"""
import sys, time, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(BASE)); sys.path.insert(0, str(ROOT))
import features_us as FU
from axis_scan import scan_one, spear, TR0, TR1, VA0
from verdict import log_trials

OUT = []


def P(x=""):
    OUT.append(x)


def log(m):
    print("%s %s" % (time.strftime("%H:%M:%S"), m), file=sys.stderr, flush=True)


def regime_down_us():
    cp = ROOT / "cache" / "us500.pkl"; cp.parent.mkdir(exist_ok=True)
    if cp.exists() and time.time() - cp.stat().st_mtime < 86400:
        IX = pd.read_pickle(cp)
    else:
        import FinanceDataReader as fdr
        IX = fdr.DataReader("US500", "2004-06-01")[["Close"]]; IX = IX[IX.Close > 0]
        IX.to_pickle(cp)
    IX = IX.copy(); IX["ma60"] = IX.Close.rolling(60).mean(); IX["date"] = IX.index.strftime("%Y%m%d")
    return dict(zip(IX.date, IX.Close < IX.ma60))


def control(df, col, h, sign):
    c = "n%d" % h
    z = df[[col, "date", c, "vq", "aq"]].dropna()
    z["b"] = np.ceil(z.groupby(["date", "vq", "aq"])[col].rank(pct=True) * 10).clip(1, 10)
    k = []
    for part in (z[(z.date >= TR0) & (z.date <= TR1)], z[z.date >= VA0]):
        rs = []
        for _, g in part.groupby(["vq", "aq"]):
            mm = g.groupby("b")[c].median()
            if len(mm) >= 8:
                rs.append(spear(mm.index, mm.values))
        k.append((sum(1 for r in rs if np.sign(r) == sign and abs(r) >= 0.5), len(rs)))
    return k


def main():
    sys.stdout.reconfigure(encoding="utf-8"); t0 = time.time()
    log("미장 패널")
    A = pd.read_pickle(BASE / "data/us_scan.pkl")
    A = A[((~A.pref.fillna(False)) & (A.rawclose >= 3)).fillna(False)]
    cal = sorted(A.date.unique())
    uni = (A.groupby("date").amt20.rank(pct=True) >= 0.60).fillna(False)
    A = A[uni & (A.date >= TR0)][["ticker", "date", "amt20", "vol20", "n5", "n20"]].reset_index(drop=True)
    log("재료 붙이는 중 (%s행)" % f"{len(A):,}")
    cols = FU.attach(A, cal=cal)
    A["down"] = A.date.map(regime_down_us()).fillna(False).astype(bool)
    A["vq"] = np.ceil(A.groupby("date").vol20.rank(pct=True) * 3).clip(1, 3)
    A["aq"] = np.ceil(A.groupby("date").amt20.rank(pct=True) * 3).clip(1, 3)
    log("붙인 재료 %d개" % len(cols))
    P("# 축 스캔 · 미장 · %s" % time.strftime("%Y-%m-%d")); P("")
    P("재료 %d개 × 5일/20일 × 전체·하락장(S&P500 60일선 아래). 계단 = 학습 |ρ|≥0.8 · 검증 같은 방향 |ρ|≥0.5 · "
      "해마다 같은 방향 70%%↑. 계단이면 변동성×거래대금 9칸 통제(학습 7↑·검증 5↑)." % len(cols)); P("")
    P("| 재료 | 설명 | 보유 | 국면 | 결측 | ρ학습 | ρ검증 | 같은방향해 | 좋은쪽 학습/검증 | 칸별 학습 중앙 | 통제 학습/검증 | 판정 |")
    P("|---|---|---|---|---|---|---|---|---|---|---|---|")
    cells = 0; keep = []
    for col in cols:
        miss = A[col].isna().mean() * 100
        for h in (5, 20):
            for reg, m in (("전체", slice(None)), ("하락장", A.down.values)):
                D = A.loc[m]
                r = scan_one(D, col, h)
                if r is None:
                    P("| %s | %s | %d일 | %s | %.0f%% | 표본 부족 | | | | | | |" % (col, FU.DESC[col][1], h, reg, miss)); continue
                cells += r["kb"]
                ctl = ""; verdict = ""
                if r["stair"]:
                    (a, na), (b, nb) = control(D, col, h, np.sign(r["rt"])); cells += 18
                    ctl = "%d/%d · %d/%d" % (a, na, b, nb)
                    real = a >= 7 and b >= 5
                    verdict = ("**진짜 축·매수**" if r["buy"] else "**진짜 축·회피**") if real else "대리 지표"
                    keep.append((col, h, reg, verdict))
                P("| %s | %s | %d일 | %s | %.0f%% | %+.2f | %+.2f | %s | %+.2f / %+.2f | %s | %s | %s |" % (
                    col, FU.DESC[col][1], h, reg, miss, r["rt"], r["rv"],
                    ("%.0f%%" % (r["cons"] * 100)) if r["cons"] == r["cons"] else "-", r["g_tr"], r["g_va"],
                    " ".join("%+.1f" % v for v in r["curve_tr"]), ctl, verdict))
        log("  %s 끝" % col)
    P(""); P("계단→통제 통과: " + (", ".join("%s %d일 %s %s" % k for k in keep if "진짜" in k[3]) or "없음"))
    P(""); P("돌린 칸 %d개 · %.0f초" % (cells, time.time() - t0))
    log_trials("axis_scan_us_%s" % time.strftime("%Y%m%d"), cells)
    rp = ROOT / "reports" / ("axis_scan_us_%s.md" % time.strftime("%Y%m%d")); rp.write_text("\n".join(OUT) + "\n", encoding="utf-8")
    print("\n".join(OUT)); print("\n보고서:", rp)


if __name__ == "__main__":
    main()
