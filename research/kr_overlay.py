# -*- coding: utf-8 -*-
"""**규칙 안 스캔 통과 재료 → 국내 계좌 얹기** (2026-09-19).

규칙 안 스캔(rule_scan_kr_20260919)에서 가격 낙폭 말고 **새 재료**로 통과한 것 중 상위 둘을 계좌로 판정한다.
  · 신용잔고 20일 변화(cr_chg20) — 줄수록 좋다(D -7.45, 8/8 규칙). 지금 [폭락반등]·[업종붕괴 이탈]에만 있다.
    [깊은 이격] -11.5 · [저PBR 낙폭] -12.4 · [낙폭과대] 에서도 같은 방향 → 셋에 넣는다(문턱 -10/-15/-20).
  · 기관 합계 20일 순매수 ÷ 거래대금(q_org20, 2018~) — 기관이 살수록 좋다(D +2.99, 검증 +7.33, 8/8).
    기관이 순매도한 신호를 뺀다(문턱 -0.5 / 0 / +0.5). 자료 없는 2017 이전은 조건을 끈다.
판정은 sv_overlay.py 와 같다: 300시드 짝비교 · 구간 3분할 · 이웃 칸이 같이 이겨야.
결측(NaN)은 **산다**(조건을 끈다) — 결측을 빼면 자료 없는 종목을 걸러내는 효과가 섞인다.

    python research/kr_overlay.py      → research/reports/kr_overlay_20260919.md
"""
import os, sys, time, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(BASE)); sys.path.insert(0, str(ROOT))
from verdict import log_trials

NS = 300
OUT = []; t0 = time.time()


def P(x=""):
    OUT.append(x)


def log(m):
    print("%s %s" % (time.strftime("%H:%M:%S"), m), file=sys.stderr, flush=True)


log("portfolio.py 재구성")
SRC = (BASE / "portfolio.py").read_text(encoding="utf-8")
HEAD, REST = SRC.split("# 신호를 한 표로 모은다", 1)
MID = "# 신호를 한 표로 모은다" + REST.split("# @@ANALYSIS", 1)[0]
os.environ["SKIP"] = ""
_real = sys.stdout
ns = {"__file__": str(BASE / "portfolio.py")}
exec(compile(HEAD, "portfolio.py", "exec"), ns); exec(compile(MID, "portfolio.py", "exec"), ns)
_keep = sys.stdout; sys.stdout = _real
S0 = ns["S"].copy(); sim = ns["simulate"]
BASECOLS = list(S0.columns)

CR = pd.concat([ns["KP"][["date", "ticker", "cr_chg20"]], ns["KQ"][["date", "ticker", "cr_chg20"]]]).drop_duplicates(["date", "ticker"])
S0 = S0.merge(CR, on=["date", "ticker"], how="left")
import features as FT
FT.attach(S0, ["q_org20"], cal=sorted(set(ns["KP"].date) | set(ns["KQ"].date)))
log("  신호 %s건 · 신용 결측 %.0f%% · 기관 결측 %.0f%%" % (f"{len(S0):,}", S0.cr_chg20.isna().mean() * 100,
                                                  S0.q_org20.isna().mean() * 100))

CR3 = S0.rid.isin(["P6", "D1", "D2"])


def drop_cr(th):
    return CR3 & (S0.cr_chg20 > th)                     # 신용이 th 보다 덜 줄었으면 뺀다(결측은 산다)


def drop_org(th):
    return S0.q_org20 < th                              # 기관 순매수가 th 미만이면 뺀다(결측은 산다)


CFG = [("지금 (그대로)", None),
       ("신용 -10 → [깊은 이격]·[낙폭과대]·[저PBR 낙폭]", drop_cr(-10)),
       ("신용 -15 (원안)", drop_cr(-15)),
       ("신용 -20", drop_cr(-20)),
       ("기관 순매수 -0.5% 미만 빼기", drop_org(-0.5)),
       ("기관 순매수 0 미만 빼기 (원안)", drop_org(0)),
       ("기관 순매수 +0.5% 미만 빼기", drop_org(0.5))]


def shuffled(Z, seed):
    return Z.sample(frac=1.0, random_state=seed).sort_values("di", kind="stable").reset_index(drop=True)


def run(Z):
    ns["S"] = Z
    C, _ = sim(1.0, 1.0, "", quiet=True)
    nav = C.nav.iloc[-1]; mdd = ((C.nav / C.nav.cummax()) - 1).min() * 100
    c15 = C[C.date <= "20151231"].nav.iloc[-1]; c22 = C[C.date <= "20221231"].nav.iloc[-1]
    navs = []
    for s in range(NS):
        ns["S"] = shuffled(Z, s)
        navs.append(sim(1.0, 1.0, "", quiet=True)[0].nav.iloc[-1])
    return dict(nav=nav, mdd=mdd, expo=C.expo.mean() * 100, navs=np.array(navs),
                hold=c15, mid=c22 / c15, late=nav / c22, n=len(Z))


S0["r"] = (S0.exit / S0.buy - 1) * 100 - S0.cost
P("# 규칙 안 스캔 통과 재료 → 국내 계좌 얹기")
P("")
P("## 빠지는 신호와 그 성적 (보유기간 끝 종가 청산·비용 차감)")
P("")
P("| 구성 | 빠지는 신호 | 빠지는 쪽 중앙 | 남는 쪽 중앙 | 규칙별 빠지는 수 |")
P("|---|---|---|---|---|")
for lbl, m in CFG[1:]:
    d = S0[m]; k = S0[~m]
    P("| %s | %s | %+.2f | %+.2f | %s |" % (lbl, f"{len(d):,}", d.r.median(), k.r.median(),
                                         " ".join("%s:%d" % kv for kv in d.rid.value_counts().items())))

R = {}
for lbl, m in CFG:
    log(lbl)
    Z = (S0 if m is None else S0[~m])[BASECOLS].reset_index(drop=True)
    R[lbl] = run(Z)
    log("  %.2f배" % R[lbl]["nav"])
B = R[CFG[0][0]]
P("")
P("## 계좌 — %d시드 짝비교" % NS)
P("")
P("| 구성 | 신호 | 노출 | 자산 | 낙폭 | 시드 중앙 | 시드 최악 | 자산 이긴 시드 | 홀드아웃 05~15 | 학습 16~22 | 검증 23~26 |")
P("|---|---|---|---|---|---|---|---|---|---|---|")
for lbl, _ in CFG:
    r = R[lbl]
    w = "—" if r is B else "%d/%d" % (int((r["navs"] > B["navs"]).sum()), NS)
    P("| %s | %s | %.0f%% | %.2f배 | %.1f%% | %.2f배 | %.2f배 | %s | %.2f배 | %.2f배 | %.2f배 |" % (
        lbl, f"{r['n']:,}", r["expo"], r["nav"], r["mdd"], np.median(r["navs"]), r["navs"].min(), w,
        r["hold"], r["mid"], r["late"]))
P("")
P("※ 이웃 칸(문턱 양옆)까지 같이 이기고 검증 23~26 도 나아져야 채택 후보. 한 칸만 이기면 운.")
P("총 %.0f초" % (time.time() - t0))
log_trials("kr_overlay_20260919", len(CFG) - 1)
rp = ROOT / "reports" / "kr_overlay_20260919.md"
rp.write_text("\n".join(OUT) + "\n", encoding="utf-8")
print("\n".join(OUT))
