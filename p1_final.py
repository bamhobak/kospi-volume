# -*- coding: utf-8 -*-
"""**[조용한 신고가] 최종 판정 — 300시드 · 다중검정 · 3억 유동성** (2026-09-16).

여기까지 나온 것:
  · 규칙 단위 중앙 **+0.94** · 절삭 **+0.79** — 9규칙 중 압도적 꼴찌(2위 [자사주 낙폭]의 1/5)
  · 계좌 체결 94건 평균 +2.29% · 승률 **49%** — 9규칙 중 유일하게 50% 미만
  · 홀드아웃 05~15 는 PF **0.53**(손실). 문턱을 백분위로 바꿔도 -1.6~-2.2% 로 그대로
  · 빼고 비중을 돌려주면 **같은 노출 29% 에서 20.14 → 41.96배**(100/100), 홀드아웃도 2.86 → 4.61배

⚠ 그런데 이건 본질적으로 **비중 최적화**다. 성적 좋은 규칙에 몰아주면 과거 성적은 당연히 오른다.
   확정 전에 셋을 본다.
     ① **300시드** — 100/100 이 유지되나([[hype-rally]]: 30시드에 두 번 데였다)
     ② **다중검정** — 비중 조합을 여러 개 돌린 뒤라 보정이 필요하다
     ③ **3억 유동성** — 비중을 1.5배 올리면 슬리피지가 감당되나([[liquidity-3e]])
   그리고 이긴 한 칸만 보지 않는다 — **이웃한 배분도 같이** 좋아야 진짜다.

    python p1_final.py
"""
import io, os, sys, time, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from pathlib import Path
from verdict import deflated_sharpe

BASE = Path(__file__).parent
NS = 300
KIMP = 0.30            # 제곱근 시장충격 계수(왕복 2회) — liquidity_3e.py 와 같다
W = 126
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

log("portfolio.py 재구성")
os.environ["SKIP"] = ""
ns = {"__file__": str(BASE / "portfolio.py")}
exec(compile(HEAD, "portfolio.py", "exec"), ns)
exec(compile(MID, "portfolio.py", "exec"), ns)
S0 = ns["S"].copy()
sim = ns["simulate"]
log("  신호 %s건" % f"{len(S0):,}")


def make(pcts, drop=(), cap=None):
    z = S0[~S0.rid.isin(drop)].copy()
    z["pct"] = z.rid.map(pcts).astype(float)
    if cap:                      # 3억 계좌의 시장충격을 비용에 더한다
        part = (cap * z.pct / 100) / (z.amt20.astype(float) * 10000) * 100
        z["cost"] = z.cost + KIMP * np.sqrt(np.maximum(part.fillna(0), 0)) * 2
    return z


def shuffled(Z, seed):
    return Z.sample(frac=1.0, random_state=seed).sort_values("di", kind="stable").reset_index(drop=True)


def run(pcts, drop=(), cap=None, seeds=NS):
    z = make(pcts, drop, cap)
    ns["S"] = z
    C, _ = sim(1.0, 1.0, "", quiet=True)
    nav = C.nav.iloc[-1]
    mdd = ((C.nav / C.nav.cummax()) - 1).min() * 100
    expo = C.expo.mean() * 100
    c15 = C[C.date <= "20151231"].nav.iloc[-1]
    c22 = C[C.date <= "20221231"].nav.iloc[-1]
    navs = []
    for s in range(seeds):
        ns["S"] = shuffled(z, s)
        navs.append(sim(1.0, 1.0, "", quiet=True)[0].nav.iloc[-1])
    ns["S"] = S0
    mo = C.assign(ym=C.date.str[:6]).groupby("ym").nav.last().pct_change().dropna() * 100
    return dict(nav=nav, mdd=mdd, expo=expo, navs=np.array(navs), mo=mo,
                hold=c15, mid=c22 / c15, late=nav / c22)


W9 = {**PCT0, "P7": 9, "D2": 9, "D1": 9}
CFG = [
    ("지금 (P1 14.4)", PCT0, ()),
    ("P1 비중 10", {**PCT0, "P1": 10}, ()),
    ("P1 빼고 → 외인9·저PBR9·낙폭9", W9, ("P1",)),
    ("이웃: 외인8·저PBR8·낙폭8", {**PCT0, "P7": 8, "D2": 8, "D1": 8}, ("P1",)),
    ("이웃: 외인10·저PBR10·낙폭10", {**PCT0, "P7": 10, "D2": 10, "D1": 10}, ("P1",)),
    ("이웃: 8규칙 골고루 +1.8", {k: (v + 1.8 if k != "P1" else v) for k, v in PCT0.items()}, ("P1",)),
]
R = {}
for lbl, pc, dr in CFG:
    log("%s" % lbl)
    R[lbl] = run(pc, dr)
    log("  %.2f배 (시드중앙 %.2f)" % (R[lbl]["nav"], np.median(R[lbl]["navs"])))
