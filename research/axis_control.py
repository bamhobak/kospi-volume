# -*- coding: utf-8 -*-
"""**축 스캔 통제 점검** — 계단이 '크고 조용한 종목' 효과의 다른 이름인지 가른다 (2026-09-19).

중앙값 잣대는 변동성 큰 종목에 구조적으로 불리하다(오른쪽 꼬리가 길수록 중앙값이 평균보다 낮다).
그래서 배당·이익수익률·공매도 비중·내부자 건수처럼 '대형·안정' 과 얽힌 축은 변동성·규모의 대리일 수 있다
(성승현 장대양봉이 변동성 대리였던 것과 같은 함정 — [[rejected-strategies]]).
여기서는 날짜별로 **변동성(vol20) 3등분 × 거래대금(amt20) 3등분 = 9칸** 안에서 따로 10등분해,
칸마다 계단 방향(ρ)이 살아 있는지 본다. 9칸 중 대부분에서 같은 방향이면 진짜 축이다.

    python research/axis_control.py divy ey sv_rto5 ins_b60 q_ofrgn5
"""
import sys, time, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(BASE)); sys.path.insert(0, str(ROOT))
import features as FT
from axis_scan import regime_down, spear, TR0, TR1, VA0

sys.stdout.reconfigure(encoding="utf-8")
names = sys.argv[1:]
A = pd.read_pickle(BASE / "data/kr_scan.pkl")
A = A[((A.close >= 1000) & (~A.pref.fillna(False))).fillna(False)]
cal = sorted(A.date.unique())
uni = (A.groupby("date").amt20.rank(pct=True) >= 0.60).fillna(False)
A = A[uni & (A.date >= TR0)].reset_index(drop=True)
FT.attach(A, names, cal=cal)
A["down"] = A.date.map(regime_down()).fillna(False).astype(bool)
A["vq"] = np.ceil(A.groupby("date").vol20.rank(pct=True) * 3).clip(1, 3)
A["aq"] = np.ceil(A.groupby("date").amt20.rank(pct=True) * 3).clip(1, 3)
print("| 재료 | 보유 | 국면 | 통제 전 ρ학습 | 9칸 중 같은 방향(학습) | 9칸 중 같은 방향(검증) | 9칸 ρ 중앙 | 판정 |")
print("|---|---|---|---|---|---|---|---|")
for col in names:
    for h in (5, 20):
        c = "n%d" % h
        for reg, m in (("전체", A.index == A.index), ("하락장", A.down.values)):
            z = A.loc[m, [col, "date", c, "vq", "aq"]].dropna()
            z["b"] = np.ceil(z.groupby(["date", "vq", "aq"])[col].rank(pct=True) * 10).clip(1, 10)
            tr = z[z.date <= TR1]; va = z[z.date >= VA0]
            base = spear(range(1, 11), tr.groupby("b")[c].median().reindex(range(1, 11)).values)
            rs_tr, rs_va = [], []
            for (v, a), g in tr.groupby(["vq", "aq"]):
                mm = g.groupby("b")[c].median()
                if len(mm) >= 8: rs_tr.append(spear(mm.index, mm.values))
            for (v, a), g in va.groupby(["vq", "aq"]):
                mm = g.groupby("b")[c].median()
                if len(mm) >= 8: rs_va.append(spear(mm.index, mm.values))
            s = np.sign(base)
            ktr = sum(1 for r in rs_tr if np.sign(r) == s and abs(r) >= 0.5)
            kva = sum(1 for r in rs_va if np.sign(r) == s and abs(r) >= 0.5)
            ok = ktr >= 7 and kva >= 5
            print("| %s | %d일 | %s | %+.2f | %d/%d | %d/%d | %+.2f | %s |" % (
                col, h, reg, base, ktr, len(rs_tr), kva, len(rs_va), np.median(rs_tr) if rs_tr else np.nan,
                "**축 살아있음**" if ok else "대리 지표"))
