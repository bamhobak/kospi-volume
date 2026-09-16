# -*- coding: utf-8 -*-
"""**규칙 우선순위 — 살 수 있는 종목이 한정일 때 어느 규칙부터 사나** (2026-09-17 요청).

사용자 결정: "규칙을 빼지 말고 우선순위를 두자. 모든 규칙이 다 걸려 있고 내가 살 수 있는
             종목은 한정적일 때, 어떤 규칙부터 사는 게 자산 증식에 좋은지."

지금 정책은 **규칙과 무관하게 그날 거래대금 큰 순**이다(portfolio.py). 그런데 모델 계좌는 평균
노출이 29% 라 돈이 모자랄 일이 드물어 순서가 거의 안 먹힌다. 사용자 질문은 **자리가 모자랄 때**
이므로 그 상황을 직접 만든다 — **동시 보유 N종목 · 종목당 균등(계좌/N)**. 실전 계좌(종목당
균등 금액)와 같은 꼴이다.

⚠ 과적합을 피하는 법: 순위를 전 구간 성적으로 매기면 답을 보고 정한 것이다.
   **순위는 학습(2016~22) 성적으로만 정하고, 홀드아웃(05~15)·검증(23~26)에서 시험한다.**

⚠ 돈이 한정일 땐 '건당 수익' 보다 **'돈이 묶이는 하루당 수익'** 이 중요할 수 있다.
   [업종붕괴 이탈]·[깊은 이격]은 5일, [외인 매집]은 60일 보유다. 같은 수익이면 5일짜리가
   같은 돈을 12번 굴린다. 이 가설도 같이 본다.

정책(같은 규칙 안의 순서는 시드마다 무작위 — 한 경로의 운을 지운다):
  현행      거래대금 큰 순(규칙 무관)
  무작위    전부 무작위 — 기준선
  절삭순    학습기간 절삭평균 높은 규칙부터
  일당순    학습기간 절삭평균 ÷ 보유일 높은 규칙부터(돈 효율)
  승률순    학습기간 승률 높은 규칙부터
  짧은보유  보유일 짧은 규칙부터(회전)
  역순      절삭평균 낮은 규칙부터 — 이게 이기면 뭔가 틀렸다(점검용)

    python rule_priority.py
"""
import io, os, sys, time, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from pathlib import Path

BASE = Path(__file__).parent
NS = 60
W = 130
OUT = []
t0 = time.time()
_REAL = sys.stdout


def P(x=""):
    OUT.append(x)


def log(m):
    print("%s %s" % (time.strftime("%H:%M:%S"), m), file=sys.stderr, flush=True)


def sec(t):
    P("\n" + "=" * W + "\n" + t + "\n" + "=" * W)


NM = {"P1": "조용한 신고가", "P2": "조정매집", "P3": "폭락반등", "P4": "업종붕괴 이탈",
      "P5": "자사주 낙폭", "P6": "깊은 이격", "P7": "외인 매집",
      "D1": "낙폭과대", "D2": "저PBR 낙폭"}
RIDS = ["P1", "P2", "P3", "P4", "P5", "P6", "P7", "D1", "D2"]

log("portfolio.py 재구성")
SRC = (BASE / "portfolio.py").read_text(encoding="utf-8")
HEAD, REST = SRC.split("# 신호를 한 표로 모은다", 1)
MID = "# 신호를 한 표로 모은다" + REST.split("# @@ANALYSIS", 1)[0]
os.environ["SKIP"] = ""
ns = {"__file__": str(BASE / "portfolio.py")}
exec(compile(HEAD, "portfolio.py", "exec"), ns)
exec(compile(MID, "portfolio.py", "exec"), ns)
S = ns["S"].copy()
DATES = ns["dates"]
hit = S.stop.notna() & ((S.low / S.buy - 1) * 100 <= -S.stop * 100)
S["ret"] = np.where(hit, -S.stop * 100 - S.cost, (S.exit / S.buy - 1) * 100 - S.cost)
S = S.dropna(subset=["ret", "di"]).reset_index(drop=True)
S["di"] = S.di.astype(int)
HOLD = S.groupby("rid").hold.first().astype(int).to_dict()
log("  신호 %s건" % f"{len(S):,}")

SEG = [("홀드 05~15", "20050101", "20151231"), ("학습 16~22", "20160101", "20221231"),
       ("검증 23~26", "20230101", "20301231")]


