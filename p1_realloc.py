# -*- coding: utf-8 -*-
"""**[조용한 신고가] 를 빼고 그 비중을 돌려주면** (2026-09-16).

앞(`p1p3_drop.py`)에서 나온 것:
  · [폭락반등]은 그대로 두기로 끝났다(빼면 16/100 · 국면조건은 48/100 동전).
  · [조용한 신고가]는 **계좌 체결 94건 평균 +2.29% · 승률 49%** — 9규칙 중 유일하게 50% 미만.
    기여 2위(+363.6%p)는 **비중이 14.4% 로 제일 커서**다(다른 규칙은 3.6~6%).
    빼면 위험이 전부 좋아지고 홀드아웃(05~15)도 2.86 → 3.46배로 좋아지는데,
    자산은 20.14 → 19.83배 · 시드중앙 21.03 → 19.36배로 진다.

**그런데 빼면 노출이 29% → 19% 로 떨어진다.** 자본의 81%가 논다. 진 이유가
'규칙이 좋아서' 가 아니라 '자리가 비어서' 일 수 있다. 그 14.4% 를 돌려주고 다시 본다.

  ① 비중을 줄이기만 — 14.4 → 10 / 7 / 4
  ② 빼고 다른 규칙에 돌려주기
  ③ 구간별·경로분포

돌려줄 후보는 계좌 체결 성적이 좋은 쪽이다(평균%·승률):
  [외인 매집] +10.27/61% · [낙폭과대] +22.91/80% · [저PBR 낙폭] +10.00/66%
  [폭락반등] +8.29/68% · [자사주 낙폭] +2.63/58%
  ⚠ [조정매집]은 3억 유동성에서 이미 한계다([[liquidity-3e]]) — 더 올리지 않는다.

    python p1_realloc.py
"""
import os, sys, time, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from pathlib import Path
from verdict import block_paths

BASE = Path(__file__).parent
NS = 100
W = 122
OUT = []
t0 = time.time()


def P(x=""):
    OUT.append(x)


def log(m):
    print("%s %s" % (time.strftime("%H:%M:%S"), m), file=sys.stderr, flush=True)


def sec(t):
    P("\n" + "=" * W + "\n" + t + "\n" + "=" * W)


SRC = (BASE / "portfolio.py").read_text(encoding="utf-8")
HEAD, REST = SRC.split("# 신호를 한 표로 모은다", 1)
MID = "# 신호를 한 표로 모은다" + REST.split("# @@ANALYSIS", 1)[0]
NM = {"P1": "조용한 신고가", "P2": "조정매집", "P3": "폭락반등", "P4": "업종붕괴 이탈",
      "P5": "자사주 낙폭", "P6": "깊은 이격", "P7": "외인 매집",
      "D1": "낙폭과대", "D2": "저PBR 낙폭"}
PCT0 = {"P1": 14.4, "P2": 18, "P3": 6, "P4": 3.6, "P5": 6, "P6": 4.8, "P7": 4.8, "D1": 6, "D2": 6}
_REAL = sys.stdout
_KEEP = []
_NS = None


def base_ns():
    """무거운 재구성은 한 번만 한다 — 비중은 신호표에서 갈아 끼울 수 있다."""
    global _NS
    if _NS is None:
        os.environ["SKIP"] = ""
        sys.stdout = _REAL
        _NS = {"__file__": str(BASE / "portfolio.py")}
        exec(compile(HEAD, "portfolio.py", "exec"), _NS)
        _KEEP.append(sys.stdout)
        exec(compile(MID, "portfolio.py", "exec"), _NS)
        _NS["_S0"] = _NS["S"].copy()
    return _NS


def shuffled(Z, seed):
    return Z.sample(frac=1.0, random_state=seed).sort_values("di", kind="stable").reset_index(drop=True)


