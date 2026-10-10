# -*- coding: utf-8 -*-
"""VI 단일가 되돌림 (H0318, 2026-10-11 사용자 "이것들 실측해봐").

정적 VI: 기준가(시가·직전 단일가) 대비 ±10% 에 닿으면 2분 단일가 → 1분봉에 2분 넘는 구멍 + 다음 봉에 단일가 체결.
일봉으로 '저가 ≤ 시가×0.905' 인 날(하락 VI 가 났을 날)을 고르고, 그날 1분봉에서
  ① 저가가 시가×0.90 에 처음 닿은 봉 ② 그 뒤 2분 이상 빈 구멍 → VI 확인
  ③ 구멍 뒤 첫 봉 시가(단일가 체결가)에 매수 → 그날 종가(15:30 단일가) 매도, 비용 0.23%
소형주 이벤트 날 1분봉은 m1_event.ensure 로 받는다(받은/못 받은 수 적음).
학습 2022-12~2024 · 검증 2025~ (1분봉이 2022-12~).
    python research/vi_rebound.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / "factory"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np, pandas as pd
import lab, feats as FT, common as C
import m1_event as ME

U = lab.hist()
P = pd.read_pickle(C.CACHE / "factory_px.pkl")
U = U[U.date >= "20221201"].merge(P, on=["ticker", "date"])
ev = U[(U.low <= U.open * 0.905) & U.oc.notna()].copy()
print("하락 VI 났을 날(유니버스, 저가 ≤ 시가×0.905): %d건 · 종목 %d" % (len(ev), ev.ticker.nunique()), flush=True)
got, miss = ME.ensure("KR", list(zip(ev.ticker, ev.date)), log=lambda *a: print(*a, flush=True))
print("1분봉 받음 %d · 못 받음 %d" % (got, miss), flush=True)


def hm2m(s):
    return int(s[:2]) * 60 + int(s[2:])


rows = []
for t, g in ev.groupby("ticker"):
    B = ME.bars("KR", t, list(g.date))
    for r in g.itertuples():
        b = B.get(r.date)
        if b is None or len(b) < 30: rows.append(dict(ticker=t, date=r.date, st="1분봉 없음")); continue
        b = b[(b.hm >= "0901") & (b.hm <= "1531")].reset_index(drop=True)
        mins = b.hm.map(hm2m).values
        ref = b.o.iloc[0]                                             # 09:01 봉 시가 = 시가 단일가
        v = b.v.values; cc = b.c.values
        # 토스 1분봉은 거래 없는 분도 v=0 봉으로 채운다 → VI(2분 단일가) = 거래 이어지던 종목에 v=0 봉 2개↑ 연속 뒤 체결 봉
        found = None
        for i in range(4, len(b) - 3):
            if mins[i] > hm2m("1518"): break
            if v[i] == 0 and v[i + 1] == 0 and (v[i - 3:i] > 0).all():
                j = i + 2
                while j < len(b) and v[j] == 0: j += 1
                if j >= len(b) or j - i > 4: continue                     # 2~4분 정지만(긴 정지는 거래정지 등)
                drop = (b.l.values[i - 1] / max(cc[max(i - 11, 0):i].max(), b.h.values[max(i - 11, 0):i].max()) - 1) * 100
                if drop <= -3:
                    found = (i - 1, j, drop); break
        if not found: rows.append(dict(ticker=t, date=r.date, st="하락 VI 정지 없음")); continue
        i, j, drop = found
        ent = b.o.iloc[j]; ext = b.c.iloc[-1]
        lo_after = b.l.iloc[j:].min()
        rows.append(dict(ticker=t, date=r.date, st="VI", hm=b.hm[i], ent=ent, ext=ext, ref=ref, pc=r.px, drop=drop,
                         ret=(ext / ent - 1) * 100 - FT.COST, ret5=(b.c.iloc[min(j + 5, len(b) - 1)] / ent - 1) * 100 - FT.COST,
                         dd=(lo_after / ent - 1) * 100, ent_ref=(ent / ref - 1) * 100, gap=r.gap, q_vm=r.q_vm, liq=r.liq,
                         aj=(ent / b.c.values[i] - 1) * 100, oc=r.oc))
R = pd.DataFrame(rows)
R.to_pickle(C.CACHE / "vi_rebound.pkl")
print("판정:", dict(R.st.value_counts()), flush=True)
V = R[R.st == "VI"].copy()
V["t1"] = False
TR, VA = ("20221201", "20241231"), ("20250101", "20991231")


def f(s):
    return ("%5d %+6.2f %4.1f%% t%4.1f PF %.2f" % (s["n"], s["mean"], s["win"], s["t"], s["pf"] or 0)) if s else "    0      -"


def row(name, m):
    a = lab.stats(V[m & (V.date >= TR[0]) & (V.date <= TR[1])]); b = lab.stats(V[m & (V.date >= VA[0])])
    print("%-46s | 학습 %s | 검증 %s" % (name[:46], f(a), f(b)), flush=True)


al = pd.Series(True, index=V.index)
print("\n== VI 단일가 체결가 매수 → 종가 (비용 0.23)")
row("하락 VI 전체", al)
row("조용한 종목(어제 거래량배수 하위 30%)", V.q_vm <= 0.3)
row("유동성 아래 1/3", V.liq <= 1 / 3)
row("조용 & 유동성 아래 1/3", (V.q_vm <= 0.3) & (V.liq <= 1 / 3))
for a, b in (("0901", "0959"), ("1000", "1159"), ("1200", "1359"), ("1400", "1518")):
    row("VI 시각 %s~%s" % (a, b), (V.hm >= a) & (V.hm <= b))
for lo, hi in ((-99, -12), (-12, -10), (-10, -8), (-8, 99)):
    row("단일가 체결가 시가 대비 %+d~%+d%%" % (max(lo, -20), min(hi, 0)), (V.ent_ref > lo) & (V.ent_ref <= hi))
row("갭 상승으로 시작(gap ≥ +3) 뒤 하락 VI", V.gap >= 3)
row("갭 보합(-3~+3) 뒤 하락 VI", (V.gap > -3) & (V.gap < 3))
row("갭 하락(gap ≤ -3) 뒤 하락 VI", V.gap <= -3)
print("\n== 참고: 단일가 체결가 매수 → 5분 뒤 매도")
V2 = V.assign(ret=V.ret5)
for nm, m in (("전체", al), ("조용", V.q_vm <= 0.3)):
    a = lab.stats(V2[m & (V2.date <= TR[1])]); b = lab.stats(V2[m & (V2.date >= VA[0])])
    print("%-46s | 학습 %s | 검증 %s" % (nm, f(a), f(b)))
print("\n== 참고: 같은 날 시가 매수 → 종가(VI 낀 날 전체 일봉) %+.2f%% · VI 뒤 저가까지 더 빠진 평균 %+.2f%%" % (V.oc.mean() - FT.COST, V.dd.mean()))
print("해마다:", " ".join("%s:%d %+.2f" % (y, len(g), g.ret.mean()) for y, g in V.groupby(V.date.str[:4])))
