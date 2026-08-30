# -*- coding: utf-8 -*-
"""스윙매매 기법 실측 — 3단계: 기준선 · 손절/익절/트레일링 · 보유기간 · 조합"""
import io, sys, time
import numpy as np, pandas as pd
exec(open("swing_test.py", encoding="utf-8").read().split("LIQ = ")[0])   # 데이터·simulate·stat 재사용
LIQ = (D.amt20 >= 10) & (D.srd.notna())

def rows(title, items, **kw):
    print(f"\n## {title}\n"); print(HDR)
    for lab, m in items:
        row(lab, simulate(m.values if hasattr(m, "values") else m, **kw))

# ═══ 기준선 ════════════════════════════════════════════════
print("## ⓪ 기준선 — 조건 없이 아무 날 아무 종목 (비용 차감 후)\n"); print(HDR)
base = LIQ.values
for h in (5, 10, 20, 40):
    row(f"{h}거래일 보유", simulate(base, hold=h))
print("\n→ 위 숫자가 '기법이 넘어야 할 선'입니다. 코스피가 오른 기간이라 기준선도 플러스입니다.\n")

# ═══ 손절·익절·트레일링 ════════════════════════════════════
SET = {
    "저점반등(120일저점+5%·거래량3배·양봉)": (LIQ & (D.fromlo120 <= 0.05) & (D.vr20 >= 3) & (D.body > 1)).values,
    "거래량5배+양봉": (LIQ & (D.vr20 >= 5) & (D.body > 0)).values,
    "60일 전고점 돌파+거래량2배": (LIQ & D.brk60 & (D.vr20 >= 2)).values,
    "급등후 20일선 눌림": (LIQ & (D.run20 >= 20) & (D.near20 <= 0.03)).values,
}
for nm, m in SET.items():
    print(f"\n## 청산 규칙 — {nm}\n"); print(HDR)
    for lab, kw in [("규칙 없음 (10일)", dict(hold=10)),
                    ("손절 -5%", dict(hold=10, stop=-5)), ("손절 -8%", dict(hold=10, stop=-8)),
                    ("손절 -12%", dict(hold=10, stop=-12)),
                    ("손절 ATR×2", dict(hold=10, stop_atr=2)), ("손절 ATR×3", dict(hold=10, stop_atr=3)),
                    ("익절 +10%", dict(hold=10, target=10)), ("익절 +20%", dict(hold=10, target=20)),
                    ("손절-8% 익절+15%", dict(hold=10, stop=-8, target=15)),
                    ("트레일링 -7%", dict(hold=20, trail=7)), ("트레일링 -10%", dict(hold=20, trail=10)),
                    ("트레일링 -10% (40일)", dict(hold=40, trail=10))]:
        row(lab, simulate(m, **kw))

# ═══ 보유기간 ══════════════════════════════════════════════
print("\n## 보유기간별 (저점반등 기본형)\n"); print(HDR)
for h in (3, 5, 10, 20, 40, 60):
    row(f"{h}거래일", simulate(SET["저점반등(120일저점+5%·거래량3배·양봉)"], hold=h))

# ═══ 저점반등에 조건 쌓기 ══════════════════════════════════
B = LIQ & (D.fromlo120 <= 0.05) & (D.vr20 >= 3) & (D.body > 1)
rows("저점반등 + 추가 조건 (20일 보유)", [
    ("기본형", B),
    ("+ 외국인 5일 순매수 2%↑", B & (D.fw5 >= 2)),
    ("+ 외국인 20일 순매수 1%↑", B & (D.fw20 >= 1)),
    ("+ 공매도 감소", B & (D.srd == True)),
    ("+ 코스피 60일선 아래", B & (~D.K60)),
    ("+ 코스피 60일선 위", B & D.K60),
    ("+ 아랫꼬리 30%↑", B & (D.lwick >= 0.3)),
    ("+ 종가 상단(0.6↑)", B & (D.clpos >= 0.6)),
    ("+ 증자·CB 없음", B & (~D.dil)),
    ("전부 결합(외인20일+공매도+60일선아래+증자없음)", B & (D.fw20 >= 1) & (D.srd == True) & (~D.K60) & (~D.dil)),
], hold=20)

# ═══ 거래량 폭발을 '되돌림 후'로 바꾸면 ════════════════════
V5 = LIQ & (D.vr20 >= 5) & (D.body > 0)
sh = lambda col, n: D.groupby("ticker")[col].shift(n)
rows("거래량 폭발 '당일 추격' vs '되돌림 대기' (10일 보유)", [
    ("당일 추격 (거래량5배 양봉 당일)", V5),
    ("3일 뒤 진입", (sh("vr20", 3) >= 5) & (sh("body", 3) > 0) & LIQ),
    ("5일 뒤 진입", (sh("vr20", 5) >= 5) & (sh("body", 5) > 0) & LIQ),
    ("5일 뒤 + 그사이 눌림(-5%↓)", (sh("vr20", 5) >= 5) & (sh("body", 5) > 0) & LIQ & (D.ret5 <= -5)),
    ("10일 뒤 + 눌림(-10%↓)", (sh("vr20", 10) >= 5) & (sh("body", 10) > 0) & LIQ & (D.ret10 <= -10)),
    ("10일 뒤 + 20일선 지지(±3%)", (sh("vr20", 10) >= 5) & (sh("body", 10) > 0) & LIQ & (D.near20 <= 0.03)),
], hold=10)
log("완료")
