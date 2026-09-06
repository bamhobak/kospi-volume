# -*- coding: utf-8 -*-
"""2005~2026 연도별 시장 구조 스캔 — 사건의 흔적이 데이터에 남아 있나.

보려는 것: 상장 종목 수 · 외국인 보유율 · 공매도 비중과 srd(공매도 감소) 조건 통과율 ·
하루 ±15% 넘는 날 비율(2015-06 가격제한폭 30% 확대) · 거래대금 · 코스피 연수익/변동성 ·
srd 를 쓰는 규칙 다섯의 연도별 신호 수(공매도 금지기와 겹치나).
"""
import io, sys, warnings; warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import numpy as np, pandas as pd, os
from pathlib import Path
BASE = Path(".")
os.environ.update(IX_FROM="2004-06-01", DART_FROM="20040101", PANEL_KP="panel_kp.pkl", PANEL_KQ="panel_kq.pkl")
src = (BASE/"portfolio.py").read_text(encoding="utf-8"); ns = {"__file__": str((BASE/"portfolio.py").resolve())}
real = sys.stdout; sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
exec(compile(src.split("# 신호를 한 표로 모은다")[0], "portfolio.py", "exec"), ns)
sys.stdout = real
KP, KQ, RULES, IX = ns["KP"], ns["KQ"], ns["RULES"], ns["IX"]
KP["_y"] = KP.date.str[:4]; KQ["_y"] = KQ.date.str[:4]
g = KP.groupby("ticker", sort=False); KP["_r1"] = (KP.close/g.close.shift(1)-1)*100
YRS = [str(y) for y in range(2005, 2027)]
ix = IX[IX.Close>0].copy(); ix["y"] = ix.index.year.astype(str)
iy = ix.groupby("y").Close.agg(["first","last"]); iy["ret"] = (iy["last"]/iy["first"]-1)*100
iv = ix.Close.pct_change().groupby(ix.y).std()*np.sqrt(252)*100
print(f"{'해':<5}{'코스피':>7}{'변동성':>6}{'종목수':>6}{'외인보유%':>8}{'공매도비중%':>9}{'srd통과%':>8}{'±15%일%':>8}{'거래대금중앙(억)':>12}{'신용(KIS)%':>10}")
print("-"*86)
for y in YRS:
    A = KP[KP._y==y]
    sr = A.short_ratio.astype(float) if "short_ratio" in A.columns else pd.Series(dtype=float)
    fr = A.foreign_ratio.astype(float) if "foreign_ratio" in A.columns else pd.Series(dtype=float)
    cr = A.cr_chg20 if "cr_chg20" in A.columns else pd.Series(dtype=float)
    print(f"{y:<5}{iy.ret.get(y, float('nan')):>+6.0f}%{iv.get(y, float('nan')):>5.0f}%{A.ticker.nunique():>6}"
          f"{fr.mean() if fr.notna().any() else float('nan'):>8.1f}{sr.mean() if sr.notna().any() else float('nan'):>9.2f}"
          f"{(A.srd==True).mean()*100:>7.0f}%{(A._r1.abs()>15).mean()*100:>7.2f}%{A.amt20.median():>12.1f}"
          f"{cr.notna().mean()*100 if len(cr) else 0:>9.0f}%")

print("\nsrd(공매도 감소) 조건을 쓰는 규칙의 월별 신호 — 공매도 금지기 전후")
BANS = [("2008.10~2009.5 전면금지", "200807", "200912"), ("2011.8~11 금지", "201105", "201202"),
        ("2020.3~2021.4 금지", "202001", "202108"), ("2023.11~2025.3 금지", "202308", "202506")]
rules = {"P3":"폭락반등","P4":"업종붕괴","P2":"조정매집","D1":"낙폭과대","D2":"저PBR"}
for nm, lo, hi in BANS:
    print(f"  [{nm}]")
    months = [m for m in sorted(set(KP.date.str[:6])) if lo <= m <= hi]
    print("   " + " ".join(f"{m[2:]:>6}" for m in months))
    for rid, rn in rules.items():
        K = RULES[rid][0]; c = RULES[rid][5].fillna(False)
        mo = K.date.str[:6]; cnt = K[c].groupby(mo[c]).size()
        print(f"   {rn:<5}" + " ".join(f"{cnt.get(m,0):>6}" for m in months)[6:])
    A = KP[KP.date.str[:6].isin(months)]
    s = (A.srd==True).groupby(A.date.str[:6]).mean()*100
    print("   srd%  " + " ".join(f"{s.get(m,0):>5.0f}%" for m in months)[6:])
