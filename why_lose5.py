# -*- coding: utf-8 -*-
"""후보안 5단계 — 착시 걸러내기와 최근 해 확인.

4단계에서 '폭락반등 -25% + 낙폭과대 -30%' 가 12/12 시드로 이겼다(8.61→10.81배, 낙폭 -15→-14%).
그런데 신호를 줄이면 남은 자리에 돈이 더 몰려 '크게 걸어서 번' 착시가 생길 수 있다.
  ㉠ 투입비중을 통째로 x0.5 / x1.5 해도 순서가 유지되나 (유지되면 진짜 선별력)
  ㉡ 연도별 계좌 수익률 — 특히 2026년(사용자 기준: 최근 해에 지면 채택 불가)
사용: IX_FROM=2004-06-01 DART_FROM=20040101 PANEL_KP=panel_kp.pkl PANEL_KQ=panel_kq.pkl python why_lose5.py
"""
import io, os, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd

BASE = Path(__file__).parent
SEEDS = 12
src = (BASE/"portfolio.py").read_text(encoding="utf-8"); ns = {"__file__": str(BASE/"portfolio.py")}
real = sys.stdout; sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
exec(compile(src.split("# 신호를 한 표로 모은다")[0], "portfolio.py", "exec"), ns)
sys.stdout = real
KP, KQ, RULES = ns["KP"], ns["KQ"], ns["RULES"]
adates = sorted(set(KP.date) | set(KQ.date)); ADI = {d: i for i, d in enumerate(adates)}
rel = (BASE/"rules_relation.py").read_text(encoding="utf-8")
exec(rel[rel.index("def build(R):"):rel.index("S = build(RULES)")], globals())
exec(rel[rel.index("def sim(S, ds, seed):"):rel.index("ds = [d for d in adates")].replace(
     "return dict(nav=Cv.iloc[-1], mdd=dd.min(), byrid=byrid)",
     "return dict(nav=Cv.iloc[-1], mdd=dd.min(), byrid=byrid, curve=Cv)"), globals())

def variant(scale=1.0, **patch):
    R = {}
    for rid, (P, h, stop, pct, mx, cond) in RULES.items():
        R[rid] = (P, h, stop, pct*scale, mx, cond)
    for rid, (cond, hold) in patch.items():
        P, h0, stop, pct, mx, _ = R[rid]
        R[rid] = (P, hold or h0, stop, pct, mx, cond)
    return build(R)

TIGHT = {"P3": (RULES["P3"][5] & (KP.ret20 <= -25), None),
         "D1": (RULES["D1"][5] & (KQ.ret20 <= -30), None)}
ds_all = [d for d in adates if d >= "20050101"]

print("㉠ 투입비중 배율을 바꿔도 순서가 유지되나 (전체 21년 자산 배수 중앙값)")
print(f"  {'배율':<8}{'현행':>10}{'조인 안':>12}{'차이':>10}{'시드 승':>10}")
for sc in (0.5, 1.0, 1.5):
    A = [sim(variant(scale=sc), ds_all, k)["nav"] for k in range(SEEDS)]
    B = [sim(variant(scale=sc, **TIGHT), ds_all, k)["nav"] for k in range(SEEDS)]
    w = sum(b > a for a, b in zip(A, B))
    print(f"  x{sc:<7}{np.median(A):>9.2f}배{np.median(B):>11.2f}배{np.median(B)-np.median(A):>+9.2f}{w:>7}/{SEEDS}")

print("\n㉡ 연도별 계좌 수익률 (중앙값)")
RA = [sim(variant(), ds_all, k) for k in range(SEEDS)]
RB = [sim(variant(**TIGHT), ds_all, k) for k in range(SEEDS)]
yrs = np.array([d[:4] for d in ds_all])
print(f"  {'해':<6}{'현행':>9}{'조인 안':>10}{'차이':>9}")
na = nb = 0
for y in sorted(set(yrs)):
    idx = np.where(yrs == y)[0]; i0 = max(idx[0]-1, 0); i1 = idx[-1]
    a = np.median([(r["curve"].to_numpy()[i1]/r["curve"].to_numpy()[i0]-1)*100 for r in RA])
    b = np.median([(r["curve"].to_numpy()[i1]/r["curve"].to_numpy()[i0]-1)*100 for r in RB])
    na += a < 0; nb += b < 0
    print(f"  {y:<6}{a:>+8.1f}%{b:>+9.1f}%{b-a:>+8.1f}")
print(f"  지는 해: 현행 {na}개 · 조인 안 {nb}개")
