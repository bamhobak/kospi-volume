# -*- coding: utf-8 -*-
"""**자리보다 후보가 많을 때 무엇을 사는가** — 정해둔 적이 없다 (2026-09-12).

trail_seeds.py 에서 기본 경로(19.03배)가 랜덤 30시드의 **최고값(17.51배)보다도 높게**
나왔다. 우연이 아니라는 뜻이다. portfolio.py 는 `S.sort_values(["di","rid"])` 로 정렬하고
그 안의 순서는 패널 순서(= 티커 코드 오름차순)다. 즉 **티커 번호가 작은 종목을 먼저** 산다.
국내는 코드가 작을수록 오래된 회사라 이게 공짜 이득일 수 있다.

미장 규칙에는 '후보가 자리보다 많으면 거래대금 큰 순' 이라고 적어 뒀는데 국내 규칙에는
**아무 말이 없다**. 실제로 무엇을 사야 하는지 정하고, 그 값으로 다시 재야 한다.

체결은 전부 **보수판**(트레일 선이 깨진 걸 종가로 보고 다음날 시가 매도)으로 통일한다.

    python tiebreak.py
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

OPT = "        px = np.where(ok, run[np.arange(len(C)), first]*(1-t), C[:, -1])"
CONS = ("        _O = np.column_stack([g.buy.shift(-i).values for i in range(0, hold+2)])\n"
        "        px = np.where(ok, _O[np.arange(len(C)), first+1], C[:, -1])\n"
        "        px = np.where(np.isnan(px), C[:, -1], px)")
SEL = '"buy","exit","low","cost"]])'
assert MID.count(OPT) == 1 and MID.count(SEL) == 1
M = MID.replace(OPT, CONS).replace('X["hold"] = (first + 1)[m]', 'X["hold"] = (first + 2)[m]')
M = M.replace(SEL, '"buy","exit","low","cost","amt20"]])')      # 거래대금을 S 에 싣는다
M = M.replace('S = S[S.buy > 0]', 'S = S[S.buy > 0]\nS["_amt"] = S.amt20.fillna(0)')

A = "    eq = 1.0; open_pos = []; log = []; blocked = 0; taken = 0"
M = M.replace(A, A + "\n    _rng = np.random.default_rng(globals().get('SEED') or 0)")
C_ = "        todays = S[S.di == i]"
D_ = C_ + """
        _tb = globals().get('TIEBREAK', 'code')
        if len(todays) > 1:
            if _tb == 'seed':
                todays = todays.sample(frac=1, random_state=int(_rng.integers(1 << 30)))
            elif _tb == 'coderev': todays = todays.iloc[::-1]
            elif _tb == 'amt':    todays = todays.sort_values('_amt', ascending=False, kind='stable')
            elif _tb == 'amtlow': todays = todays.sort_values('_amt', ascending=True, kind='stable')"""
assert M.count(C_) == 1
M = M.replace(C_, D_)

ns = {"__file__": str(BASE / "portfolio.py")}
t0 = time.time()
exec(compile(HEAD, "portfolio.py", "exec"), ns)
print(f"패널 적재 {time.time()-t0:.0f}초")
ns["SEED"] = None; ns["TIEBREAK"] = "code"
with contextlib.redirect_stdout(io.StringIO()):
    exec(compile(M, "portfolio.py", "exec"), ns)
sim = ns["simulate"]; yrs = len(ns["dates"]) / 252


def one(tb, seed=None):
    ns["TIEBREAK"] = tb; ns["SEED"] = seed
    with contextlib.redirect_stdout(io.StringIO()):
        Cv, L = sim(1.0, 1.0, "", quiet=True)
    nav = Cv.nav.iloc[-1]
    return nav, ((Cv.nav / Cv.nav.cummax()) - 1).min() * 100, len(L)


W = 92
print("\n" + "=" * W)
print("자리보다 후보가 많을 때 무엇을 먼저 사나 — 보수 체결 · 같은 신호")
print("=" * W)
print(f"  {'우선순위':<26}{'최종':>9}{'연':>8}{'최대낙폭':>10}{'거래':>7}")
for tb, lbl in (("code", "티커 코드 작은 순 (지금 백테스트)"), ("coderev", "티커 코드 큰 순"),
                ("amt", "거래대금 큰 순 (미장 규칙과 같게)"), ("amtlow", "거래대금 작은 순")):
    nav, mdd, n = one(tb)
    print(f"  {lbl:<26}{nav:>8.2f}배{(nav**(1/yrs)-1)*100:>7.2f}%{mdd:>9.1f}%{n:>7,}")

print(f"\n  랜덤 {NSEED}시드 (정해둔 규칙이 없을 때 실제로 겪는 것)")
rows = [one("seed", k) for k in range(NSEED)]
d = pd.DataFrame(rows, columns=["nav", "mdd", "n"])
print(f"  {'':<26}{d.nav.median():>8.2f}배{(d.nav.median()**(1/yrs)-1)*100:>7.2f}%"
      f"{d.mdd.median():>9.1f}%{d.n.median():>7,.0f}   ← 중앙")
print(f"  {'':<26}{d.nav.min():>8.2f}배{'':>7}{d.mdd.min():>9.1f}%{'':>7}   ← 최악")
print(f"  {'':<26}{d.nav.max():>8.2f}배{'':>7}{d.mdd.max():>9.1f}%{'':>7}   ← 최고")
