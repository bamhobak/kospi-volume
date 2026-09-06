# -*- coding: utf-8 -*-
"""이미 만들어 둔 패널에 PBR 을 붙인다 — 패널을 17분 걸려 다시 만들지 않기 위해.

[저PBR 낙폭] 이 21년 검증에서 여섯 구간 전부 신호 0건이었다. 원인은 데이터가 없어서가 아니라
krx_daily.db 의 fundamental(2005~ · 1,195만 행)이 패널에 병합되지 않아서였다.
build_panel.py 는 고쳐 뒀고(다음 재생성부터 자동), 이번엔 기존 pkl 에 덧붙인다.
사용: python attach_pbr.py
"""
import io, sqlite3, sys
from pathlib import Path
import pandas as pd
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
BASE = Path(__file__).parent
con = sqlite3.connect(f"file:{BASE}/data/krx_daily.db?mode=ro", uri=True, timeout=600)
V = pd.read_sql("SELECT date, ticker, pbr AS PBR, per AS PER, bps AS BPS FROM fundamental", con)
con.close()
print(f"밸류에이션 {len(V):,}행 {V.date.min()}~{V.date.max()}")
for fn in ("panel_kp.pkl", "panel_kq.pkl"):
    f = BASE/"data"/fn
    df = pd.read_pickle(f)
    drop = [c for c in ("PBR","PER","BPS") if c in df.columns]
    if drop: df = df.drop(columns=drop)
    n = len(df)
    df = df.merge(V, on=["ticker","date"], how="left")
    assert len(df) == n, f"{fn}: 병합에서 행이 늘었다 — 키 중복"
    df["_y"] = df.date.str[:4]
    r = df.groupby("_y").PBR.apply(lambda s: s.notna().mean()*100)
    df = df.drop(columns=["_y"])
    df.to_pickle(f)
    print(f"  {fn}: {n:,}행 · PBR 유효율 " + " · ".join(f"{y}:{v:.0f}%" for y, v in r.items()))
