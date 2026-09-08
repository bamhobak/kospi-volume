# -*- coding: utf-8 -*-
"""장기 규칙 탐색용 준비 — 패널에 없는 장기 수익 컬럼(n120·n180·n250)을 만들어 캐시한다.

패널(panel_*.pkl)은 n1~n60 까지만 갖고 있다. 사용자 요청(2026-09-08)으로 장기 규칙을
찾으려면 더 먼 수익이 필요하다. 패널 전체를 다시 쓰면 무겁고 위험하므로 **별도 캐시**로
빼둔다: data/long_ret_kp.pkl · data/long_ret_kq.pkl (ticker·date·n120·n180·n250).

수익 정의는 패널과 똑같이 맞춘다 — 매수는 **다음날 시가**(buy), 청산은 h 거래일 뒤 종가,
왕복비용(cost) 차감. 다르게 재면 기존 규칙과 나란히 놓을 수 없다.
"""
import io, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd

BASE = Path(__file__).parent
HS = [120, 180, 250]

for f, tag in (("panel_kp.pkl", "kp"), ("panel_kq.pkl", "kq")):
    K = pd.read_pickle(BASE / "data" / f)
    K = K.sort_values(["ticker", "date"]).reset_index(drop=True)
    g = K.groupby("ticker", sort=False)
    out = K[["ticker", "date"]].copy()
    for h in HS:
        out[f"n{h}"] = (g.close.shift(-h) / K.buy - 1) * 100 - K.cost
    p = BASE / "data" / f"long_ret_{tag}.pkl"
    out.to_pickle(p)
    n = {h: int(out[f"n{h}"].notna().sum()) for h in HS}
    print(f"{tag}: {len(out):,}행 저장 {p.name} · 유효 " +
          " ".join(f"n{h}={v:,}" for h, v in n.items()))
