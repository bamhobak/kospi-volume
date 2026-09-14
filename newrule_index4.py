# -*- coding: utf-8 -*-
"""**지수 제외 4차 — 계좌 판정 + 겹침 검사** (2026-09-15).

3차에서 생존편향은 깨끗했다. 제외 이벤트 2,101건 중 400건이 패널에 없는데, 그중 372건은
**이미 거래가 끊긴 뒤**(마지막 거래일로부터 중앙 18일 뒤) 월별 스냅샷이 뒤늦게 반영한
것이다 — 그 시점엔 살 수가 없으니 표본에서 빠지는 게 맞다. 수익률 결측도 0.14%뿐이다.

이제 남은 관문 셋.
  ① **계좌** — 규칙 단위 통과는 절반이다. 자리 경쟁·현금 제약에 넣어야 진짜다.
     (stock_fg·short_program 은 규칙 단위로 통과했다가 계좌에서 기각됐다)
  ② **겹침** — 목적이 '기존 9규칙이 쉬는 날을 채우는 것' 이었다. 같은 종목을 같은 때
     사고 있으면 새 후보가 아니라 중복이다.
  ③ **최근 해** — 2차에서 2024년 제외 10일 중앙이 -6.1% 였다. 최근 해 성적은 필수 기준이다.

⚠ 지수 자료가 2018-02~ 라 새 규칙은 그 뒤에만 신호를 낸다. 계좌 비교는 **2018~2026**
   구간을 따로 봐야 공정하다(2005~17 은 새 규칙이 아예 없어 희석된다).

    python newrule_index4.py           (시드 12)
"""
import sqlite3, sys, time, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
from pathlib import Path

BASE = Path(__file__).parent
SEEDS = int(sys.argv[1]) if len(sys.argv) > 1 else 12
W = 108
NAME = {"P1": "조용한 신고가", "P2": "조정매집", "P3": "폭락반등", "P4": "업종붕괴 이탈",
        "P5": "자사주 낙폭", "P6": "깊은 이격", "P7": "외인 매집",
        "D1": "낙폭과대", "D2": "저PBR 낙폭", "IX": "지수 제외"}


def sec(t): print("\n" + "=" * W + f"\n{t}\n" + "=" * W)


SRC = (BASE / "portfolio.py").read_text(encoding="utf-8")
HEAD, REST = SRC.split("# 신호를 한 표로 모은다", 1)
MID = "# 신호를 한 표로 모은다" + REST.split("# @@ANALYSIS", 1)[0]
ns = {"__file__": str(BASE / "portfolio.py")}
t0 = time.time()
exec(compile(HEAD, "portfolio.py", "exec"), ns)
print(f"패널 적재 {time.time()-t0:.0f}초")
KP, KQ, base, RULES0 = ns["KP"], ns["KQ"], ns["base"], dict(ns["RULES"])

# ── 이벤트 붙이기 ────────────────────────────────────────────────────────
con = sqlite3.connect(BASE / "data/index_members.db")
M = pd.read_sql("SELECT idx,date,ticker FROM members", con)
M["ticker"] = M.ticker.astype(str).str.zfill(6)
cal = np.array(sorted(set(KP.date) | set(KQ.date)))


def onday(s):
    i = np.searchsorted(cal, s, "left")
    return cal[i] if i < len(cal) else None


EV = []
for ix, g in M.groupby("idx"):
    ds = sorted(g.date.unique()); mem = {d: set(g[g.date == d].ticker) for d in ds}
    for a, b in zip(ds, ds[1:]):
        d = onday(b)
        if d is None: continue
        for t in mem[a] - mem[b]: EV.append((t, d))
KEY = set(t + d for t, d in EV)
for K in (KP, KQ):
    K["ixout"] = (K.ticker + K.date).isin(KEY)
print(f"제외 이벤트 {len(KEY):,}개 · 코스피 행 {int(KP.ixout.sum()):,} · 코스닥 행 {int(KQ.ixout.sum()):,}")

# ── 새 규칙 후보 (RULES 형식: K, hold, stop, pct, mx, cond) ───────────────
KB = pd.concat([KP, KQ], ignore_index=True).sort_values(["ticker", "date"]).reset_index(drop=True)
KB["pref"] = ~KB.ticker.str.endswith("0")
if "jw" in KP.columns:
    KB["jw"] = pd.concat([KP.jw, KQ.jw], ignore_index=True).values
CAND = {
    "IX50_20": (KB, 20, None, 5, 3, base(KB, 3) & KB.ixout & (KB.fromhi <= -50)),
    "IX50_10": (KB, 10, None, 5, 3, base(KB, 3) & KB.ixout & (KB.fromhi <= -50)),
    "IX30_20": (KB, 20, None, 5, 3, base(KB, 3) & KB.ixout & (KB.fromhi <= -30)),
    "IX30_10": (KB, 10, None, 5, 3, base(KB, 3) & KB.ixout & (KB.fromhi <= -30)),
}


def build(rules):
    ns["RULES"] = dict(rules)
    exec(compile(MID, "portfolio.py", "exec"), ns)
    return ns["S"], ns["simulate"]


def stats(C, lo=None):
    c = C if lo is None else C[C.date >= lo]
    n = c.nav.iloc[-1] / c.nav.iloc[0]
    return n, ((c.nav / c.nav.cummax()) - 1).min() * 100, c.expo.mean() * 100


def shuffled(Z, seed):
    return Z.sample(frac=1.0, random_state=seed).sort_values("di", kind="stable").reset_index(drop=True)


S0, simulate = build(RULES0)
C0, L0 = simulate(1.0, 1.0, "", quiet=True)

