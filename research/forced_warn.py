# -*- coding: utf-8 -*-
"""시장경보(투자경고·투자위험) 지정 뒤 매물 소진 (2026-10-15) — H0347.

지정되면 신용 매수 막힘·위탁증거금 100%(위험은 지정 당일 거래정지 1일) → 단타·신용 자금이 기계적으로 빠진다.
지정일(KIND, data/krx_warn.pkl · collect_warn.py) 기준 k거래일째(0=지정일) 종가 매수 → 5·20·60일 보유, 같은 날 유니버스 대비 초과.
같은 종목이 60일 안에 다시 지정되면 첫 번째만. 지정 전 20일 수익(급등 크기)로도 나눔. 비용 0.43(0.23 + 미끄러짐 0.2).
    python research/forced_warn.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np, pandas as pd
import forced_kr as K

BASE = K.BASE


def main():
    A = K.load()
    A["r20"] = (A.close / A.groupby("ticker").close.shift(20) - 1) * 100
    W = pd.read_pickle(BASE / "data" / "krx_warn.pkl").dropna(subset=["ticker"])
    TI = A.groupby("ticker").indices; DT = A.date.to_numpy()
    K.P("# 시장경보 지정 뒤 — 경고 %d건 · 위험 %d건 (2007~)" % ((W.kind == "경고").sum(), (W.kind == "위험").sum()))
    rows = []
    for kind in ("경고", "위험"):
        ev = W[W.kind == kind].sort_values("date")
        for k in (0, 1, 3, 5, 10, 20):
            recs = []; lastd = {}
            for r in ev.itertuples():
                ii = TI.get(r.ticker)
                if ii is None: continue
                j = np.searchsorted(DT[ii], r.date)
                if j >= len(ii) or DT[ii[j]] != r.date and j == 0: pass
                if r.ticker in lastd and j - lastd[r.ticker] < 60: continue
                lastd[r.ticker] = j
                if j + k >= len(ii): continue
                i = ii[j + k]
                if A.bad.iat[i]: continue
                recs.append(dict(date=DT[i], x5=A.x_c5.iat[i] - K.CS, x20=A.x_c20.iat[i] - K.CS, x60=A.x_c60.iat[i] - K.CS, r20=A.r20.iat[ii[j]] if j < len(ii) else np.nan))
            R = pd.DataFrame(recs)
            if len(R): rows.append(("투자%s · 지정 %d일째 종가" % (kind, k), R))
    K.table("종목 단위 초과(비용 뒤): 20일 / 5일 / 60일 (칸: 건수 · 평균 · 승률 · t)", rows, ["x20", "x5", "x60"], ["20일", "5일", "60일"])
    # 급등 크기로 나눔 — 경고 5일째
    base = [z for nm, z in rows if nm == "투자경고 · 지정 5일째 종가"][0]
    sub = [("경고 5일째 · 지정 전 20일 +100%↑", base[base.r20 >= 100]), ("경고 5일째 · +50~100%", base[base.r20.between(50, 100)]), ("경고 5일째 · +50% 미만", base[base.r20 < 50])]
    K.table("지정 전 급등 크기별 — 경고 5일째 종가 매수 20일 / 60일 초과", sub, ["x20", "x60"], ["20일", "60일"])
    (BASE / "research" / "cache" / "forced_warn.out").write_text("\n".join(K.OUT), encoding="utf-8")


if __name__ == "__main__":
    main()