def run(pcts, drop=(), seeds=NS):
    ns = base_ns()
    z = ns["_S0"]
    z = z[~z.rid.isin(drop)].copy()
    z["pct"] = z.rid.map(pcts).astype(float)
    sim = ns["simulate"]
    ns["S"] = z
    C, L = sim(1.0, 1.0, "", quiet=True)
    nav = C.nav.iloc[-1]
    mdd = ((C.nav / C.nav.cummax()) - 1).min() * 100
    expo = C.expo.mean() * 100
    c15 = C[C.date <= "20151231"].nav.iloc[-1]
    navs = []
    for s in range(seeds):
        ns["S"] = shuffled(z, s)
        navs.append(sim(1.0, 1.0, "", quiet=True)[0].nav.iloc[-1])
    ns["S"] = ns["_S0"]
    return dict(nav=nav, mdd=mdd, expo=expo, hold=c15, later=nav / c15,
                navs=np.array(navs), C=C, L=L)


CFG = [("지금 (P1 14.4)", dict(PCT0), ()),
       ("P1 비중 10", {**PCT0, "P1": 10}, ()),
       ("P1 비중 7", {**PCT0, "P1": 7}, ()),
       ("P1 비중 4", {**PCT0, "P1": 4}, ()),
       ("P1 빼기 (그대로)", PCT0, ("P1",)),
       ("P1 빼고 → 외인매집 9", {**PCT0, "P7": 9}, ("P1",)),
       ("P1 빼고 → 외인9·저PBR9·낙폭9", {**PCT0, "P7": 9, "D2": 9, "D1": 9}, ("P1",)),
       ("P1 빼고 → 남은 8규칙 1.5배",
        {k: (v * 1.5 if k != "P1" else v) for k, v in PCT0.items()}, ("P1",)),
       ("P1 빼고 → 남은 8규칙 2배",
        {k: (v * 2 if k != "P1" else v) for k, v in PCT0.items()}, ("P1",))]

R = {}
for lbl, pc, dr in CFG:
    log("%s 돌리는 중" % lbl)
    R[lbl] = run(pc, dr)
    log("  끝 (%.2f배)" % R[lbl]["nav"])
B = R["지금 (P1 14.4)"]

sec("① 계좌 — %d시드 짝비교 (2005~2026)" % NS)
P("  %-26s%7s%9s%9s%11s%10s%9s"
  % ("구성", "노출", "자산", "낙폭", "시드중앙", "자산승", "낙폭승"))
for lbl, _, _ in CFG:
    r = R[lbl]
    if lbl.startswith("지금"):
        P("  %-26s%6.0f%%%8.2f배%8.1f%%%10.2f배%10s%9s"
          % (lbl, r["expo"], r["nav"], r["mdd"], np.median(r["navs"]), "—", "—"))
    else:
        P("  %-26s%6.0f%%%8.2f배%8.1f%%%10.2f배%7d/%d%8s"
          % (lbl, r["expo"], r["nav"], r["mdd"], np.median(r["navs"]),
             int((r["navs"] > B["navs"]).sum()), NS, "—"))
P("\n  ※ %d/%d 이 동전이다." % (NS // 2, NS))

sec("② 구간별 — 홀드아웃(05~15)과 그 뒤(16~26)")
P("  %-26s%13s%13s%12s" % ("구성", "05~15", "16~26", "전체"))
for lbl, _, _ in CFG:
    r = R[lbl]
    P("  %-26s%12.2f배%12.2f배%11.2f배" % (lbl, r["hold"], r["later"], r["nav"]))

sec("③ 경로분포 — 위험이 얼마나 줄고 무엇을 내주나")
P("  %-26s%10s%10s%9s%9s%14s%11s"
  % ("", "실제낙폭", "낙폭중앙", "하위5%", "하위1%", "언더워터 하위5%", "자산하위5%"))
for lbl, _, _ in CFG:
    C = R[lbl]["C"]
    m = C.assign(ym=C.date.str[:6]).groupby("ym").nav.last().pct_change().dropna() * 100
    Pt = block_paths(m, n_paths=5000, mean_block=3)
    P("  %-26s%9.1f%%%9.1f%%%8.1f%%%8.1f%%%12.1f년%10.2f배"
      % (lbl, R[lbl]["mdd"], Pt.mdd.median(), np.percentile(Pt.mdd, 5),
         np.percentile(Pt.mdd, 1), np.percentile(Pt.under, 95) / 12, np.percentile(Pt.nav, 5)))

P("\n총 %.0f초" % (time.time() - t0))
sys.stdout = _REAL
print("\n".join(OUT))
