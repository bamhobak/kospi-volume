# -*- coding: utf-8 -*-
"""미국 분사주 견고성 (2026-09-29, spinoff.py 후속).

spinoff.py: 상장 21일째 매수 · 250일 보유가 같은 날 아무거나 대비 +9.7%p(세 구간 +9.9/+10.5/+12.2). 운인지 가른다.
  ① 매수 시점 11·21·41·61일째 × 보유 120·250일 — 이웃 칸도 같은 방향인가
  ② 연도별(상장 해) 초과 — 한두 해가 만든 건가
  ③ 대조군: 같은 기간 패널에 **처음 나타난 다른 종목**(IPO·스팩·이전상장 등, 분사 아님) 같은 잣대 — 신규 상장주 공통 현상인가
  ④ 1년이 안 찬 2023~ 보유는 뺀 판(끝난 거래만)
판정(미리 정함): ①이웃 칸 과반이 +3%p↑ · ② 양수 해 60%↑ · ③ 대조군보다 확실히 높음 · ④ 끝난 거래만으로도 유지.

    python research/spinoff2.py
"""
import io, json, re, sys, time, zipfile, contextlib, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(BASE)); sys.path.insert(0, str(ROOT))
from verdict import log_trials

def log(m):
    print("%s %s" % (time.strftime("%H:%M:%S"), m), file=sys.stderr, flush=True)


src = (ROOT / "spinoff.py").read_text(encoding="utf-8")
# 사건 찾기 부분만 재사용 — main() 앞부분을 함수로 떼어 쓴다
body = src.split("def main():", 1)[1].split('    uq = K.amt20.groupby', 1)[0]
exec("def _events():\n" + body.replace("    sys.stdout.reconfigure(encoding=\"utf-8\")\n", "") + "    return E, K, idx, ev\n")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    E, K, idx, ev = _events()
    px, buy, cost = K.px.values, K.buy.values, K.cost.values
    dates = K.date.values; last_date = dates.max()
    uq = K.amt20.groupby(K.date).rank(pct=True)
    BEN = {}
    for h in (120, 250):
        fut = K.groupby("ticker", sort=False).px.shift(-h)
        r = (fut / K.buy - 1) * 100
        BEN[h] = r[uq >= 0.6].groupby(K.date[uq >= 0.6]).median()
    first = K.groupby("ticker").date.first()
    spin = set(E.ticker)
    ctrl = [t for t, f in first.items() if f > "20080101" and t not in spin]

    def trades(tks, k, h, only_done=False):
        out = []
        for t in tks:
            ix = idx[t]
            if len(ix) <= k:
                continue
            s = ix[k - 1]; e = ix[min(k - 1 + h, len(ix) - 1)]
            done = len(ix) > k + h or dates[ix[-1]] < last_date     # 끝남 = 보유기간 채움 또는 중간 폐지
            if only_done and not done:
                continue
            b = buy[s]
            if not (b == b and b > 0):
                continue
            out.append((dates[s], (px[e] / b - 1) * 100 - cost[s]))
        X = pd.DataFrame(out, columns=["date", "r"])
        X["bm"] = X.date.map(BEN[h])
        X["ex"] = X.r - X.bm
        return X

    O = ["# 미국 분사주 견고성 · %s" % time.strftime("%Y-%m-%d"), "",
         "분사주 %d건 · 대조군(같은 기간 처음 나타난 비분사 종목) %d건. 초과 = 수익 − 같은 날 유동성 상위 40%% 아무거나 중앙(%%p, 중앙값)." % (len(E), len(ctrl)), "",
         "## ① 매수 시점 × 보유", "", "| 매수 | 보유 | 분사주 n | 분사주 초과 중앙 | 승률(초과>0) | 대조군 초과 중앙 | 끝난 거래만 분사주 초과 |", "|---|---|---|---|---|---|---|"]
    cells = 0
    for k in (11, 21, 41, 61):
        for h in (120, 250):
            X = trades(E.ticker, k, h); Cx = trades(ctrl, k, h); D = trades(E.ticker, k, h, True)
            cells += 1
            O.append("| %d일째 | %d일 | %d | **%+.1f** | %.0f%% | %+.1f | %+.1f (n%d) |" % (
                k, h, len(X), X.ex.median(), (X.ex > 0).mean() * 100, Cx.ex.median(), D.ex.median(), len(D)))
    X = trades(E.ticker, 21, 250, True)
    X["y"] = X.date.str[:4]
    ys = X.groupby("y").ex.agg(["size", "median"])
    O += ["", "## ② 연도별 (21일째 매수 · 250일 · 끝난 거래만)", "", "| 해 | n | 초과 중앙 |", "|---|---|---|"]
    O += ["| %s | %d | %+.1f |" % (y, r["size"], r["median"]) for y, r in ys.iterrows()]
    O += ["", "양수 해 %d/%d · 건수 5건↑ 해만: %d/%d" % ((ys["median"] > 0).sum(), len(ys),
                                               (ys[ys["size"] >= 5]["median"] > 0).sum(), (ys["size"] >= 5).sum())]
    log_trials("spinoff2_%s" % time.strftime("%Y%m%d"), cells)
    rp = ROOT / "reports" / ("spinoff2_%s.md" % time.strftime("%Y%m%d"))
    rp.write_text("\n".join(O) + "\n", encoding="utf-8")
    print("\n".join(O))


if __name__ == "__main__":
    main()
