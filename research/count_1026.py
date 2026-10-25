# -*- coding: utf-8 -*-
"""거래건수 변화 — 갭하락 장기하락 필터 · NXT 52주저점+신규 빼기 (2026-10-26)."""
import sys, time
from pathlib import Path
ROOT = Path(r'C:\vscode\kospi-volume\research'); BASE = ROOT.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / 'factory')); sys.path.insert(0, str(BASE))
sys.stdout.reconfigure(encoding='utf-8')
import numpy as np, pandas as pd
import lab

def cnt(z, lo):
    z = z[z.date >= lo]
    ny = z.date.str[:4].nunique()
    return len(z), len(z) / max(ny, 1), z.date.nunique()

print("=== 갭하락 조용주: 장기하락 필터 거래건수 ===")
H = lab.hist()
H = H[H.t1]
B = H[H.q_d120 <= 0.30]
for lo, nm in (("20160101", "2016~"), ("20230101", "2023~")):
    a = cnt(H, lo); b = cnt(B, lo)
    print(f"  {nm}: 전부 {a[0]}건(연 {a[1]:.0f}·{a[1]/252*100:.0f}% 날에) → 장기하락 {b[0]}건(연 {b[1]:.0f}) = {b[0]/a[0]*100:.0f}% 유지")

print("\n=== NXT: 52주저점 근처·신규상장 빼기 거래건수 ===")
# nxt_axis 재구성 간단판
sys.path.insert(0, str(ROOT))
import importlib.util
spec = importlib.util.spec_from_file_location("nxtax", str(ROOT / "nxt_axis_1026.py"))
m = importlib.util.module_from_spec(spec)
try:
    # build_Z 만 빌려 쓴다
    import types
    src = open(ROOT / "nxt_axis_1026.py", encoding="utf-8").read()
    g = {}
    exec(compile(src.split("def main")[0], "nxtax", "exec"), g)
    Z = g["build_Z"]()
    Hf = lab.hist()[["ticker", "date", "q_lo250", "age"]].rename(columns={"ticker": "t", "date": "d"})
    Z = Z.merge(Hf, on=["t", "d"], how="left")
    calm = Z.mkt > -1.0
    base = Z[(Z.rel <= -2.0) & calm & (Z.a10 >= 3e7)].copy()
    base["rk"] = base.groupby("d").rel.rank(method="first"); base = base[base.rk <= 10]
    keep = base[(base.q_lo250 > 0.30) & (base.age >= 250)]
    nd = base.d.nunique()
    print(f"  기준(안정신호 하루10): {len(base)}건 · 하루평균 {len(base)/nd:.1f} · 신호날 {nd}일")
    print(f"  저점근처(q_lo250<=0.3) {len(base[base.q_lo250<=0.3])}건 · 신규(age<250) {len(base[base.age<250])}건")
    print(f"  둘 다 빼면: {len(keep)}건 = {len(keep)/len(base)*100:.0f}% 유지 · 하루평균 {len(keep)/keep.d.nunique():.1f}")
    print(f"  수익(r_vw): 기준 건당 +{base.r_vw.mean():.2f}·승{(base.r_vw>0).mean()*100:.0f} → 필터 후 건당 +{keep.r_vw.mean():.2f}·승{(keep.r_vw>0).mean()*100:.0f}")
except Exception as e:
    import traceback; traceback.print_exc()
