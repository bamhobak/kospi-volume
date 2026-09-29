# -*- coding: utf-8 -*-
"""관심도 후속 (2026-09-29) — att_scan 에서 '관심 쏠림(상위 10~20%%)은 60일 -5%%p, 11/11해 음수' 가 나왔다.
① 이게 '이미 많이 올랐다/거래량이 터졌다' 의 대리일 뿐인가: ret20·거래량(vm3) 5분위 칸 안에서 att 상위 10%% − 나머지.
② 우리 규칙이 산 종목 중 그날 att 가 시장 상위 10%%/20%% 인 신호는 나쁜가(규칙별 거래 수익 중앙).

    python research/att_scan2.py
"""
import sys, time, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(BASE)); sys.path.insert(0, str(ROOT))
import run_spec as R
import rule_scan as RS
from verdict import log_trials


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    N = pd.read_pickle(ROOT / "cache" / "naver_att.pkl")
    A, uni, since = R.load_market("KR")
    A["uni"] = uni.values
    A = A[["ticker", "date", "uni", "n20", "n60", "ret20", "vm3"]].merge(N, on=["ticker", "date"], how="inner")
    A = A[A.zfrac <= 0.2]
    # 그날 시장(검색 있는 종목 전체) 안 att 백분위 — 규칙 신호에도 이 값을 붙인다
    A["attp"] = A.groupby("date").att.rank(pct=True)
    U = A[A.uni].dropna(subset=["ret20", "vm3", "att"]).copy()
    O = ["# 관심도 후속 · %s" % time.strftime("%Y-%m-%d"), ""]
    O += ["## ① 오른 폭·거래량 통제 — ret20 5분위 × vm3 5분위 칸 안에서 att 상위 10% − 나머지 (60일 %p, 칸 가중)", "",
          "| 구간 | 칸 | 차이 | 음수 칸 비율 | 해별(음수 해) |", "|---|---|---|---|---|"]
    U["rq"] = U.groupby("date").ret20.rank(pct=True).mul(5).clip(upper=4.999).astype(int)
    U["vq"] = U.groupby("date").vm3.rank(pct=True).mul(5).clip(upper=4.999).astype(int)
    U["top"] = U.groupby("date").att.rank(pct=True) > 0.9
    U = U.dropna(subset=["n60"])
    for lab, z in (("전체 16-12~", U), ("학습 ~22", U[U.date <= "20221231"]), ("검증 23~", U[U.date >= "20230101"])):
        rows = []
        for (y, rq, vq), g in z.groupby([z.date.str[:4], "rq", "vq"]):
            a, b = g[g.top], g[~g.top]
            if len(a) >= 30 and len(b) >= 30:
                rows.append((y, a.n60.median() - b.n60.median(), len(a)))
        G = pd.DataFrame(rows, columns=["y", "d", "w"])
        yy = G.groupby("y").apply(lambda g: np.average(g.d, weights=g.w))
        O.append("| %s | %d | %+.2f | %.0f%% | %d/%d |" % (lab, len(G), np.average(G.d, weights=G.w), (G.d < 0).mean() * 100,
                                                         (yy < 0).sum(), len(yy)))
    O.append("")
    # ② 우리 규칙 안
    S = RS.kr_signals()[["date", "ticker", "rid", "r"]]
    S = S.merge(A[["ticker", "date", "attp"]], on=["ticker", "date"], how="left")
    S = S[S.date >= "20161201"]
    O += ["## ② 우리 규칙 신호 — 그날 시장 관심 상위 N% 에 든 신호 vs 나머지 (거래 수익 중앙 %)", "",
          "| 규칙 | 신호(관심값 있음) | 상위10% 건수 | 상위10% 중앙 | 상위20% 건수 | 상위20% 중앙 | 나머지 중앙 | 나머지 승률 | 상위20% 승률 |",
          "|---|---|---|---|---|---|---|---|---|"]
    for rid, g in list(S.groupby("rid")) + [("전체", S)]:
        g = g.dropna(subset=["attp"])
        t10, t20, rest = g[g.attp > 0.9], g[g.attp > 0.8], g[g.attp <= 0.8]
        f = lambda x: "%+.2f" % x.r.median() if len(x) else "-"
        w = lambda x: "%.0f%%" % ((x.r > 0).mean() * 100) if len(x) else "-"
        O.append("| %s | %d | %d | %s | %d | %s | %s | %s | %s |" % (rid, len(g), len(t10), f(t10), len(t20), f(t20), f(rest), w(rest), w(t20)))
    O += ["", "attp = 그날 검색이 원래 있는 종목 전체 중 att 백분위. 규칙 신호는 2016-12~만."]
    log_trials("att_scan2_%s" % time.strftime("%Y%m%d"), 12)
    rp = ROOT / "reports" / ("att_scan2_%s.md" % time.strftime("%Y%m%d"))
    rp.write_text("\n".join(O) + "\n", encoding="utf-8")
    print("\n".join(O))


if __name__ == "__main__":
    main()