sec("① 계좌 — 새 규칙을 얹으면 (2005~26 전체 · 2018~26 구간 각각)")
print(f"  {'구성':<24}{'전체 자산':>10}{'낙폭':>8}{'노출':>7}   {'2018~ 자산':>11}{'낙폭':>8}{'노출':>7}{'거래':>7}")
a1, m1, e1 = stats(C0); a2, m2, e2 = stats(C0, "20180101")
print(f"  {'기준 9규칙':<24}{a1:>9.2f}배{m1:>7.1f}%{e1:>6.0f}%   {a2:>10.2f}배{m2:>7.1f}%{e2:>6.0f}%{len(L0):>7,}")
OUT = {}
for k, v in CAND.items():
    S, simulate = build({**RULES0, "IX": v})
    OUT[k] = S
    C, L = simulate(1.0, 1.0, "", quiet=True)
    a1, m1, e1 = stats(C); a2, m2, e2 = stats(C, "20180101")
    nix = int((L.rid == "IX").sum()) if len(L) else 0
    lbl = f"+지수제외 {k.split('_')[0][2:]}% {k.split('_')[1]}일"
    print(f"  {lbl:<24}{a1:>9.2f}배{m1:>7.1f}%{e1:>6.0f}%   {a2:>10.2f}배{m2:>7.1f}%{e2:>6.0f}%{len(L):>7,}"
          f"   (그중 새 규칙 체결 {nix}건)")

sec(f"② 랜덤 {SEEDS}시드 짝비교 — 2018~26 구간 (새 규칙이 실제로 도는 구간)")
print(f"  {'구성':<24}{'중앙':>9}{'최악':>9}{'최고':>9}{'자산승':>8}{'낙폭승':>8}")
for k in CAND:
    rows = []
    for s in range(SEEDS):
        ns["S"] = shuffled(S0, s);      x, _ = simulate(1.0, 1.0, "", quiet=True)
        ns["S"] = shuffled(OUT[k], s);  y, _ = simulate(1.0, 1.0, "", quiet=True)
        ax = x[x.date >= "20180101"]; ay = y[y.date >= "20180101"]
        rows.append((ay.nav.iloc[-1]/ay.nav.iloc[0], ax.nav.iloc[-1]/ax.nav.iloc[0],
                     ((ay.nav/ay.nav.cummax())-1).min()*100, ((ax.nav/ax.nav.cummax())-1).min()*100))
    R = pd.DataFrame(rows, columns=["nav", "base", "mdd", "bmdd"])
    lbl = f"+지수제외 {k.split('_')[0][2:]}% {k.split('_')[1]}일"
    print(f"  {lbl:<24}{R.nav.median():>8.2f}배{R.nav.min():>8.2f}배{R.nav.max():>8.2f}배"
          f"{int((R.nav>R.base).sum()):>6}/{SEEDS}{int((R.mdd>R.bmdd).sum()):>6}/{SEEDS}")

sec("③ 겹침 — 새 규칙이 정말 '빈 날' 을 채우나")
best = "IX50_20"
S = OUT[best]
ix = S[S.rid == "IX"]
old = S[S.rid != "IX"]
print(f"  새 규칙 신호 {len(ix):,}건 (2018~)")
oldkey = {}
for t, d in zip(old.ticker.values, old.di.values): oldkey.setdefault(t, []).append(d)
near = sum(1 for t, d in zip(ix.ticker.values, ix.di.values)
           if any(abs(d - x) <= 5 for x in oldkey.get(t, [])))
print(f"  같은 종목을 ±5거래일 안에 기존 규칙도 잡은 건 {near:,}건 ({near/max(len(ix),1):.0%})")
# 새 규칙이 신호를 낸 날, 기존 계좌의 노출은 얼마였나
expo = dict(zip(C0.date, C0.expo))
e = pd.Series([expo.get(d, np.nan) for d in ix.date]) * 100
allday = C0[C0.date >= "20180101"].expo * 100
print(f"  새 신호가 난 날의 기존 노출 중앙 {e.median():.0f}% (그 구간 평상시 중앙 {allday.median():.0f}%)")
print(f"    기존 노출 10% 미만인 날에 난 신호 {int((e < 10).sum()):,}건 ({(e<10).mean():.0%})"
      f" · 40% 이상인 날 {int((e >= 40).sum()):,}건 ({(e>=40).mean():.0%})")
print("  ※ 평상시보다 낮은 노출일에 몰려 있으면 '빈 날을 채운다' 가 맞다")

sec("④ 연도별 — 새 규칙 체결분만")
S, simulate = build({**RULES0, "IX": CAND[best]})
C, L = simulate(1.0, 1.0, "", quiet=True)
z = L[L.rid == "IX"].copy()
if len(z):
    z["yr"] = z.date.str[:4]
    print(f"  {'연도':<7}{'체결':>6}{'평균%':>9}{'중앙%':>9}{'승률':>7}{'기여%p':>9}")
    for y, g in z.groupby("yr"):
        print(f"  {y:<7}{len(g):>6}{g.ret.mean():>+9.2f}{g.ret.median():>+9.2f}"
              f"{(g.ret>0).mean():>7.0%}{(g.amt*g.ret/100).sum()*100:>9.2f}")
    print(f"  {'전체':<7}{len(z):>6}{z.ret.mean():>+9.2f}{z.ret.median():>+9.2f}"
          f"{(z.ret>0).mean():>7.0%}{(z.amt*z.ret/100).sum()*100:>9.2f}")
print(f"\n총 {time.time()-t0:.0f}초")