def dedup(z):
    """같은 종목이 보유기간 안에 또 걸린 건 하나로 — 규칙 성적을 부풀리지 않게."""
    z = z.sort_values("di")
    keep, last = [], {}
    for t, i, h, ix in zip(z.ticker.values, z.di.values, z.hold.values, z.index):
        if last.get(t, -10 ** 9) >= i:
            continue
        last[t] = i + int(h)
        keep.append(ix)
    return z.loc[keep]


def rule_stats(a, b):
    out = {}
    for r in RIDS:
        z = dedup(S[(S.rid == r) & (S.date >= a) & (S.date <= b)])
        v = z.ret
        if len(v) < 5:
            out[r] = dict(n=len(v), med=np.nan, trim=np.nan, win=np.nan, perday=np.nan)
            continue
        tr = v[v <= v.quantile(0.95)].mean()
        out[r] = dict(n=len(v), med=v.median(), trim=tr, win=(v > 0).mean() * 100,
                      perday=tr / HOLD[r])
    return out


sec("① 규칙별 성적과 순위 — 구간마다 순위가 안정적인가 (순위가 흔들리면 우선순위는 못 배운다)")
ST = {lbl: rule_stats(a, b) for lbl, a, b in SEG}
P("  %-14s%6s" % ("규칙", "보유") + "".join("%26s" % lbl for lbl, _, _ in SEG))
P("  %-14s%6s" % ("", "") + "".join("%6s%7s%7s%6s" % ("n", "절삭", "일당", "승률") for _ in SEG))
for r in RIDS:
    row = "  %-14s%5d일" % (NM[r], HOLD[r])
    for lbl, _, _ in SEG:
        s = ST[lbl][r]
        row += ("%6d%+7.2f%+7.2f%5.0f%%" % (s["n"], s["trim"], s["perday"], s["win"])
                if s["trim"] == s["trim"] else "%6d%20s" % (s["n"], "—"))
    P(row)


def ranks(metric, seg):
    s = ST[seg]
    vals = {r: (s[r][metric] if s[r][metric] == s[r][metric] else -1e9) for r in RIDS}
    return vals


P()
P("  순위 상관(스피어만) — 학습 16~22 기준 순위가 다른 구간에서도 유지되나")
for metric, lab in (("trim", "절삭"), ("perday", "일당"), ("win", "승률")):
    base = pd.Series(ranks(metric, "학습 16~22")).rank()
    cells = []
    for lbl in ("홀드 05~15", "검증 23~26"):
        other = pd.Series(ranks(metric, lbl)).rank()
        cells.append("%s %+.2f" % (lbl, base.corr(other, method="spearman")))
    P("    %-6s %s" % (lab, " · ".join(cells)))

# 정책 = 규칙 → 우선 점수(클수록 먼저). 학습 16~22 로만 만든다.
TR = ST["학습 16~22"]
POL = {                            # 무작위를 맨 앞에 — 다른 정책이 짝비교할 기준이다
    "무작위": "random",
    "현행 (거래대금순)": None,
    "절삭순": {r: TR[r]["trim"] for r in RIDS},
    "일당순": {r: TR[r]["perday"] for r in RIDS},
    "승률순": {r: TR[r]["win"] for r in RIDS},
    "짧은보유순": {r: -HOLD[r] for r in RIDS},
    "역순 (점검)": {r: -TR[r]["trim"] for r in RIDS},
}
P()
P("  정책별 규칙 순서 (학습 16~22 로 정함):")
for k, v in POL.items():
    if isinstance(v, dict):
        order = sorted(RIDS, key=lambda r: -(v[r] if v[r] == v[r] else -1e9))
        P("    %-14s %s" % (k, " > ".join(NM[r] for r in order)))

# ── 슬롯 계좌 ─────────────────────────────────────────────────────────
DI_OF = {d: i for i, d in enumerate(DATES)}


def seg_idx(a, b):
    ii = [i for i, d in enumerate(DATES) if a <= d <= b]
    return ii[0], ii[-1]


