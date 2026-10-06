# -*- coding: utf-8 -*-
"""국장 패널의 매매비용을 현행 세율로 맞춘다 (2026-10-07 사용자 '응').
build_panel 은 거래세를 0.15%(2025 세율)로 넣었는데 2026-01-01 부터 매도 세금은 0.20%(코스피 거래세 0.05+농특세 0.15 · 코스닥 0.20)이고
토스 수수료 0.015%×2 도 빠져 있었다 → 왕복 0.23%. 차이 +0.08%p 를 cost 에 더하고 선도수익 n{h}(=총수익 − cost)에서 뺀다.
패널을 처음부터 다시 만들면 뒤에 붙인 후처리(attach_pbr·fix_panels 등)를 다시 해야 해서 이 방식이 같은 결과를 더 안전하게 낸다.
두 번 적용 방지: df.attrs['tax_2026'] 표시.
    python patch_tax_2026.py
"""
import re, sys, time
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import pandas as pd
BASE = Path(__file__).parent
ADD = 0.08
for f in ("panel_kp.pkl", "panel_kq.pkl", "kr_scan.pkl"):   # kr_scan = 연구용 슬림 패널(같은 비용 열)
    p = BASE / "data" / f; t0 = time.time()
    d = pd.read_pickle(p)
    if d.attrs.get("tax_2026"):
        print(f, "이미 적용됨 — 건너뜀"); continue
    d["cost"] = d["cost"] + ADD
    for c in [c for c in d.columns if re.fullmatch(r"n\d+", c)]:
        d[c] = d[c] - ADD
    d.attrs["tax_2026"] = True
    tmp = p.with_suffix(".tmp"); d.to_pickle(tmp); tmp.replace(p)
    print(f, "cost 평균 %.3f · %.1f분" % (d.cost.mean(), (time.time() - t0) / 60), flush=True)
