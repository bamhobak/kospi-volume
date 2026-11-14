# -*- coding: utf-8 -*-
"""2026-11-14 portfolio.py 를 RAM 10GB 안에서 돌리기 위한 가는 패널 — panel_kp.pkl(3GB)·panel_kq.pkl(4.3GB)에서
portfolio.py 소스에 이름이 나오는 열만(보유 수익 열 n숫자는 n10 만 — portfolio 는 청산가를 종가로 직접 셈 · KB 만 n10), 실수는 float32 로 data/slim/ 에 저장(원본은 안 건드림).
portfolio.py 를 통째로 exec 하면 16.8GB 였다(11-14 acct_mix 사고). 쓰는 법:  PANEL_KP=slim/panel_kp.pkl PANEL_KQ=slim/panel_kq.pkl
11-14 저녁: 열을 골라 복사하면 패널이 두 벌(코스닥 11.6GB) → 그 자리에서 지우고 열마다 바꾼다. slim2_panels 단계도 여기로 합침.
    python research/memguard.py research/slim_panels.py kp     (한 번에 하나씩)
    python research/memguard.py research/slim_panels.py kq"""
import re, sys, gc, time
from pathlib import Path
import numpy as np, pandas as pd
BASE = Path(__file__).resolve().parent.parent
if sys.stdout is not None: sys.stdout.reconfigure(encoding="utf-8")
which = sys.argv[1]
src = (BASE / "portfolio.py").read_text(encoding="utf-8")
toks = set(re.findall(r"[A-Za-z_가-힣][A-Za-z0-9_가-힣]*", src))
KEEP0 = {"ticker", "date", "name", "close", "open", "high", "low", "buy", "cost", "marcap", "amt20", "n10"}
t0 = time.time()
K = pd.read_pickle(BASE / "data" / ("panel_%s.pkl" % which))
n0 = K.shape[1]
drop = [c for c in K.columns if not ((c in toks or c in KEEP0) and not (re.fullmatch(r"n\d+", str(c)) and c != "n10"))]
K.drop(columns=drop, inplace=True); gc.collect()
for c in list(K.columns):
    if K[c].dtype == np.float64:
        K[c] = K[c].astype(np.float32); gc.collect()
print("%s: 열 %d → %d · 행 %d · %.0f MB · %.1f분" % (which, n0, K.shape[1], len(K), K.memory_usage(deep=True).sum() / 1e6, (time.time() - t0) / 60), flush=True)
(BASE / "data" / "slim").mkdir(exist_ok=True)
K.to_pickle(BASE / "data" / "slim" / ("panel_%s.pkl" % which))
print("저장 %.1f분" % ((time.time() - t0) / 60))
