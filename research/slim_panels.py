# -*- coding: utf-8 -*-
"""2026-11-14 portfolio.py 를 RAM 6GB 안에서 돌리기 위한 가는 패널 — panel_kp.pkl(3GB)·panel_kq.pkl(4.3GB)에서
portfolio.py 소스에 이름이 나오는 열 + 보유 수익 열(n숫자)만 남겨 data/slim/ 에 저장한다(원본은 안 건드림).
portfolio.py 를 통째로 exec 하면 16.8GB 였다(11-14 acct_mix 사고). 쓰는 법:  PANEL_KP=slim/panel_kp.pkl PANEL_KQ=slim/panel_kq.pkl
    python research/slim_panels.py kp     (한 번에 하나씩 — 패널 하나 읽는 데 4~5GB)
    python research/slim_panels.py kq"""
import re, sys, gc, time
from pathlib import Path
import pandas as pd
BASE = Path(__file__).resolve().parent.parent
sys.stdout.reconfigure(encoding="utf-8")
which = sys.argv[1]
src = (BASE / "portfolio.py").read_text(encoding="utf-8")
toks = set(re.findall(r"[A-Za-z_가-힣][A-Za-z0-9_가-힣]*", src))
t0 = time.time()
K = pd.read_pickle(BASE / "data" / ("panel_%s.pkl" % which))
cols = [c for c in K.columns if c in toks or re.fullmatch(r"n\d+", str(c)) or c in ("ticker", "date", "name", "close", "open", "high", "low", "buy", "cost", "marcap", "amt20")]
print("%s: 원래 열 %d → %d · 행 %d · %.0f MB → " % (which, K.shape[1], len(cols), len(K), K.memory_usage(deep=True).sum() / 1e6), end="", flush=True)
K = K[cols].copy(); gc.collect()
print("%.0f MB · 빠진 열 예: %s" % (K.memory_usage(deep=True).sum() / 1e6, ""), flush=True)
(BASE / "data" / "slim").mkdir(exist_ok=True)
K.to_pickle(BASE / "data" / "slim" / ("panel_%s.pkl" % which))
print("저장 %.1f분 · 열: %s" % ((time.time() - t0) / 60, ", ".join(map(str, cols))))
