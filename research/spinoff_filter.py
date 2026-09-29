# -*- coding: utf-8 -*-
"""미국 분사주 — 어떤 경우에 더 좋은가(설명용 쪼개기) (2026-09-29, spinoff_exit 후속).

⚠ 결과를 보고 조건을 고르면 과적합이다 — 여기서는 **기전 확인용**으로만 본다(표본 166건).
  · 첫 20일 수익(상장가 대비 매수 직전까지) — 기관의 기계적 매도가 깊었을수록 더 좋은가
  · 매수 시점 20일 거래대금(유동성 상위 40% 기준 순위)
  · 주가 수준($10 미만 · 10~30 · 30↑)
  · S&P500 국면(60일선 위/아래)
기준: 고정 250일 · 다음날 시가 매수 · 비용 차감 · 같은 구간 유니버스 동일가중 대비 초과.

    python research/spinoff_filter.py
"""
import io, json, re, sys, time, warnings, zipfile, contextlib
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(BASE)); sys.path.insert(0, str(ROOT))
from verdict import log_trials


def log(m):
    print("%s %s" % (time.strftime("%H:%M:%S"), m), file=sys.stderr, flush=True)


src = (ROOT / "spinoff.py").read_text(encoding="utf-8")
body = src.split("def main():", 1)[1].split('    uq = K.amt20.groupby', 1)[0]
exec("def _events():\n" + body.replace("    sys.stdout.reconfigure(encoding=\"utf-8\")\n", "") + "    return E, K, idx, ev\n")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    E, K, idx, ev = _events()
    px, buy, cost, dates, raw = K.px.values, K.buy.values, K.cost.values, K.date.values, K.rawclose.values
    uq = K.amt20.groupby(K.date).rank(pct=True).values
    rr = K.px.groupby(K.ticker, sort=False).pct_change().clip(-0.5, 0.5)
    liq = (pd.Series(uq, index=K.index).groupby(K.ticker, sort=False).shift(1) >= 0.6).fillna(False)
    EW = (1 + rr[liq].groupby(K.date[liq]).mean()).cumprod()
    ewd = np.array([str(x) for x in EW.index]); ewv = EW.values
    ewat = lambda d: ewv[max(np.searchsorted(ewd, str(d), "right") - 1, 0)]
    import FinanceDataReader as fdr
    ix_ = fdr.DataReader("US500", "2007-01-01"); ix_ = ix_[ix_.Close > 0]
    up = dict(zip(ix_.index.strftime("%Y%m%d"), (ix_.Close > ix_.Close.rolling(60).mean()).values))
    last = dates.max()
    R = []
    for t in E.ticker:
        ix = idx[t]
        if len(ix) <= 21:
            continue
        s = ix[20]; b0 = buy[s]
        if not (b0 == b0 and b0 > 0):
            continue
        e = ix[min(20 + 250, len(ix) - 1)]
        done = len(ix) > 21 + 250 or dates[ix[-1]] < last
        if not done:
            continue
        r = (px[e] / b0 - 1) * 100 - cost[s]
        R.append(dict(d=dates[s], r=r, ex=r - (ewat(dates[e]) / ewat(dates[s]) - 1) * 100,
                      f20=(px[s] / px[ix[0]] - 1) * 100, uq=uq[s], price=raw[s], up=bool(up.get(dates[s], True))))
    Z = pd.DataFrame(R)
    O = ["# 미국 분사주 — 어떤 경우에 더 좋은가 · %s" % time.strftime("%Y-%m-%d"), "",
         "끝난 거래 %d건 · 고정 250일 · 초과 = 같은 구간 유니버스 동일가중 대비. **설명용 — 여기서 조건을 고르지 않는다.**" % len(Z), ""]

    def tab(title, col, bins, labels):
        Z["_b"] = pd.cut(Z[col], bins, labels=labels)
        O.extend(["## " + title, "", "| 구간 | n | 초과 중앙 | 초과 평균 | 수익 중앙 | 승률 |", "|---|---|---|---|---|---|"])
        for lb, g in Z.groupby("_b"):
            if len(g):
                O.append("| %s | %d | %+.1f%%p | %+.1f%%p | %+.1f%% | %.0f%% |" % (lb, len(g), g.ex.median(), g.ex.mean(), g.r.median(), (g.r > 0).mean() * 100))
        O.append("")
    tab("첫 20일 수익(상장가 → 매수 직전)", "f20", [-1000, -15, 0, 15, 1000], ["-15% 이하", "-15~0%", "0~15%", "+15% 이상"])
    tab("매수 시점 거래대금 순위(그날 전 종목 중)", "uq", [0, 0.4, 0.7, 0.9, 1.01], ["하위 40%", "40~70%", "70~90%", "상위 10%"])
    tab("주가 수준", "price", [0, 10, 30, 1e9], ["$10 미만", "$10~30", "$30 이상"])
    Z["upn"] = Z.up.astype(int)
    tab("S&P500 국면(매수일)", "upn", [-1, 0.5, 2], ["60일선 아래(하락)", "60일선 위(상승)"])
    log_trials("spinoff_filter_%s" % time.strftime("%Y%m%d"), 14)
    rp = ROOT / "reports" / ("spinoff_filter_%s.md" % time.strftime("%Y%m%d"))
    rp.write_text("\n".join(O) + "\n", encoding="utf-8")
    print("\n".join(O))


if __name__ == "__main__":
    main()
