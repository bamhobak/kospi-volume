# -*- coding: utf-8 -*-
"""상승장 2호 마지막 판정 — 복권형이 풀리는가.

여기까지: **내부자 신고 2건 이상**(서로 다른 내부자 둘 이상이 같은 날 매수) + 상승장 · 20일 보유
  승률 59.0% · 중앙 +1.66 · 절삭 **+0.09** · 초과 +1.33 · 학CI +0.22 · 양수해 10/11
  계좌 14.42 → 20.41배 · 검증 4.13 → 4.53 · 랜덤최악 4.17 → 5.70

걸리는 두 가지
  · **복권형** — 상위 5%가 전체 수익의 94.7%. 절삭평균이 겨우 +0.09 다.
  · **스트레스(2006~15)** — 초과 +0.10 · 5/10. 사실상 0.
둘 다 N1 의 약점과 같은 모양이라, 이대로면 'N1 의 사촌' 이지 대안이 아니다.
목적은 **N1 의존을 줄이는 것**이므로 성질이 달라야 한다.

그런데 금액을 겹친 칸(2건↑ & 100만$↑)은 절삭이 **+0.86** 으로 확 좋아졌다.
조이면 복권형이 풀리는지, 아니면 표본만 줄어 우연이 커지는지 가른다.

  ① 인원 × 금액 격자 — 절삭평균과 상위5% 비중을 같이 본다
  ② 살아남는 칸의 스트레스
  ③ 계좌 (자리·비중까지)
  ④ 최종 판정 — 다중검정 보정 포함

    python us_bull7.py
"""
import sys, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
src = open(Path(__file__).parent / "us_bull5.py", encoding="utf-8").read()
exec(src.split('print("\\n" + "=" * 168)')[0].split('"""', 2)[2])

def lot(d):
    """복권형 지표 — 절삭평균 · 상위1%/5% 가 전체 수익에서 차지하는 비중."""
    tot = d.r.sum()
    if tot <= 0: return d.r[d.r <= d.r.quantile(.95)].mean(), np.nan, np.nan
    return (d.r[d.r <= d.r.quantile(.95)].mean(),
            d.r.nlargest(max(1, len(d) // 100)).sum() / tot * 100,
            d.r.nlargest(max(1, len(d) // 20)).sum() / tot * 100)

print("\n" + "=" * 150)
print("① 인원 × 금액 격자 — 조이면 복권형이 풀리나 (상승장 · 20일 보유)")
print("=" * 150)
print(f"  {'조건':<24} {'n':>6} {'일':>5} {'승률':>6} {'중앙':>7} {'절삭':>7} {'상위1%':>7} {'상위5%':>7} "
      f"{'초과':>7} {'학습':>7} {'검증':>7} {'학CI':>7} {'검CI':>7} {'연양수':>6}")
CELLS = []
for n in (1, 2, 3):
    for v in (0, 3e5, 1e6, 2e6):
        c = BASEC & (K.bn >= n) & ((K.bv >= v) if v else K.bv.notna())
        d = dd(c, 20)
        if len(d) < 100:
            print(f"  {f'{n}건↑' + (f' & {v/1e6:.1f}M$↑' if v else ''):<24} {len(d):>6}  (표본 부족)")
            continue
        d["ex"] = d.r - d.date.map(BENS[("act", 20)]); d["ym"] = d.date.str[:6]
        tr = d[d.date <= TR1]; va = d[d.date >= VA0]
        cit = boot_ci(tr.groupby("ym").ex.mean()) if len(tr) >= 25 else np.nan
        civ = boot_ci(va.groupby("ym").ex.mean()) if len(va) >= 25 else np.nan
        yr = d.groupby(d.date.str[:4]).ex.mean()
        tm, t1, t5 = lot(d)
        tag = f"{n}건↑" + (f" & {v/1e6:.1f}M$↑" if v else "")
        print(f"  {tag:<24} {len(d):>6} {len(d)/NDAY:>5.2f} {(d.r>0).mean()*100:>5.1f}% {d.r.median():>7.2f} "
              f"{tm:>7.2f} {t1:>6.1f}% {t5:>6.1f}% {d.ex.mean():>7.2f} {tr.ex.mean():>7.2f} "
              f"{va.ex.mean():>7.2f} {cit:>7.2f} {civ:>7.2f} {int((yr>0).sum()):>3}/{len(yr)}")
        CELLS.append((tag, n, v, tm, t5, d.ex.mean(), int((yr > 0).sum())))
    print()

print("=" * 150)
print("② 절삭평균>0 이고 상위5%<90% 인 칸만 — 스트레스 2006~2015")
print("=" * 150)
ok = [c for c in CELLS if c[3] > 0 and c[4] < 90]
if not ok:
    print("  없음 — 어느 칸도 복권형을 벗어나지 못했다")
    ok = [c for c in CELLS if c[3] > 0.3]
    print(f"  (참고로 절삭평균 +0.3 넘는 칸: {[c[0] for c in ok]})")
print(f"  {'조건':<24} {'n':>6} {'승률':>6} {'중앙':>7} {'절삭':>7} {'초과':>7} {'연양수':>6}")
for tag, n, v, *_ in ok:
    c = BASEC & (K.bn >= n) & ((K.bv >= v) if v else K.bv.notna())
    d = dd(c, 20, lo="20060101", hi="20151231")
    if len(d) < 60: print(f"  {tag+' · 06~15':<24} {len(d):>6}  (표본 부족)"); continue
    d["ex"] = d.r - d.date.map(BENS[("act", 20)])
    tm, _, _ = lot(d); yr = d.groupby(d.date.str[:4]).ex.mean()
    print(f"  {tag+' · 06~15':<24} {len(d):>6} {(d.r>0).mean()*100:>5.1f}% {d.r.median():>7.2f} "
          f"{tm:>7.2f} {d.ex.mean():>7.2f} {int((yr>0).sum()):>3}/{len(yr)}")

print("\n" + "=" * 150)
print("③ 다중검정 보정 — 지금까지 몇 개를 훑어서 나온 후보인가")
print("=" * 150)
try:
    import verdict
    verdict.log_trials("us_bull2nd", 12)
    import json
    tr_ = json.load(open(Path(__file__).parent / "data/trials.json", encoding="utf-8"))
    n_t = tr_.get("by_topic", {}).get("us_bull2nd", 0)
    print(f"  이 주제(us_bull2nd)에서 시험한 칸 {n_t}개 · 전체 누적 {tr_.get('total', 0):,}개")
    for tag, n, v, tm, t5, ex, ny in CELLS:
        c = BASEC & (K.bn >= n) & ((K.bv >= v) if v else K.bv.notna())
        d = dd(c, 20)
        d["ex"] = d.r - d.date.map(BENS[("act", 20)]); d["ym"] = d.date.str[:6]
        mo = d.groupby("ym").ex.mean()
        try:
            r = verdict.judge(tag, mo, n_trials=n_t)
        except Exception as e:
            print(f"  {tag}: 판정 실패 {e}")
except Exception as e:
    print("verdict:", e)