B = R["지금 (P1 14.4)"]

sec("① %d시드 짝비교 — 이긴 한 칸만 보지 않고 **이웃도 같이** 본다" % NS)
P("  %-28s%7s%9s%9s%11s%11s%10s"
  % ("구성", "노출", "자산", "낙폭", "시드중앙", "시드최악", "자산승"))
for lbl, _, _ in CFG:
    r = R[lbl]
    tail = ("%10s" % "—") if lbl.startswith("지금") else ("%7d/%d" % (int((r["navs"] > B["navs"]).sum()), NS))
    P("  %-28s%6.0f%%%8.2f배%8.1f%%%10.2f배%10.2f배%s"
      % (lbl, r["expo"], r["nav"], r["mdd"], np.median(r["navs"]), r["navs"].min(), tail))
P("\n  ※ %d/%d 이 동전이다. 이웃 칸까지 같이 이겨야 한 칸의 운이 아니다." % (NS // 2, NS))

sec("② 구간 3분할 — 홀드아웃(05~15) · 학습(16~22) · 검증(23~26)")
P("  %-28s%13s%13s%13s%12s" % ("구성", "홀드 05~15", "학습 16~22", "검증 23~26", "전체"))
for lbl, _, _ in CFG:
    r = R[lbl]
    P("  %-28s%12.2f배%12.2f배%12.2f배%11.2f배"
      % (lbl, r["hold"], r["mid"], r["late"], r["nav"]))

sec("③ 다중검정 보정 — 비중 조합을 여러 개 돌린 뒤다")
NT = 9 + 7 + len(CFG)      # p1_realloc 9칸 + p1p3_drop 7칸 + 여기 6칸
P("  (돌린 칸 %d개로 보정 · 월수익 기준 · '진짜일 확률' 95%% 이상이면 통과)\n" % NT)
P("  %-28s%8s%9s%10s%12s%10s" % ("구성", "월수", "샤프", "문턱샤프", "진짜일확률", "판정"))
for lbl, _, _ in CFG:
    d = deflated_sharpe(R[lbl]["mo"], NT)
    if not d:
        P("  %-28s (못 잼)" % lbl); continue
    P("  %-28s%8d%9.3f%10.3f%11.1f%%%10s"
      % (lbl, d["T"], d["sr"], d["sr0"], d["dsr"] * 100,
         "통과" if d["dsr"] >= 0.95 else "**기각**"))

sec("④ 3억 유동성 — 비중을 1.5배 올리면 슬리피지가 감당되나")
P("  슬리피지 = 0.30 × √(참여율%) × 2 (왕복) · 12시드\n")
P("  %-28s%10s%10s%12s%12s" % ("구성", "무제한", "3억 자산", "3억 시드중앙", "깎인 비율"))
for lbl, pc, dr in [CFG[0], CFG[1], CFG[2]]:
    a = R[lbl]["nav"]
    r3 = run(pc, dr, cap=30000, seeds=12)
    P("  %-28s%9.2f배%9.2f배%11.2f배%11.0f%%"
      % (lbl, a, r3["nav"], np.median(r3["navs"]), (1 - r3["nav"] / a) * 100))

sec("⑤ 비중을 올린 규칙의 시장충격 — 3억 기준")
z = make(W9, ("P1",))
P("  %-16s%10s%12s%12s%12s%10s" % ("규칙", "비중", "종목당(만원)", "중앙 충격", "하위10% 때", "5%↑ 비율"))
for r in ["P7", "D2", "D1", "P2", "P3", "P5", "P6", "P4"]:
    zz = z[(z.rid == r) & z.amt20.notna()]
    if not len(zz):
        continue
    amt = 30000 * W9[r] / 100
    part = amt / (zz.amt20.astype(float) * 10000) * 100
    P("  %-16s%9.1f%%%12s%11.2f%%%11.2f%%%9.0f%%"
      % (NM[r], W9[r], f"{amt:,.0f}", part.median(), part.quantile(0.90), (part >= 5).mean() * 100))
P("\n  ※ 충격 5% 를 넘는 거래가 많으면 실제로는 그 가격에 못 산다([[liquidity-3e]]).")

P("\n총 %.0f초" % (time.time() - t0))
io.open(BASE / "_p1final_out.txt", "w", encoding="utf-8").write("\n".join(OUT))
log("결과를 _p1final_out.txt 에 썼다")
