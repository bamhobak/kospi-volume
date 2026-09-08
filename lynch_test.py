# -*- coding: utf-8 -*-
"""피터 린치 영상(kji2_WhW-Y4, 하와이 대저택) 실측 — 기계적 매매법이 아니라 '주장' 을 잰다.

이 영상은 기법 강의가 아니라 『전설로 떠나는 월가의 영웅』 소개다. 진입 조건 같은 건
안 나온다. 대신 **숫자로 확인 가능한 주장**이 다섯 개 있어 그것만 골라 잰다.

  L1 폭락 통계 — "미국 100년에 -10% 하락 53번(2년에 한 번), 그중 -25% 가 15번,
     그런데 매번 회복하고 새 고점을 갈아치웠다"  → **한국 시장은 어떤가**
  L2 "폭락을 피하려다 잃은 돈이 폭락으로 잃은 돈보다 많다"
     → 조정을 예측해 미리 파는 시늉(낙폭 발생 시 이탈·회복 시 재진입)과 항상보유 맞대기
  L3 "꽃을 뽑고 잡초에 물을 준다" — 오른 종목은 얼른 팔고 물린 종목은 붙든다
     → 우리 규칙 보유분을 중간 시점의 손익으로 갈라, 남은 구간 수익이 어느 쪽이 나은지
  L4 "매도는 가격이 아니라 **산 이유**가 사라졌을 때" → 우리 하락장 규칙이 산 이유는
     '코스피 60일선 아래의 공포' 다. 그 이유가 사라진 날(60일선 위 복귀) 청산해 본다
  L5 "10루타는 머리가 아니라 엉덩이가 만든다" → 보유기간을 늘리면 좋아지는가

L3~L5 는 우리 규칙 위에서 재므로 계좌 짝 비교까지 간다. L1·L2 는 시장 팩트체크다.
"""
import io, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
import FinanceDataReader as fdr

BASE = Path(__file__).parent
SEEDS = 12

# ══════════════════════════════════════════════════════════════════════
# L1. 폭락 통계 — 한국 시장에서 -10% / -25% 는 얼마나 자주 오고, 정말 매번 회복했나
# ══════════════════════════════════════════════════════════════════════
print("=" * 104)
print("L1. 폭락 빈도와 회복 — 린치: 미국 100년에 -10% 53번 · -25% 15번 · 전부 회복해 새 고점")
print("=" * 104)

def episodes(px, th):
    """고점 대비 th 이상 빠진 '사건' 을 센다. 신고가를 다시 쓰면 사건 종료."""
    v = px.values
    peak, i, out = v[0], 0, []
    n = len(v)
    while i < n:
        if v[i] >= peak:
            peak = v[i]; i += 1; continue
        j, trough, ti = i, v[i], i
        while j < n and v[j] < peak:
            if v[j] < trough: trough, ti = v[j], j
            j += 1
        dd = trough / peak - 1
        if dd <= -th:
            out.append(dict(start=px.index[i], bottom=px.index[ti], dd=dd * 100,
                            end=(px.index[j] if j < n else None),
                            days=(j - i if j < n else None),
                            rec=(j - ti if j < n else None)))
        peak = v[j] if j < n else peak
        i = j + 1 if j < n else n
    return pd.DataFrame(out)

def episodes_roll(px, th, win=250):
    """직전 1년 고점 대비 th 이상 빠진 사건. 그 고점을 되찾으면 종료.
    사상최고 기준은 한 번 무너지면 뒤가 통째로 한 사건이 되어(코스닥 2000년 고점 26년째
    미회복) 조정 횟수를 셀 수 없다. 사람이 실제 겪는 '조정' 은 이쪽에 가깝다."""
    v = px.values
    ref = px.rolling(win, min_periods=20).max().values
    n, i, out = len(v), 0, []
    while i < n:
        if np.isnan(ref[i]) or v[i] > ref[i] * (1 - th):
            i += 1; continue
        pk = ref[i]                       # 이 사건의 기준 고점
        # 종료는 '옛 고점 회복' 이 아니라 **1년 신고가 재탈환**이다. 옛 고점을 기다리면
        # 장기 약세장이 통째로 한 사건이 되어 사상최고 기준과 똑같아진다.
        j, trough, ti = i, v[i], i
        while j < n and not (v[j] >= ref[j] and j > i):
            if v[j] < trough: trough, ti = v[j], j
            j += 1
        out.append(dict(start=px.index[i], bottom=px.index[ti], dd=trough / pk - 1,
                        end=(px.index[j] if j < n else None),
                        rec=(j - ti if j < n else None)))
        i = j + 1 if j < n else n
    return pd.DataFrame(out, columns=["start", "bottom", "dd", "end", "rec"])