def sim_slots(N, pol, seed, lo, hi):
    z = S[(S.di >= lo) & (S.di <= hi)]
    rng = np.random.default_rng(seed)
    tb = rng.random(len(z))
    if pol is None:
        key1 = np.zeros(len(z)); key2 = -z.amt20.fillna(0).values
    elif pol == "random":
        key1 = np.zeros(len(z)); key2 = tb
    else:
        key1 = -z.rid.map(pol).fillna(-1e9).values; key2 = tb
    order = np.lexsort((key2, key1, z.di.values))
    di = z.di.values[order]; ret = z.ret.values[order]; hold = z.hold.values[order].astype(int)
    tk = z.ticker.values[order]; rid = z.rid.values[order]
    eq = 1.0; pos = []              # (exit_di, amt, ret, ticker, rid)
    j, n = 0, len(di)
    peak, mdd = 1.0, 0.0
    taken = {r: 0 for r in RIDS}
    for i in range(lo, hi + 1):
        if pos:
            keep = []
            for p in pos:
                if p[0] <= i:
                    eq += p[1] * p[2] / 100
                else:
                    keep.append(p)
            pos = keep
        peak = max(peak, eq); mdd = min(mdd, eq / peak - 1)
        held = {p[3] for p in pos}
        while j < n and di[j] < i:
            j += 1
        while j < n and di[j] == i:
            if len(pos) < N and tk[j] not in held:
                pos.append((i + hold[j], eq / N, ret[j], tk[j], rid[j]))
                held.add(tk[j]); taken[rid[j]] += 1
            j += 1
    for p in pos:
        eq += p[1] * p[2] / 100
    return eq, mdd * 100, taken


sec("② 동시 보유 N종목 · 균등 — 정책별 계좌 (시드 %d · 같은 규칙 안 순서만 무작위)" % NS)
P("  숫자 = 그 구간을 1 로 시작해 끝난 자산(배) · 시드 중앙값\n")
RES = {}
for N in (5, 10, 20):
    P("  [동시 보유 %d종목]" % N)
    P("  %-16s" % "정책" + "".join("%14s" % s[0] for s in SEG) + "%16s" % "무작위 대비 이김")
    for pname, pol in POL.items():
        cells, wins = "", []
        for lbl, a, b in SEG:
            lo, hi = seg_idx(a, b)
            navs = np.array([sim_slots(N, pol, s, lo, hi)[0] for s in range(NS)])
            RES[(N, pname, lbl)] = navs
            cells += "%13.2f배" % np.median(navs)
        # 무작위와 같은 시드끼리 짝비교 — 세 구간 합산
        if pname != "무작위":
            w = sum(int((RES[(N, pname, lbl)] > RES[(N, "무작위", lbl)]).sum()) for lbl, _, _ in SEG
                    if (N, "무작위", lbl) in RES)
            wtxt = "%d/%d" % (w, NS * 3) if (N, "무작위", SEG[0][0]) in RES else "—"
        else:
            wtxt = "—"
        P("  %-16s%s%16s" % (pname, cells, wtxt))
        log("  N=%d %s" % (N, pname))
    P()
P("  ※ '무작위 대비 이김' 은 세 구간 × %d시드 = %d번 중 무작위보다 자산이 큰 횟수다. 절반이 동전이다." % (NS, NS * 3))
P("  ※ 순위는 **학습 16~22 로만** 정했다. 홀드아웃·검증 칸이 진짜 시험이다.")

sec("③ 정책별로 실제 무엇을 샀나 — 동시 보유 10종목 · 검증 23~26 · 시드 0")
lo, hi = seg_idx("20230101", "20301231")
P("  %-16s" % "정책" + "".join("%9s" % NM[r][:4] for r in RIDS))
for pname, pol in POL.items():
    _, _, tk = sim_slots(10, pol, 0, lo, hi)
    P("  %-16s" % pname + "".join("%9d" % tk[r] for r in RIDS))

sec("④ 낙폭 — 우선순위가 위험을 키우나 (동시 보유 10종목 · 시드 중앙 · 전 구간)")
lo, hi = 0, len(DATES) - 1
P("  %-16s%12s%12s%14s" % ("정책", "자산", "최대낙폭", "시드 최악 자산"))
for pname, pol in POL.items():
    rr = [sim_slots(10, pol, s, lo, hi) for s in range(NS)]
    navs = np.array([x[0] for x in rr]); mdds = np.array([x[1] for x in rr])
    P("  %-16s%11.2f배%11.1f%%%13.2f배" % (pname, np.median(navs), np.median(mdds), navs.min()))

P("\n총 %.0f초" % (time.time() - t0))
io.open(BASE / "_priority_out.txt", "w", encoding="utf-8").write("\n".join(OUT))
log("결과를 _priority_out.txt 에 썼다")
