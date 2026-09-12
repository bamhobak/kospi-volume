# -*- coding: utf-8 -*-
"""**트레일링 -8% 가 제 값을 하나** — 랜덤 30시드 짝비교 (2026-09-12).

stop_sweep2.py 에서 경로 하나로는 '트레일 없음' 이 더 나아 보였다(19.50 vs 19.03배,
낙폭 -10.9 vs -13.4%). 경로 하나로는 판정하지 않는다.

같은 날 후보가 자리보다 많으면 무엇이 체결될지는 운이다. 그 순서를 시드로 섞어
30경로를 만들고 **같은 시드끼리 짝지어** 비교한다(us_n_acct.py 와 같은 방식).

  ① 트레일 -8% · 낙관 체결 — 지금 사이트·대화에서 쓰던 값
  ② 트레일 -8% · 보수 체결 — 선이 깨진 걸 종가로 보고 다음날 시가에 판다
  ③ 트레일 아예 없음      — 정해진 날까지 그냥 보유

판정은 ② vs ③ 이다(둘 다 같은 체결 잣대). 목표는 더 버는 게 아니라 덜 아픈 것이므로
**낙폭을 먼저** 본다.

    python trail_seeds.py
"""
import sys, warnings, io, contextlib, time
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
from pathlib import Path
BASE = Path(__file__).parent
NSEED = 30

SRC = (BASE / "portfolio.py").read_text(encoding="utf-8")
HEAD, REST = SRC.split("# 신호를 한 표로 모은다", 1)
MID = "# 신호를 한 표로 모은다" + REST.split("# @@ANALYSIS", 1)[0]

# ── 체결 가정 보수판
OPT = "        px = np.where(ok, run[np.arange(len(C)), first]*(1-t), C[:, -1])"
CONS = ("        _O = np.column_stack([g.buy.shift(-i).values for i in range(0, hold+2)])\n"
        "        px = np.where(ok, _O[np.arange(len(C)), first+1], C[:, -1])\n"
        "        px = np.where(np.isnan(px), C[:, -1], px)")
assert MID.count(OPT) == 1

# ── 같은 날 후보 순서를 시드로 섞는다(자리 경쟁의 운을 재현)
A = "    eq = 1.0; open_pos = []; log = []; blocked = 0; taken = 0"
B = A + "\n    _rng = np.random.default_rng(globals().get('SEED') or 0)"
assert MID.count(A) == 1
C_ = "        todays = S[S.di == i]"
D_ = (C_ + "\n        if globals().get('SEED') is not None and len(todays) > 1:\n"
      "            todays = todays.sample(frac=1, random_state=int(_rng.integers(1 << 30)))")
assert MID.count(C_) == 1


def variant(cons):
    m = MID.replace(OPT, CONS) if cons else MID
    if cons: m = m.replace('X["hold"] = (first + 1)[m]', 'X["hold"] = (first + 2)[m]')
    return m.replace(A, B).replace(C_, D_)


ns = {"__file__": str(BASE / "portfolio.py")}
t0 = time.time()
exec(compile(HEAD, "portfolio.py", "exec"), ns)
print(f"패널 적재 {time.time()-t0:.0f}초")
TRAIL0 = dict(ns["TRAIL"])

CFG = [("① 트레일 -8% · 낙관", TRAIL0, False),
       ("② 트레일 -8% · 보수", TRAIL0, True),
       ("③ 트레일 없음", {}, False)]

RES = {}
for lbl, tr, cons in CFG:
    ns["TRAIL"] = dict(tr); ns["SEED"] = None
    b = io.StringIO()
    with contextlib.redirect_stdout(b):
        exec(compile(variant(cons), "portfolio.py", "exec"), ns)
    sim = ns["simulate"]; yrs = len(ns["dates"]) / 252
    rows = []
    t1 = time.time()
    for k in range(NSEED):
        ns["SEED"] = k
        with contextlib.redirect_stdout(io.StringIO()):
            Cv, L = sim(1.0, 1.0, lbl, quiet=True)
        nav = Cv.nav.iloc[-1]
        rows.append((nav, ((Cv.nav / Cv.nav.cummax()) - 1).min() * 100,
                     Cv.expo.mean() * 100, len(L)))
    RES[lbl] = pd.DataFrame(rows, columns=["nav", "mdd", "expo", "n"])
    d = RES[lbl]
    print(f"  {lbl:<22} {NSEED}시드 {time.time()-t1:.0f}초 · 중앙 {d.nav.median():.2f}배")

W = 100
print("\n" + "=" * W)
print(f"① 랜덤 {NSEED}시드 분포")
print("=" * W)
print(f"  {'설정':<22}{'중앙':>8}{'최악':>8}{'최고':>8}{'하위25%':>9}"
      f"{'낙폭 중앙':>11}{'낙폭 최악':>11}{'평균노출':>9}")
for lbl, _, _ in CFG:
    d = RES[lbl]
    print(f"  {lbl:<22}{d.nav.median():>7.2f}배{d.nav.min():>7.2f}배{d.nav.max():>7.2f}배"
          f"{d.nav.quantile(0.25):>8.2f}배{d.mdd.median():>10.1f}%{d.mdd.min():>10.1f}%"
          f"{d.expo.mean():>8.0f}%")

print("\n" + "=" * W)
print("② 짝비교 — 같은 시드에서 ③(트레일 없음)이 ②(트레일·보수)를 이긴 횟수")
print("=" * W)
a = RES["② 트레일 -8% · 보수"]; b = RES["③ 트레일 없음"]
dn = b.nav.values - a.nav.values
dm = b.mdd.values - a.mdd.values          # mdd 는 음수 — 클수록(0에 가까울수록) 얕다
print(f"  최종자산  ③이 큼 {int((dn > 0).sum())}/{NSEED}회 · 차이 중앙 {np.median(dn):+.2f}배"
      f" (평균 {dn.mean():+.2f})")
print(f"  최대낙폭  ③이 얕음 {int((dm > 0).sum())}/{NSEED}회 · 차이 중앙 {np.median(dm):+.1f}%p"
      f" (평균 {dm.mean():+.1f})")
print(f"\n  ②(트레일·보수) 낙폭 중앙 {a.mdd.median():.1f}% · 최악 {a.mdd.min():.1f}%")
print(f"  ③(트레일 없음) 낙폭 중앙 {b.mdd.median():.1f}% · 최악 {b.mdd.min():.1f}%")

print("\n" + "=" * W)
print("③ 참고 — 낙관 체결이 얼마나 부풀리나")
print("=" * W)
o = RES["① 트레일 -8% · 낙관"]
print(f"  중앙 {o.nav.median():.2f}배 → 보수 {a.nav.median():.2f}배 "
      f"({(a.nav.median()/o.nav.median()-1)*100:+.1f}%)")
print(f"  낙폭 중앙 {o.mdd.median():.1f}% → 보수 {a.mdd.median():.1f}% ({a.mdd.median()-o.mdd.median():+.1f}%p)")
