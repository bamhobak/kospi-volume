# -*- coding: utf-8 -*-
"""사이트 [저PBR 낙폭](N3) 설명문 숫자를 보유 40일·60일로 다시 낸다 (2026-09-24 보유 60일 전환).

사이트 숫자와 같은 잣대를 쓴다 — us_verify.py(사이트 신호 건수와 대조한 정본)의 규칙 정의 · 생존 패널(us_scan) ·
2016~ · 한 종목 보유 중 재신호 무시. 40일로 사이트 숫자(1,544건 · 평균 +8.48%)가 재현되는지 먼저 본다.
    python n3_site_stats.py
"""
import sys, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd

BASE = Path(__file__).parent
SRC = (BASE / "us_verify.py").read_text(encoding="utf-8").split('sec("① 재구성 검증', 1)[0]
G = {"__name__": "uv", "__file__": str(BASE / "us_verify.py")}
exec(compile(SRC, "us_verify.py", "exec"), G)
sys.stdout.reconfigure(encoding="utf-8")
K, N3 = G["K"], G["N3"]


def dedup(cond, h, lo="20160101"):
    Z = K[cond].dropna(subset=[f"n{h}"]).copy()
    Z = Z[Z.buy > 0].sort_values("di")
    keep, last = [], {}
    for t, i, ix in zip(Z.ticker.values, Z.di.values, Z.index):
        if last.get(t, -10 ** 9) >= i:
            continue
        last[t] = i + h
        keep.append(ix)
    Z = Z.loc[keep]
    Z = Z[Z.date >= lo].copy()
    Z["r"] = Z[f"n{h}"].astype(float)
    return Z


for h in (40, 60):
    Z = dedup(N3, h)
    r = Z.r
    mo = Z.date.str[:6]
    last = mo.max()
    span = (int(last[:4]) - 2016) * 12 + int(last[4:]) - 1 + 1
    vc = mo.value_counts()
    up, dn = r[r > 0].sum(), -r[r < 0].sum()
    ys = Z.groupby(Z.date.str[:4]).r.mean()
    tr, va = Z[Z.date <= "20221231"].r, Z[Z.date >= "20230101"].r
    print(f"\n## 보유 {h}일 (2016~, 사이트 잣대)")
    print(f"n:{len(r)} perMonth:{len(r)/span:.0f} monthsActive:{mo.nunique()} spanMonths:{span} "
          f"medPerActive:{vc.median():.0f} topMonth:'{vc.index[0]}' topN:{vc.iloc[0]} win:{(r>0).mean()*100:.0f} "
          f"pf:{up/dn:.1f} avg:{r.mean():.2f}")
    print(f"중앙값 {r.median():+.2f}% · 학습(2016~22) 중앙 {tr.median():+.2f}% · 검증(2023~26) 중앙 {va.median():+.2f}% · "
          f"양수해 {(ys>0).sum()}/{len(ys)}")
    print("연도별 평균: " + " · ".join(f"{y} {v:+.1f}%" for y, v in ys.items()))
