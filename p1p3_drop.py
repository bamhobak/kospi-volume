# -*- coding: utf-8 -*-
"""**[폭락반등]·[조용한 신고가] 를 뺄까 — 계좌 판정** (2026-09-16 요청).

해부(`p1p3_autopsy.py`)에서 둘 다 **구조적 약점**이 나왔다.

  [폭락반등] — V자 반등형 사건에서만 통한다
    2008 중앙 **-8.56**(40%) · 2011 **-4.00**(29%)  ← 계단식으로 내려가는 진짜 위기에서 실패
    2018 +13.40(87%) · 2020 **+35.35(98%, 308건)** · 2022 +9.50 · 2023~26 +18.92
    전체 509건 중 **308건(60%)이 2020년 한 해**다.
    제도 탓이 아니다 — 같은 2005~2015 에서 [깊은 이격]은 +11.31(68%), 2008년만 봐도
    1,587건 +11.79(68%) 로 같은 폭락을 먹었다.

  [조용한 신고가] — 강세장에만 신호가 나고, 없는 해엔 0건이다
    홀드 05~15 중앙 **-3.37**(승률 35%) · 05~09 -2.72(38%) · 10~15 -3.87(32%)
    신호 건수: 2016~19 **0건** · 2020 48 · 2021 57 · 2022 **0건** · 2023 23 · 2024 137 · 2025 9 · 2026 0
    2025 중앙 **-13.4%**.
    제도 탓이 아니다 — 같은 상승 규칙 [외인 매집]은 홀드아웃에서 +4.89(62%) 였다.

⚠ 그래도 **뺄지 말지는 계좌가 정한다**([[contrib-not-removal]]). [업종붕괴 이탈]은 거래별
   성적이 꼴찌였는데 빼니까 21.65 → 19.21배로 떨어졌다. 신호가 많은 규칙은 다른 규칙이
   쉴 때 노출을 채우고, 상관이 낮으면 평균이 낮아도 낙폭을 눌러 준다.

계좌는 2005~2026 전 구간(21.7년)이다 — 홀드아웃이 이미 들어 있다.

  ① 빼고 돌리기 (100시드 짝비교)
  ② 구간별 — 홀드 05~15 / 16~26 따로
  ③ 경로분포
  ④ 규칙별 체결 — 뺀 자리를 누가 메우나

    python p1p3_drop.py
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


# ⚠ portfolio.py 는 첫 줄에서 `sys.stdout = io.TextIOWrapper(sys.stdout.buffer, ...)` 를 한다.
#   두 번 넘게 exec 하면 앞 래퍼가 정리되면서 밑의 버퍼가 닫혀 "I/O operation on closed file"
#   로 죽는다. 원래 stdout 을 붙들어 두고 매번 되돌린 뒤, 만들어진 래퍼도 참조를 남겨 둔다.
_REAL = sys.stdout
_KEEP = []


def build(skip=""):
    os.environ["SKIP"] = skip
    sys.stdout = _REAL
    ns = {"__file__": str(BASE / "portfolio.py")}
    exec(compile(HEAD, "portfolio.py", "exec"), ns)
    _KEEP.append(sys.stdout)
    exec(compile(MID, "portfolio.py", "exec"), ns)
    return ns


def build_gate(maxdays, skip=""):
    """[폭락반등]에 **지수 60일선 아래 연속일수 ≤ maxdays** 를 얹은 판.

    해부에서 나온 축이다 — 60일선 아래 60일 넘게 있으면 승률 40%, 그 전이면 88~100%.
    '이미 오래 내려간 장에서는 반등을 사지 마라' 라는 뜻이고, 2008·2011 이 거기 걸린다.
    """
    os.environ["SKIP"] = skip
    sys.stdout = _REAL
    ns = {"__file__": str(BASE / "portfolio.py")}
    exec(compile(HEAD, "portfolio.py", "exec"), ns)
    _KEEP.append(sys.stdout)
    IX = ns["IX"].sort_values("date").reset_index(drop=True)
    bl = (IX.Close < IX.ma60).astype(int)
    IX["belowN"] = bl.groupby((bl == 0).cumsum()).cumsum()
    BN = dict(zip(IX.date, IX.belowN))
    KP = ns["KP"]
    okd = KP.date.map(BN).fillna(0) <= maxdays
    K, h, stp, pc, mxx, cd = ns["RULES"]["P3"]
    ns["RULES"]["P3"] = (K, h, stp, pc, mxx, cd & okd.values)
    exec(compile(MID, "portfolio.py", "exec"), ns)
    return ns


def shuffled(Z, seed):
    return Z.sample(frac=1.0, random_state=seed).sort_values("di", kind="stable").reset_index(drop=True)


def run(ns, seeds=NS):
    S0, sim = ns["S"], ns["simulate"]
    C, L = sim(1.0, 1.0, "", quiet=True)
    nav = C.nav.iloc[-1]
    mdd = ((C.nav / C.nav.cummax()) - 1).min() * 100
    expo = C.expo.mean() * 100
    # 구간 나누기 — 곡선에서 잘라 본다
    c15 = C[C.date <= "20151231"].nav.iloc[-1]
    seg = dict(hold=c15, later=nav / c15)
    navs = []
    for s in range(seeds):
        ns["S"] = shuffled(S0, s)
        navs.append(sim(1.0, 1.0, "", quiet=True)[0].nav.iloc[-1])
    ns["S"] = S0
    return dict(nav=nav, mdd=mdd, expo=expo, navs=np.array(navs), C=C, L=L, **seg)


CFG = [("지금 (9규칙)", ""), ("[폭락반등] 빼기", "P3"),
       ("[조용한 신고가] 빼기", "P1"), ("둘 다 빼기", "P1,P3"),
       ("[폭락반등] 국면조건 ≤40일", ("gate", 40)),
       ("[폭락반등] 국면조건 ≤60일", ("gate", 60)),
       ("국면조건60 + [조용한] 빼기", ("gate", 60, "P1"))]
R = {}
for lbl, sk in CFG:
    log("%s 돌리는 중" % lbl)
    if isinstance(sk, tuple):
        R[lbl] = run(build_gate(sk[1], sk[2] if len(sk) > 2 else ""))
    else:
        R[lbl] = run(build(sk))
    log("  끝")
B = R["지금 (9규칙)"]

sec("① 빼고 돌리기 — %d시드 짝비교 (2005~2026 · 21.7년)" % NS)
P("  %-22s%7s%9s%9s%11s%10s%9s"
  % ("구성", "노출", "자산", "낙폭", "시드중앙", "자산승", "낙폭승"))
for lbl, _ in CFG:
    r = R[lbl]
    if lbl.startswith("지금"):
        P("  %-22s%6.0f%%%8.2f배%8.1f%%%10.2f배%10s%9s"
          % (lbl, r["expo"], r["nav"], r["mdd"], np.median(r["navs"]), "—", "—"))
    else:
        P("  %-22s%6.0f%%%8.2f배%8.1f%%%10.2f배%7d/%d%6s"
          % (lbl, r["expo"], r["nav"], r["mdd"], np.median(r["navs"]),
             (r["navs"] > B["navs"]).sum(), NS, "—"))
P("\n  ※ %d/%d 이 동전이다. 빼는 쪽이 이겨야 뺄 근거가 된다." % (NS // 2, NS))

sec("② 구간별 — 홀드아웃(05~15)과 그 뒤(16~26)를 따로")
P("  %-22s%14s%14s%12s" % ("구성", "05~15", "16~26", "전체"))
for lbl, _ in CFG:
    r = R[lbl]
    P("  %-22s%13.2f배%13.2f배%11.2f배" % (lbl, r["hold"], r["later"], r["nav"]))
P("\n  ※ 05~15 는 규칙을 만들 때 **안 본 구간**이다. 거기서 빼는 쪽이 나으면 진짜 짐이었다는 뜻이다.")

sec("③ 경로분포")
P("  %-22s%10s%10s%9s%9s%14s%11s"
  % ("", "실제낙폭", "낙폭중앙", "하위5%", "하위1%", "언더워터 하위5%", "자산하위5%"))
for lbl, _ in CFG:
    C = R[lbl]["C"]
    m = C.assign(ym=C.date.str[:6]).groupby("ym").nav.last().pct_change().dropna() * 100
    Pt = block_paths(m, n_paths=5000, mean_block=3)
    P("  %-22s%9.1f%%%9.1f%%%8.1f%%%8.1f%%%12.1f년%10.2f배"
      % (lbl, R[lbl]["mdd"], Pt.mdd.median(), np.percentile(Pt.mdd, 5),
         np.percentile(Pt.mdd, 1), np.percentile(Pt.under, 95) / 12, np.percentile(Pt.nav, 5)))

sec("④ 규칙별 체결 — 뺀 자리를 누가 메우나")
for lbl, _ in CFG:
    L = R[lbl]["L"]
    P("\n  [%s]  노출 %.0f%%" % (lbl, R[lbl]["expo"]))
    P("    %-16s%8s%9s%8s%11s" % ("규칙", "체결", "평균%", "승률", "기여%p"))
    for r in ["P1", "P7", "P2", "P3", "P4", "P5", "P6", "D1", "D2"]:
        z = L[L.rid == r]
        if not len(z):
            continue
        P("    %-16s%8s%+9.2f%7.0f%%%+11.1f"
          % (NM[r], f"{len(z):,}", z.ret.mean(), (z.ret > 0).mean() * 100,
             (z.amt * z.ret / 100).sum() * 100))

P("\n총 %.0f초" % (time.time() - t0))
sys.stdout = _REAL
print("\n".join(OUT))