# 기준 고점을 두 가지로 잰다. 사상 최고가 기준은 한 번 무너지면 그 뒤가 통째로 한 사건이
# 되어(코스닥 2000년 고점은 26년째 미회복) 린치의 '53번' 과 셈법이 달라진다. 그래서
# **직전 1년 고점** 기준도 같이 낸다 — 사람들이 실제로 겪는 '조정' 에 가깝다.
for code, nm, start in (("KS11", "코스피", "1981-01-01"), ("KQ11", "코스닥", "1996-07-01"),
                        ("US500", "S&P500", "1985-01-01")):
    D = fdr.DataReader(code, start)
    D = D[D.Close > 0]
    px = D.Close
    yrs = (px.index[-1] - px.index[0]).days / 365.25
    print(f"  ── {nm} {px.index[0].date()}~{px.index[-1].date()} ({yrs:.0f}년) ──")
    for th in (0.10, 0.25):
        E = episodes(px, th)
        done = E[E.end.notna()]
        alive = len(E) - len(done)
        per = yrs / len(E) if len(E) else float("nan")
        rec = f"회복 중앙 {done.rec.median():.0f}거래일" if len(done) else "회복 없음"
        print(f"    사상최고 기준 -{th*100:.0f}% 이상 {len(E):>3}회 · {per:>4.1f}년에 한 번 · "
              f"회복 {len(done)}/{len(E)}{' 미회복'+str(alive) if alive else ''} · {rec} · "
              f"최악 {E.dd.min():.0f}%")
        E2 = episodes_roll(px, th)
        done2 = E2[E2.end.notna()]
        per2 = yrs / len(E2) if len(E2) else float("nan")
        print(f"    1년고점 기준 -{th*100:.0f}% 이상 {len(E2):>3}회 · {per2:>4.1f}년에 한 번 · "
              f"회복 {len(done2)}/{len(E2)} · "
              f"{'회복 중앙 '+format(done2.rec.median(),'.0f')+'거래일' if len(done2) else '회복 없음'}")

# ══════════════════════════════════════════════════════════════════════
# L2. "폭락을 피하려다 잃은 돈이 더 많다" — 이탈·재진입을 흉내 내 본다
# ══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 104)
print("L2. 조정을 피하려는 시도 vs 항상보유 — 지수 기준 (왕복비용 0.3%)")
print("=" * 104)
for code, nm in (("KS11", "코스피"), ("KQ11", "코스닥"), ("US500", "S&P500")):
    D = fdr.DataReader(code, "1996-07-01")
    D = D[D.Close > 0].copy()
    c = D.Close
    D["r"] = c.pct_change().shift(-1) * 100          # 오늘 판단 → 내일 수익
    peak = c.cummax()
    print(f"  [{nm}]")
    for th in (5, 10, 15):
        for back in (0, 5, 10):
            # 고점 대비 th% 빠지면 판다. 저점 대비 back% 오르면 다시 산다(back=0 이면 신고가에서).
            on, trough, pos = True, c.iloc[0], []
            pk = c.iloc[0]
            for v in c.values:
                pk = max(pk, v)
                if on and v <= pk * (1 - th / 100):
                    on = False; trough = v
                elif not on:
                    trough = min(trough, v)
                    if (back and v >= trough * (1 + back / 100)) or (not back and v >= pk):
                        on = True
                pos.append(on)
            P = pd.Series(pos, index=c.index)
            sw = P != P.shift(1)
            r = D.r.fillna(0)
            sysr = np.where(P, r, 0.0) - sw.astype(float) * 0.30
            s = (1 + pd.Series(sysr) / 100).prod()
            b = (1 + r / 100).prod()
            mdd_s = float(((1 + pd.Series(sysr) / 100).cumprod() /
                           (1 + pd.Series(sysr) / 100).cumprod().cummax() - 1).min() * 100)
            mdd_b = float(((1 + r / 100).cumprod() / (1 + r / 100).cumprod().cummax() - 1).min() * 100)
            tag = f"-{th}% 이탈 / " + (f"저점+{back}% 재진입" if back else "신고가 재진입")
            print(f"    {tag:<26} 회피 {s:>7.2f}배 낙폭{mdd_s:>5.0f}% · 매매 {sw.sum():>3}회  |  "
                  f"항상보유 {b:>7.2f}배 낙폭{mdd_b:>5.0f}%  → {'회피 승' if s > b else '보유 승'}")
