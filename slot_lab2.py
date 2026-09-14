# -*- coding: utf-8 -*-
"""**slot_lab 후속 — 두 가지 확인** (2026-09-15).

slot_lab.py 에서 두 가지가 걸렸다.

① B(막힌 후보)의 '흘려보낸 게 나았다' 는 **날짜를 통제하지 않은 비교**다. 막힘은 폭락
   바닥 며칠에 몰리는데 그 구간은 원래 수익률이 높다(현금부족 720건 승률 95% 가 증거다).
   게다가 같은 사건이 여러 날 신호로 반복돼 중복 계상된다.
   → **같은 날·같은 규칙 안에서** 거래대금 순위별 성적을 본다. 그래야 우선순위 정책만
     남는다. (계좌 단위로는 tiebreak.py 가 이미 '거래대금 큰 순' 이 작은 순보다 나음을
     쟀다 — 14.97 vs 14.41배. 여기선 그 이유를 보는 것이다.)

② A(자리 쪼개기)에서 비중을 ÷k 하니 **실제 노출이 같이 떨어졌다**(25%→9%). 자리를 늘려도
   그날 후보가 없으면 못 채우기 때문이다. 그러면 안 해 본 칸이 하나 남는다 —
   **비중은 그대로 두고 자리만 늘리기**. 최대 노출은 오르지만 실제로 얼마나 오르나.

    python slot_lab2.py           (시드 12)
"""
import sys, time, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
from pathlib import Path

BASE = Path(__file__).parent
SEEDS = int(sys.argv[1]) if len(sys.argv) > 1 else 12
W = 104
NAME = {"P1": "조용한 신고가", "P2": "조정매집", "P3": "폭락반등", "P4": "업종붕괴 이탈",
        "P5": "자사주 낙폭", "P6": "깊은 이격", "P7": "외인 매집",
        "D1": "낙폭과대", "D2": "저PBR 낙폭"}


def sec(t): print("\n" + "=" * W + f"\n{t}\n" + "=" * W)


SRC = (BASE / "portfolio.py").read_text(encoding="utf-8").split("# @@ANALYSIS", 1)[0]
ns = {"__file__": str(BASE / "portfolio.py")}
t0 = time.time()
exec(compile(SRC, "portfolio.py", "exec"), ns)
S0, simulate = ns["S"], ns["simulate"]
print(f"패널·신호 준비 {time.time()-t0:.0f}초")

# ══════════════════════════════════════════════════════════════════════════
sec("① 같은 날·같은 규칙 안에서 — 거래대금 순위가 성적과 관계있나")
print("  후보가 2개 이상인 (날짜×규칙) 묶음만 본다. 같은 날 같은 규칙이므로 국면도 재료도")
print("  같다 — 남는 차이는 **무엇을 먼저 고르느냐** 뿐이다. 이게 우선순위 정책의 순수 실험이다.\n")
S = S0.copy()
S["ret"] = (S.exit / S.buy - 1) * 100 - S.cost
g = S.groupby(["di", "rid"])
S["ncand"] = g.ret.transform("size")
C = S[S.ncand >= 2].copy()
# 그 묶음 안에서 거래대금 순위(1 = 가장 큼)와, 묶음 평균 대비 초과수익
C["rk"] = C.groupby(["di", "rid"]).amt20.rank(ascending=False, method="first")
C["q"] = (C.rk - 1) / (C.ncand - 1)                    # 0 = 거래대금 1등, 1 = 꼴찌
C["ex"] = C.ret - C.groupby(["di", "rid"]).ret.transform("mean")
print(f"  경쟁이 붙은 묶음 {C.groupby(['di','rid']).ngroups:,}개 · 후보 {len(C):,}건"
      f" (전체 신호의 {len(C)/len(S):.0%})")
print(f"\n  {'거래대금 자리':<16}{'건수':>9}{'평균%':>9}{'묶음대비 초과%p':>16}{'승률':>8}")
for lo, hi, lbl in [(-.01, .25, "상위 25% (큰 쪽)"), (.25, .5, "25~50%"),
                    (.5, .75, "50~75%"), (.75, 1.01, "하위 25% (작은 쪽)")]:
    z = C[(C.q > lo) & (C.q <= hi)]
    if len(z):
        print(f"  {lbl:<16}{len(z):>9,}{z.ret.mean():>+9.2f}{z.ex.mean():>+16.3f}{(z.ret>0).mean():>8.0%}")
