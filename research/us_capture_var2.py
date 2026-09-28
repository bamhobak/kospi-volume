# -*- coding: utf-8 -*-
"""미장 계좌 '[자사주 낙폭] 빼기 + 투입 상한 70%' 후보 — 이웃 칸·세 구간·시드 짝비교 (2026-09-29).

us_capture_var: 두 구간(2016~20 · 2021~) 모두 낙폭이 나아진 건 이 조합 하나였다. 운이 아닌지 본다.
  · 구간 셋: A 2009~15(폐지 포함 패널이라 가능) · B 2016~20 · C 2021~  — 같은 경로를 잘라 잰다
  · 이웃: 투입 상한 60/70/80% × [자사주 낙폭] 빼기 / 비중 절반(2.5%) / 그대로
  · 100시드 짝비교(같은 시드 = 같은 날 순서 무작위) — 지금 대비 낙폭이 얕은 시드 %, 수익이 높은 시드 %
채택 기준(미리 정함): 세 구간 모두 낙폭이 얕은 시드 70%↑ · 하락 포착이 낮아짐 · 이웃 칸(60·80%)도 같은 방향.
수익은 '적당히' 면 된다([[goal-not-beating-index]]) — 단 세 구간 합계 수익이 크게 깎이면(연 3%p↑) 보고한다.

    python research/us_capture_var2.py
"""
import sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent
src = (ROOT / "us_capture.py").read_text(encoding="utf-8").split("# ── ① 미장 계좌", 1)[0]
src = src.replace('S = S[S.date >= "20160101"]', 'S = S[S.date >= "20090101"]')
src = src.replace('x = fdr.DataReader(sym, "2015-06-01")', 'x = fdr.DataReader(sym, "2008-06-01")')
src = src.replace('x = x[x.index >= "20160101"]', 'x = x[x.index >= "20090101"]')
exec(compile(src, "us_capture.py", "exec"))

NS = 100
PER = [("A 2009~15", "20090101", "20151231"), ("B 2016~20", "20160101", "20201231"), ("C 2021~", "20210101", "20991231")]


def seg(nav, lo, hi):
    s = nav[(nav.index >= lo) & (nav.index <= hi)]
    b = SPX.reindex(s.index).ffill()
    m = s.groupby(s.index.str[:6]).last().pct_change().dropna() * 100
    mb = b.groupby(b.index.str[:6]).last().pct_change().reindex(m.index) * 100
    dn = mb < 0
    return (((s.iloc[-1] / s.iloc[0]) ** (252 / len(s)) - 1) * 100, (s / s.cummax() - 1).min() * 100,
            m[dn].mean() / mb[dn].mean(), m[mb > 0].mean() / mb[mb > 0].mean())


def run(Sx, pct, cap):
    global PATH_X
    PATH_X = [PATH[i] for i in Sx.index]
    Sx = Sx.reset_index(drop=True)
    R = np.zeros((NS, len(PER), 4))
    for s in range(NS):
        nav = sim(Sx, pct, MX, s, cap)[0]
        for k, (_, lo, hi) in enumerate(PER):
            R[s, k] = seg(nav, lo, hi)
    return R


PCT_H = dict(PCT); PCT_H["N4"] = 2.5
NO4 = S[S.rid != "N4"]
VAR = [("지금 (6규칙 · 상한 100%)", S, PCT, 1.0)]
for cap in (0.6, 0.7, 0.8):
    VAR += [("자사주 빼기 · 상한 %d" % int(cap * 100), NO4, PCT, cap),
            ("자사주 절반 · 상한 %d" % int(cap * 100), S, PCT_H, cap),
            ("6규칙 그대로 · 상한 %d" % int(cap * 100), S, PCT, cap)]
VAR.append(("자사주 빼기 · 상한 100", NO4, PCT, 1.0))

RES = {}
for lbl, Sx, pct, cap in VAR:
    log(lbl)
    RES[lbl] = run(Sx, pct, cap)
pickle.dump(RES, open(ROOT / "cache" / "us_capture_var2.pkl", "wb"))
B = RES[VAR[0][0]]
O = ["# 미장 계좌 후보 검증 — 이웃 칸·세 구간·%d시드 짝비교 · %s" % (NS, time.strftime("%Y-%m-%d")), "",
     "각 칸: 연수익 / 최대낙폭 / 하락 포착(S&P 하락 달 기준). 괄호 = 지금 대비 **낙폭이 얕은 시드 %** · **수익이 높은 시드 %**.", "",
     "| 구성 | " + " | ".join(p[0] for p in PER) + " | 세 구간 모두 낙폭 개선 70%↑ |", "|---|" + "---|" * len(PER) + "---|"]
for lbl, *_ in VAR:
    R = RES[lbl]; cells = []; ok = True
    for k in range(len(PER)):
        med = np.median(R[:, k], axis=0)
        if R is B:
            cells.append("%+.1f%% / %.1f%% / %.2f" % (med[0], med[1], med[2]))
        else:
            wm = (R[:, k, 1] > B[:, k, 1]).mean() * 100; wr = (R[:, k, 0] > B[:, k, 0]).mean() * 100
            ok &= wm >= 70
            cells.append("%+.1f%% / %.1f%% / %.2f (%.0f%% · %.0f%%)" % (med[0], med[1], med[2], wm, wr))
    O.append("| %s | %s | %s |" % (lbl, " | ".join(cells), "—" if R is B else ("✅" if ok else "")))
spx = [seg(BN["S&P500"], lo, hi) for _, lo, hi in PER]
O.append("| (참고) S&P500 | " + " | ".join("%+.1f%% / %.1f%% / 1.00" % (x[0], x[1]) for x in spx) + " | |")
O += ["", "※ 채택 기준(미리 정함): 세 구간 모두 낙폭 얕은 시드 70%↑ · 하락 포착 하락 · 이웃 칸(60·80%) 같은 방향.",
      "※ A 구간(2009~15)의 [실적 서프라이즈]는 실적 자료가 2013년부터라 신호가 적다."]
rp = ROOT / "reports" / ("us_capture_var2_%s.md" % time.strftime("%Y%m%d"))
rp.write_text("\n".join(O) + "\n", encoding="utf-8")
print("\n".join(O))
