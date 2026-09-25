# -*- coding: utf-8 -*-
"""국내 하룻밤 보유 — **상한가를 빼면 남는 게 있나** (2026-09-26, overnight.py 후속).

overnight.py 에서 국내만 강했다: 상한가 고가 마감 → 밤 +5.27%(순)·승률 74%. 그런데 상한가 종가 매수는
잔량이 없어 **체결이 안 된다**(체결되는 날은 매물이 터지는 날 — 역선택). 寄り底 +15%·BSJP 의 좋은 평균이
그 상한가 섞임 덕인지 가른다. 당일 상승률 구간 × 고가 마감 여부로 쪼갠다. 상한가(+29%↑)는 따로 둔다.
가격제한폭이 2015-06-15 전엔 ±15% 라 그 전은 '+14%↑' 가 상한가다 — 여기선 **2016~ 만** 본다.

    python research/overnight_kr2.py
"""
import sys, time, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(BASE)); sys.path.insert(0, str(ROOT))
import run_spec as R
from verdict import log_trials, boot_ci


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    A, uni, since = R.load_market("KR")
    g = A.groupby("ticker", sort=False)
    A["r1"] = (A.close / g.close.shift(1) - 1) * 100
    A["ovn"] = (A.buy / A.close - 1) * 100 - A.cost
    A["ov"] = (A.buy / A.close - 1) * 100
    A["hiclose"] = A.close >= A.high * 0.995
    A["locked"] = (A.high == A.low)                                  # 하루 종일 한 가격(점상 등)
    Z = A[uni & A.ovn.notna() & (A.date >= "20160101")].copy()
    bins = [-100, 0, 5, 10, 15, 20, 25, 29, 100]
    lab = ["<0", "0~5", "5~10", "10~15", "15~20", "20~25", "25~29", "29↑(상한가)"]
    Z["b"] = pd.cut(Z.r1, bins, labels=lab, right=False)
    out = ["# 국내 하룻밤 보유 — 당일 상승률 × 고가 마감 · 2016~ · %s" % time.strftime("%Y-%m-%d"), "",
           "밤 = 다음날 시가 ÷ 오늘 종가 − 1(%). 순 = 왕복 비용 차감. 거래대금 상위 40%.", "",
           "| 당일 상승률 | 고가 마감(0.5% 이내) | n | 밤 평균(전) | 밤 평균(순) | 중앙(순) | 순 승률 | 학습 16~22 평균(순) | 검증 23~ 평균(순) | 양수해 | 월CI 하한 |",
           "|---|---|---|---|---|---|---|---|---|---|---|"]
    for b in lab:
        for hc in (True, False):
            z = Z[(Z.b == b) & (Z.hiclose == hc)]
            if len(z) < 50:
                continue
            yr = z.groupby(z.date.str[:4]).ovn.mean(); ym = z.groupby(z.date.str[:6]).ovn.mean()
            tr, va = z[z.date <= "20221231"].ovn.mean(), z[z.date >= "20230101"].ovn.mean()
            out.append("| %s | %s | %s | %+.2f | **%+.2f** | %+.2f | %.0f%% | %+.2f | %+.2f | %d/%d | %s |" % (
                b, "예" if hc else "아니오", f"{len(z):,}", z.ov.mean(), z.ovn.mean(), z.ovn.median(), (z.ovn > 0).mean() * 100,
                tr, va, (yr > 0).sum(), len(yr), ("%+.2f" % boot_ci(ym)) if len(ym) >= 12 else "-"))
    lk = Z[(Z.b == "29↑(상한가)")]
    out += ["", "상한가 마감 %s건 중 하루 종일 한 가격(점상한가) %s건(%.0f%%) — 이건 종가에 **절대** 못 산다. 나머지 %s건 밤 평균(순) %+.2f%%." % (
        f"{len(lk):,}", f"{lk.locked.sum():,}", lk.locked.mean() * 100, f"{(~lk.locked).sum():,}", lk[~lk.locked].ovn.mean())]
    # 상한가 제외판 — 寄り底·BSJP
    OL = Z.low >= Z.open * 0.998
    for nm, m in (("寄り底 시가=저가 & +15%↑, 상한가 제외", OL & (Z.r1 >= 15) & (Z.r1 < 29)),
                  ("寄り底 시가=저가 & +10%↑, 상한가 제외", OL & (Z.r1 >= 10) & (Z.r1 < 29)),
                  ("+20~29% & 고가 마감, 상한가 제외", (Z.r1 >= 20) & (Z.r1 < 29) & Z.hiclose)):
        z = Z[m]
        out.append("- %s: %s건 · 밤 평균(순) %+.2f · 중앙 %+.2f · 승률 %.0f%% · 학습 %+.2f · 검증 %+.2f" % (
            nm, f"{len(z):,}", z.ovn.mean(), z.ovn.median(), (z.ovn > 0).mean() * 100,
            z[z.date <= "20221231"].ovn.mean(), z[z.date >= "20230101"].ovn.mean()))
    log_trials("overnight_kr2_%s" % time.strftime("%Y%m%d"), len(lab) * 2 + 3)
    rp = ROOT / "reports" / ("overnight_kr2_%s.md" % time.strftime("%Y%m%d"))
    rp.write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()
