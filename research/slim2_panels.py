# -*- coding: utf-8 -*-
"""2026-11-14 가는 패널 2차 — data/slim/panel_*.pkl 에서 n숫자 보유 수익 열은 n10 만 남기고(portfolio.py 는 청산가를 종가로 직접 셈 · KB 만 n10),
실수 열을 float32 로. 6GB 안에서 portfolio.py 를 돌리려고. 원본(data/panel_*.pkl)은 안 건드림.
    python research/slim2_panels.py kp   /   kq"""
import re, sys, gc
from pathlib import Path
import numpy as np, pandas as pd
BASE = Path(__file__).resolve().parent.parent
sys.stdout.reconfigure(encoding="utf-8")
w = sys.argv[1]; f = BASE / "data" / "slim" / ("panel_%s.pkl" % w)
K = pd.read_pickle(f); m0 = K.memory_usage(deep=True).sum() / 1e6
K = K.drop(columns=[c for c in K.columns if re.fullmatch(r"n\d+", str(c)) and c != "n10"])
for c in K.columns:
    if K[c].dtype == np.float64: K[c] = K[c].astype(np.float32)
gc.collect()
print("%s %.0f MB → %.0f MB · 열 %d" % (w, m0, K.memory_usage(deep=True).sum() / 1e6, K.shape[1]), flush=True)
K.to_pickle(f)
