# -*- coding: utf-8 -*-
"""**자리(slot) 실험실** — 계좌의 진짜 화폐는 돈이 아니라 자리다 (2026-09-15).

관찰: 규칙별 자리 상한을 다 더하면 이론상 최대 노출이 222% 인데 실제 평균 노출은 25% 다.
      그런데 막힘은 10,867건 — 신호의 11배다. 모순이 아니라 **시간 쏠림**이다.
      대부분의 날 텅 비어 있다가 몇 주에 몰아서 만선이 된다(연도별 노출 9%~68%).
      그러면 '무엇을 살까' 가 아니라 **'자리를 어떻게 쓸까'** 가 진짜 문제다.

  A. 자리 쪼개기  — 비중을 반으로 줄이고 자리를 두 배로. 최대 노출은 같고 분산만 는다.
                   시드별로 13.18~17.77배(1.35배)가 순전히 자리 경쟁의 운이었다.
  B. 막힌 후보 추적 — 자리가 없어 못 산 후보가 그 뒤 어떻게 됐나. **한 번도 안 쟀다.**
                   우선순위 정책(거래대금 큰 순)의 기회비용을 직접 재는 유일한 방법이다.
  C. 보유기간 절반 — 같은 노출에서 회전을 두 배로. 수익 곡선이 보유일에 선형인지 본다.

판정은 늘 계좌다. 규칙 단위 평균은 자리 경쟁을 지운 숫자라 여기선 쓰지 않는다.

    python slot_lab.py            (시드 12)
    python slot_lab.py 30
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


SRC = (BASE / "portfolio.py").read_text(encoding="utf-8")
HEAD, REST = SRC.split("# 신호를 한 표로 모은다", 1)
MID = "# 신호를 한 표로 모은다" + REST.split("# @@ANALYSIS", 1)[0]

# ── simulate 에 '막힌 후보' 기록을 심는다 ────────────────────────────────
# portfolio.py 는 막힘을 **세기만** 한다(blocked += 1). 무엇이 왜 막혔고 그 뒤 어떻게
# 됐는지는 버려진다. 여기서만 기록해 둔다 — 정본은 건드리지 않는다.
OLD = """                if n_rule >= mx or invested + w > eq*cash_cap or any(
                        p["ticker"]==t.ticker for p in open_pos):
                    blocked += 1; continue"""
NEW = """                _dup = any(p["ticker"]==t.ticker for p in open_pos)
                if n_rule >= mx or invested + w > eq*cash_cap or _dup:
                    blocked += 1
                    BLOG.append((t.rid, t.date, t.ticker,
                                 "중복보유" if _dup else ("자리참" if n_rule >= mx else "현금부족"),
                                 (t.exit/t.buy-1)*100 - t.cost, t.amt20))
                    continue"""
assert MID.count(OLD) == 1
MIDB = MID.replace(OLD, NEW).replace(
    '                invested += w; taken += 1',
    '                invested += w; taken += 1\n'
    '                TLOG.append((t.rid, t.date, t.ticker, "체결",\n'
    '                             (t.exit/t.buy-1)*100 - t.cost, t.amt20))')

ns = {"__file__": str(BASE / "portfolio.py"), "BLOG": [], "TLOG": []}
t0 = time.time()
exec(compile(HEAD, "portfolio.py", "exec"), ns)
print(f"패널 적재 {time.time()-t0:.0f}초")
RULES0 = dict(ns["RULES"])


def build(rules=None, patched=False):
    """RULES 를 갈아 끼우고 신호표+simulate 를 다시 만든다."""
    ns["RULES"] = dict(rules or RULES0)
    ns["BLOG"], ns["TLOG"] = [], []
    exec(compile(MIDB if patched else MID, "portfolio.py", "exec"), ns)
    return ns["S"], ns["simulate"]


def shuffled(S, seed):
    """자리 경쟁 순서를 무작위로 — '거래대금 큰 순' 이라는 한 경로의 운을 지운다."""
    return S.sample(frac=1.0, random_state=seed).sort_values("di", kind="stable").reset_index(drop=True)


def stats(C):
    nav = C.nav.iloc[-1]
    return nav, ((C.nav / C.nav.cummax()) - 1).min() * 100, C.expo.mean() * 100


S0, simulate = build()
BASEC, BASEL = simulate(1.0, 1.0, "", quiet=True)
b_nav, b_mdd, b_exp = stats(BASEC)
print(f"기준 확인: {b_nav:.2f}배 · 낙폭 {b_mdd:.1f}% · 노출 {b_exp:.0f}%")

# ══════════════════════════════════════════════════════════════════════════
sec("A. 자리 쪼개기 — 최대 노출은 그대로 두고 자리 수만 늘린다")
print("  비중 ÷ k · 자리 × k 면 이론상 최대 노출(pct×mx)은 변하지 않는다.")
print("  달라지는 건 **한 자리에 몰던 돈을 몇 종목에 나누느냐** 뿐이다.\n")


def split(S, k):
    z = S.copy(); z["pct"] = z.pct / k; z["mx"] = (z.mx * k).astype(int); return z


A_CFG = [("지금 그대로", 1), ("반 비중 · 자리 2배", 2), ("1/3 비중 · 자리 3배", 3),
         ("1/4 비중 · 자리 4배", 4), ("2배 비중 · 자리 1/2 (역방향 확인)", 0.5)]
A_S = {}
print(f"  {'구성':<30}{'자산':>9}{'낙폭':>8}{'노출':>7}{'거래':>8}")
for lbl, k in A_CFG:
    z = split(S0, k) if k != 1 else S0
    if k == 0.5:
        z = S0.copy(); z["pct"] = z.pct * 2; z["mx"] = np.maximum(1, (z.mx / 2).astype(int))
    A_S[lbl] = z
    ns["S"] = z
    C, L = simulate(1.0, 1.0, "", quiet=True)
    n, m, e = stats(C)
    print(f"  {lbl:<30}{n:>8.2f}배{m:>7.1f}%{e:>6.0f}%{len(L):>8,}")

print(f"\n  랜덤 {SEEDS}시드 짝비교 — 같은 시드 안에서 기준과 견준다")
print(f"  {'구성':<30}{'중앙':>8}{'최악':>8}{'최고':>8}{'폭':>7}{'자산승':>8}{'낙폭승':>8}")
A_RES = {}
for lbl, k in A_CFG:
    rows = []
    for s in range(SEEDS):
        ns["S"] = shuffled(S0, s);        x, _ = simulate(1.0, 1.0, "", quiet=True)
        ns["S"] = shuffled(A_S[lbl], s);  y, _ = simulate(1.0, 1.0, "", quiet=True)
        rows.append((y.nav.iloc[-1], x.nav.iloc[-1],
                     ((y.nav/y.nav.cummax())-1).min()*100, ((x.nav/x.nav.cummax())-1).min()*100))
    R = pd.DataFrame(rows, columns=["nav", "base", "mdd", "bmdd"]); A_RES[lbl] = R
    print(f"  {lbl:<30}{R.nav.median():>7.2f}배{R.nav.min():>7.2f}배{R.nav.max():>7.2f}배"
          f"{R.nav.max()/R.nav.min():>6.2f}x{int((R.nav>R.base).sum()):>6}/{SEEDS}"
          f"{int((R.mdd>R.bmdd).sum()):>6}/{SEEDS}")
print("  ※ '폭' = 최고÷최악. 이 값이 작을수록 **운에 덜 휘둘린다** — 이 실험의 진짜 목적이다.")

# ══════════════════════════════════════════════════════════════════════════
sec("B. 막힌 후보 추적 — 못 산 것이 산 것보다 나았나")
ns["S"] = S0
_S, _sim = build(patched=True)
ns["S"] = _S
_sim(1.0, 1.0, "", quiet=True)
B = pd.DataFrame(ns["BLOG"], columns=["rid", "date", "ticker", "why", "ret", "amt20"])
T = pd.DataFrame(ns["TLOG"], columns=["rid", "date", "ticker", "why", "ret", "amt20"])
print(f"  체결 {len(T):,}건 · 막힘 {len(B):,}건 (신호 {len(_S):,})")
print(f"\n  {'막힌 이유':<10}{'건수':>9}{'평균%':>9}{'중앙%':>9}{'승률':>8}")
for w, g in B.groupby("why"):
    print(f"  {w:<10}{len(g):>9,}{g.ret.mean():>+9.2f}{g.ret.median():>+9.2f}{(g.ret>0).mean():>8.0%}")
print(f"  {'체결':<10}{len(T):>9,}{T.ret.mean():>+9.2f}{T.ret.median():>+9.2f}{(T.ret>0).mean():>8.0%}")

print(f"\n  ▸ 핵심은 '자리참' 이다 — 자리만 있었으면 샀을 것들이다.")
sit = B[B.why == "자리참"]
print(f"  {'규칙':<18}{'체결':>7}{'자리참':>8}{'체결 평균%':>12}{'자리참 평균%':>13}{'차이':>9}   판정")
for rid in ["P1", "P2", "P3", "P4", "P5", "P6", "P7", "D1", "D2"]:
    a, c = T[T.rid == rid], sit[sit.rid == rid]
    if not len(a) or not len(c): continue
    d = a.ret.mean() - c.ret.mean()
    print(f"  {NAME[rid]:<18}{len(a):>7,}{len(c):>8,}{a.ret.mean():>+12.2f}{c.ret.mean():>+13.2f}"
          f"{d:>+9.2f}   " + ("✅ 고른 게 나았다" if d > 0 else "⚠ 흘려보낸 게 나았다"))
d = T.ret.mean() - sit.ret.mean()
print(f"  {'전체':<18}{len(T):>7,}{len(sit):>8,}{T.ret.mean():>+12.2f}{sit.ret.mean():>+13.2f}{d:>+9.2f}")
print("\n  ▸ 우선순위(거래대금 큰 순)가 정말 맞나 — 자리참 안에서 거래대금 순위별 성적")
if len(sit):
    both = pd.concat([T.assign(k="체결"), sit.assign(k="자리참")])
    both["q"] = both.groupby("date").amt20.rank(pct=True, ascending=False)
    for lo, hi, lbl in [(0, .25, "거래대금 상위 25%"), (.25, .5, "25~50%"),
                        (.5, .75, "50~75%"), (.75, 1.01, "하위 25%")]:
        z = both[(both.q > lo) & (both.q <= hi)]
        if len(z): print(f"    {lbl:<18}{len(z):>7,}건 · 평균 {z.ret.mean():>+6.2f}% · 승률 {(z.ret>0).mean():>3.0%}")

# ══════════════════════════════════════════════════════════════════════════
sec("C. 보유기간 절반 — 같은 노출에서 회전을 두 배로")
print("  보유기간을 반으로 줄이면 자리가 두 배 빨리 빈다. 자리 수를 그대로 두면 노출이 줄고,")
print("  자리를 두 배로 늘리면 노출은 같고 회전만 두 배가 된다. 뒤쪽이 진짜 물음이다.\n")
LONG = {"P1", "P7", "D2"}                      # 40·60·40일 — 자리를 가장 오래 깔고 앉은 셋


def rehold(fn, slots=1.0):
    r = {}
    for k, v in RULES0.items():
        K, hold, stop, pct, mx, cond = v
        h = max(1, int(fn(k, hold)))
        m = mx if h == hold else max(1, int(round(mx * slots)))
        r[k] = (K, h, stop, pct, m, cond)
    return r


C_CFG = [("지금 그대로", lambda k, h: h, 1.0),
         ("전 규칙 절반 (자리 그대로)", lambda k, h: h / 2, 1.0),
         ("전 규칙 절반 + 자리 2배", lambda k, h: h / 2, 2.0),
         ("긴 셋만 절반 (자리 그대로)", lambda k, h: h / 2 if k in LONG else h, 1.0),
         ("긴 셋만 절반 + 자리 2배", lambda k, h: h / 2 if k in LONG else h, 2.0),
         ("전 규칙 2배 (자리 절반)", lambda k, h: h * 2, 0.5)]
print(f"  {'구성':<30}{'자산':>9}{'낙폭':>8}{'노출':>7}{'거래':>8}   보유일")
C_S = {}
for lbl, fn, sl in C_CFG:
    S, simulate = build(rehold(fn, sl))
    C_S[lbl] = S
    ns["S"] = S
    C, L = simulate(1.0, 1.0, "", quiet=True)
    n, m, e = stats(C)
    hs = S.groupby("rid").hold.first()
    print(f"  {lbl:<30}{n:>8.2f}배{m:>7.1f}%{e:>6.0f}%{len(L):>8,}   "
          + " ".join(f"{r}{int(hs[r])}" for r in ["P1", "P7", "D2"] if r in hs))

print(f"\n  랜덤 {SEEDS}시드 짝비교")
print(f"  {'구성':<30}{'중앙':>8}{'자산승':>9}{'낙폭승':>9}")
for lbl, fn, sl in C_CFG[1:]:
    rows = []
    for s in range(SEEDS):
        ns["S"] = shuffled(S0, s);        x, _ = simulate(1.0, 1.0, "", quiet=True)
        ns["S"] = shuffled(C_S[lbl], s);  y, _ = simulate(1.0, 1.0, "", quiet=True)
        rows.append((y.nav.iloc[-1], x.nav.iloc[-1],
                     ((y.nav/y.nav.cummax())-1).min()*100, ((x.nav/x.nav.cummax())-1).min()*100))
    R = pd.DataFrame(rows, columns=["nav", "base", "mdd", "bmdd"])
    print(f"  {lbl:<30}{R.nav.median():>7.2f}배{int((R.nav>R.base).sum()):>7}/{SEEDS}"
          f"{int((R.mdd>R.bmdd).sum()):>7}/{SEEDS}")

print(f"\n총 {time.time()-t0:.0f}초")