print(f"\n  1등만 (실제로 사는 것)   {len(C[C.rk==1]):>6,}건 · 초과 {C[C.rk==1].ex.mean():>+6.3f}%p")
print(f"  꼴찌만                {len(C[C.rk==C.ncand]):>6,}건 · 초과 {C[C.rk==C.ncand].ex.mean():>+6.3f}%p")
print(f"\n  {'규칙':<16}{'묶음':>8}{'후보':>9}{'1등 초과%p':>12}{'꼴찌 초과%p':>13}   방향")
for rid in ["P1", "P2", "P3", "P4", "P5", "P6", "P7", "D1", "D2"]:
    z = C[C.rid == rid]
    if not len(z): continue
    a, b = z[z.rk == 1].ex.mean(), z[z.rk == z.ncand].ex.mean()
    print(f"  {NAME[rid]:<16}{z.groupby('di').ngroups:>8,}{len(z):>9,}{a:>+12.3f}{b:>+13.3f}   "
          + ("✅ 큰 쪽이 낫다" if a > b else "⚠ 작은 쪽이 낫다"))

# ══════════════════════════════════════════════════════════════════════════
sec("② 비중은 그대로, 자리만 늘리면 — 실제 노출이 어디까지 오르나")
print("  slot_lab A 는 비중을 ÷k 해서 노출이 같이 떨어졌다. 여기서는 비중을 유지한다.")
print("  최대 노출(pct×mx)은 k배가 되지만, 후보가 없으면 자리는 비어 있을 뿐이다.\n")
print(f"  {'구성':<26}{'최대노출':>10}{'실제노출':>10}{'자산':>9}{'낙폭':>8}{'거래':>8}")
base_max = (S0.groupby("rid").first().pct * S0.groupby("rid").first().mx).sum()
res = {}
for k in (1, 1.5, 2, 3):
    z = S0.copy()
    if k != 1: z["mx"] = np.maximum(1, np.round(z.mx * k)).astype(int)
    res[k] = z
    ns["S"] = z
    Cc, L = simulate(1.0, 1.0, "", quiet=True)
    mx = (z.groupby("rid").first().pct * z.groupby("rid").first().mx).sum()
    print(f"  {('지금 그대로' if k==1 else f'자리 {k}배 (비중 유지)'):<26}{mx:>9.0f}%"
          f"{Cc.expo.mean()*100:>9.0f}%{Cc.nav.iloc[-1]:>8.2f}배"
          f"{((Cc.nav/Cc.nav.cummax())-1).min()*100:>7.1f}%{len(L):>8,}")


def shuffled(Z, seed):
    return Z.sample(frac=1.0, random_state=seed).sort_values("di", kind="stable").reset_index(drop=True)


print(f"\n  랜덤 {SEEDS}시드 짝비교")
print(f"  {'구성':<26}{'중앙':>9}{'최악':>9}{'최고':>9}{'폭':>7}{'자산승':>8}{'낙폭승':>8}")
for k in (1.5, 2, 3):
    rows = []
    for s in range(SEEDS):
        ns["S"] = shuffled(S0, s);     x, _ = simulate(1.0, 1.0, "", quiet=True)
        ns["S"] = shuffled(res[k], s); y, _ = simulate(1.0, 1.0, "", quiet=True)
        rows.append((y.nav.iloc[-1], x.nav.iloc[-1],
                     ((y.nav/y.nav.cummax())-1).min()*100, ((x.nav/x.nav.cummax())-1).min()*100))
    R = pd.DataFrame(rows, columns=["nav", "base", "mdd", "bmdd"])
    print(f"  {f'자리 {k}배 (비중 유지)':<26}{R.nav.median():>8.2f}배{R.nav.min():>8.2f}배"
          f"{R.nav.max():>8.2f}배{R.nav.max()/R.nav.min():>6.2f}x"
          f"{int((R.nav>R.base).sum()):>6}/{SEEDS}{int((R.mdd>R.bmdd).sum()):>6}/{SEEDS}")

print(f"\n총 {time.time()-t0:.0f}초")
