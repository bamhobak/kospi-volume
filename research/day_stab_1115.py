# -*- coding: utf-8 -*-
"""11-15 사용자 "데이 규칙 중 수익을 가장 안정적으로 뽑아주는 게 뭐지?" — decay_watch 날 바구니(연구 정의·비용 0.23 뒤·같은 금액)로 안정성 지표."""
import sys
from pathlib import Path
import numpy as np, pandas as pd
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import decay_watch as DW
S = DW.series()
NAME = {"T1": "[갭하락]", "T5": "[장전 되돌림]", "T6": "[장후 낙폭]"}
def stat(s, lab):
    s = s.dropna(); m = s.groupby(s.index.str[:6]).sum(); y = s.groupby(s.index.str[:4]).mean()
    allm = pd.period_range(pd.Period(s.index.min()[:6], "M"), pd.Period(s.index.max()[:6], "M"), freq="M").strftime("%Y%m")
    mm = m.reindex(allm).fillna(0)
    return "| %s | %s~%s | %.1f일 | %+.2f%% | %.0f%% | %d/%d (%.0f%%) | %+.1f%%p | %.2f | %d/%d | %s |" % (
        lab, s.index.min(), s.index.max(), len(s) / len(allm), s.mean(), (s > 0).mean() * 100, (mm > 0).sum(), len(mm), (mm > 0).mean() * 100,
        mm.min(), mm.mean() / mm.std() if mm.std() > 0 else np.nan, (y > 0).sum(), len(y), " ".join("%s %+.2f" % (k[2:], v) for k, v in y.items()))
print("| 규칙 | 기간 | 달마다 신호 날 | 날 바구니 평균 | 플러스 날 | 플러스 달 | 최악의 달(날 바구니 합) | 달 평균÷달 흔들림 | 플러스 해 | 해마다 날 바구니 평균 |")
print("|---|---|---|---|---|---|---|---|---|---|")
for r in ("T1", "T5", "T6"): print(stat(S[r], NAME[r] + " 전체"))
for r in ("T1", "T5", "T6"): print(stat(S[r][S[r].index >= "20250401"], NAME[r] + " 2025-04~(같은 창)"))
