# -*- coding: utf-8 -*-
"""네이버 검색 관심도 — 시장 전체 10분위 · 우리 규칙 안 (2026-09-29, 제안 1번 '관심 없는 매집').

① 시장 전체: 거래대금 상위 40% · 검색이 원래 있는 종목(앞 1년 0인 날 20% 이하) 안에서, 그날 att 10분위별
   20·60일 수익 중앙 − 같은 날 유니버스 중앙(%p). 2016-12~ · 학습(~2022)·검증(2023~) 따로. att7 도 본다.
   이미 확인된 회피 신호(로또주·이상 거래량 — 관심이 몰린 종목은 나쁘다)의 반대편(관심 없음)이 좋은가.
② 우리 규칙 안: rule_scan.scan(같은 규칙·같은 달 위/아래 절반) — att 가 우리가 산 종목을 가르나(필터 재료).

    python research/att_scan.py
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
    A = A[["ticker", "date", "uni", "n20", "n60"]].merge(N, on=["ticker", "date"], how="inner")
    A = A[A.uni & (A.zfrac <= 0.2)]
    O = ["# 네이버 검색 관심도 · %s" % time.strftime("%Y-%m-%d"), "",
         "att = 최근 28일 검색량 ÷ 그 앞 1년 평균(1 미만 = 관심이 식음). 대상 = 거래대금 상위 40%% · 검색이 원래 있는 종목. %s행." % f"{len(A):,}", ""]
    for col in ("att", "att7"):
        A["q"] = A.groupby("date")[col].rank(pct=True).mul(10).clip(upper=9.999).astype(int)
        for h in (20, 60):
            c = "n%d" % h
            A["ex"] = A[c] - A.groupby("date")[c].transform("median")
            O += ["## ① %s 10분위 · %d일 (같은 날 유니버스 대비 %%p, 중앙)" % (col, h), "",
                  "| 분위(1=관심 가장 식음) | 전체 16-12~ | 학습 ~22 | 검증 23~ | 음수 해 |", "|---|---|---|---|---|"]
            for q in range(10):
                z = A[A.q == q].dropna(subset=["ex"])
                ys = z.groupby(z.date.str[:4]).ex.median()
                O.append("| %d | %+.2f | %+.2f | %+.2f | %d/%d |" % (q + 1, z.ex.median(), z[z.date <= "20221231"].ex.median(),
                                                                z[z.date >= "20230101"].ex.median(), (ys < 0).sum(), len(ys)))
            O.append("")
    # ② 우리 규칙 안
    S = RS.kr_signals()
    S = S[["date", "ticker", "rid", "r"]].merge(N, on=["ticker", "date"], how="left")
    S = S[(S.zfrac <= 0.2) | S.zfrac.isna()]
    O += ["## ② 우리 규칙 안 — 같은 규칙·같은 달 위 절반 − 아래 절반(거래 수익 중앙 %p)", "",
          "| 재료 | 신호 | 묶음 | D | 95% 구간 | 학습 | 검증 | 규칙 같은방향 | 규칙별 D | 통과 |", "|---|---|---|---|---|---|---|---|---|---|"]
    rng = np.random.default_rng(0)
    for col in ("att", "att7"):
        x = RS.scan(S, col, rng)
        if not x:
            O.append("| %s | 표본 부족 | | | | | | | | |" % col); continue
        O.append("| %s | %s | %d | %+.2f | %+.2f ~ %+.2f | %+.2f | %+.2f | %d/%d | %s | %s |" % (
            col, f"{x['n']:,}", x["groups"], x["D"], x["lo"], x["hi"], x["dtr"], x["dva"], x["same"], x["nr"],
            " ".join("%s%+.1f" % (k, v) for k, v in sorted(x["per"].items())), "✅" if x["ok"] else ""))
    O += ["", "D 가 음수면 '관심 낮은 쪽이 더 좋다'. 규칙 신호는 2016-12 이후만 관심도가 있다."]
    log_trials("att_scan_%s" % time.strftime("%Y%m%d"), 42)
    rp = ROOT / "reports" / ("att_scan_%s.md" % time.strftime("%Y%m%d"))
    rp.write_text("\n".join(O) + "\n", encoding="utf-8")
    print("\n".join(O))


if __name__ == "__main__":
    main()
