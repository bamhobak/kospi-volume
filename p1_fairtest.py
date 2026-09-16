# -*- coding: utf-8 -*-
"""**[조용한 신고가] 공정 재검정 — 절대 문턱 대신 백분위** (2026-09-16).

사용자 반론: "홀드아웃 시기랑 지금은 시장이 많이 바뀌지 않았나? 그 시기를 중요하게
             생각하면 안 되지 않아?"

타당하다. 그리고 **검증 가능한 반론**이라 재볼 수 있다. 결정적인 증거가 하나 나왔다.

  [조용한 신고가]는 **거래대금 200억** 이라는 **절대 금액** 문턱을 쓴다. 그 문턱이 뜻하는 바는
  해마다 다르다 — 코스피에서 200억을 넘는 종목이
      2005년 **35개(4.3%)** · 2008년 64개(7.4%) · 2016년 53개(6.1%) · 2026년 **148개(16.2%)**
  즉 홀드아웃 시절엔 지금보다 **4배 좁은 초대형주 집단**에서만 신호가 났다.

  우리는 이 교훈을 **미장에서 이미 배웠다**([[us-market-character-n1]]) — [상승장 신고가]는
  "절대 금액이 아니라 백분위(상위 40%)" 를 쓴다. 국내 [조용한 신고가]만 아직 절대값이다.

⚠ 재료 결측은 원인이 아니다 — 2006년부터 채움률이 거의 100% 다(2005년만 r16·ret250 결측).

그래서 **문턱을 백분위로 바꿔** 홀드아웃을 다시 잰다. 지금(2026) 200억이 상위 16% 이므로
같은 뜻이 되게 **상위 16%·10%·6%** 세 가지로 훑는다.

  ① 문턱을 백분위로 — 구간별 성적이 달라지나
  ② 문턱 없이(유동성 조건만 빼고) — 문턱 자체가 범인인가
  ③ 같은 백분위로 맞췄을 때 신호 수·성적을 구간별로
  ④ 다른 규칙도 절대 문턱을 쓰나 — 같은 병이 또 있는지 점검

    python p1_fairtest.py
"""
import io, sys, time, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from pathlib import Path

BASE = Path(__file__).parent
W = 124
OUT = []
t0 = time.time()


def P(x=""):
    OUT.append(x)


def log(m):
    print("%s %s" % (time.strftime("%H:%M:%S"), m), file=sys.stderr, flush=True)


def sec(t):
    P("\n" + "=" * W + "\n" + t + "\n" + "=" * W)


# ⚠ portfolio.py 는 `sys.stdout = io.TextIOWrapper(sys.stdout.buffer, ...)` 를 한다.
#   원래 stdout 을 붙들어 두지 않으면 정리되면서 밑의 버퍼가 닫혀 마지막 print 가 죽는다.
_REAL = sys.stdout

log("portfolio.py 재구성")
SRC = (BASE / "portfolio.py").read_text(encoding="utf-8")
HEAD = SRC.split("# 신호를 한 표로 모은다", 1)[0]
ns = {"__file__": str(BASE / "portfolio.py")}
exec(compile(HEAD, "portfolio.py", "exec"), ns)
KP, RULES = ns["KP"], ns["RULES"]
K, hold, stop0, pct0, mx0, cond0 = RULES["P1"]
assert hold == 40
K = KP
g = K.groupby("ticker", sort=False)
EX = g.close.shift(-hold)
AQ = K.groupby("date").amt20.rank(pct=True)          # 그날 코스피 안 거래대금 백분위
log("  P1 원본 조건 %s건" % f"{int(cond0.fillna(False).sum()):,}")

# 원본 조건에서 **거래대금 문턱만** 떼어낸다 — 나머지는 그대로 둔다.
# (portfolio.py 의 P1 조건식을 건드리지 않고, 200억 조건을 '항상 참' 으로 만든 판을 만든다)
NOAMT = cond0 & (K.amt20.fillna(0) >= 0)             # 원본 그대로(200억은 이미 안에 들어 있다)
# 200억 조건을 빼려면 조건식을 다시 짜야 한다 — base() 와 같은 재료로 직접 만든다.
base = ns["base"]
try:
    RAW = (base(K, 0) & (K.fromhi >= -10) & (K.r16 < 120) & (K.rw1 <= 120)
           & (K.fw5 >= 3) & (K.fw60 >= 1) & (K.vol20 <= 2) & (K.sr20 <= 0.5)
           & (K.ret20 <= 5)
           & ~((K.above20 > 70) & (K.ret250 > 120)))
except Exception as e:
    log("  RAW 조립 실패 %r — base 시그니처 확인 필요" % (e,))
    RAW = None


def evalcond(c, lab):
    """중복 제거 후 구간별 성적."""
    X = K[c.fillna(False)].copy()
    X["exit"] = EX.reindex(X.index)
    X = X.dropna(subset=["exit", "buy", "cost"])
    X = X[X.buy > 0].sort_values("date")
    keep, last = [], {}
    di = dict(zip(sorted(K.date.unique()), range(K.date.nunique())))
    for t, d_, ix in zip(X.ticker.values, X.date.values, X.index):
        i = di[d_]
        if last.get(t, -10 ** 9) >= i:
            continue
        last[t] = i + hold
        keep.append(ix)
    X = X.loc[keep]
    X["ret"] = (X.exit / X.buy - 1) * 100 - X.cost
    return X


def row(lab, X):
    cells = ""
    for _, a, b in SEG:
        v = X[(X.date >= a) & (X.date <= b)].ret
        if len(v) < 10:
            cells += "%22s" % ("n=%d" % len(v)); continue
        tr = v[v <= v.quantile(0.95)].mean()
        cells += "%6d%+8.2f%+8.2f" % (len(v), v.median(), tr)
    return "  %-22s%s" % (lab, cells)


SEG = [("홀드 05~15", "20050101", "20151231"), ("16~26", "20160101", "20301231")]
sec("① 거래대금 문턱을 백분위로 — 홀드아웃 성적이 달라지나")
P("  %-22s%s" % ("구성", "".join("%22s" % s[0] for s in SEG)))
P("  %-22s%s" % ("", "".join("%6s%8s%8s" % ("n", "중앙", "절삭") for _ in SEG)))
P(row("원본 (절대 200억)", evalcond(cond0, "orig")))
if RAW is not None:
    for q, lab in [(0.84, "상위 16% (지금과 같은 뜻)"), (0.90, "상위 10%"),
                   (0.94, "상위 6% (옛날과 같은 뜻)"), (0.0, "문턱 없음")]:
        P(row(lab, evalcond(RAW & (AQ >= q), lab)))

sec("② 신호 수가 구간별로 어떻게 달라지나")
P("  %-22s%12s%12s%10s" % ("구성", "홀드 05~15", "16~26", "비율"))
for lab, c in ([("원본 (절대 200억)", cond0)] +
               ([("상위 16%", RAW & (AQ >= 0.84)), ("상위 10%", RAW & (AQ >= 0.90)),
                 ("상위 6%", RAW & (AQ >= 0.94)), ("문턱 없음", RAW)] if RAW is not None else [])):
    X = evalcond(c, lab)
    a = int((X.date <= "20151231").sum()); b = int((X.date >= "20160101").sum())
    P("  %-22s%12s%12s%9.2f" % (lab, f"{a:,}", f"{b:,}", (a / b) if b else float("nan")))

sec("③ 다른 규칙의 절대 문턱 — 같은 병이 또 있나")
P("  규칙이 쓰는 절대 금액·절대 가격 문턱과, 그게 해마다 몇 %를 거르는지\n")
P("  %-24s%10s" % ("문턱", "설명"))
P("  %-24s%s" % ("[조용한 신고가] 200억", "2005 상위 4.3% → 2026 상위 16.2% — **4배 차이**"))
P("  %-24s%s" % ("[외인 매집] 시총 1천억~1조", "절대값 — 물가·지수 상승으로 뜻이 달라진다"))
P("  %-24s%s" % ("[깊은 이격] 10억", "낮은 문턱이라 거의 전 종목 통과 — 영향 작다"))
P("  %-24s%s" % ("[업종붕괴 이탈] 5억·1000원", "낮은 문턱 — 영향 작다"))
P("  %-24s%s" % ("[폭락반등]·[낙폭과대] 2~3억", "낮은 문턱 — 영향 작다"))
P()
for lab, col, thr in [("코스피 시총 1천억 이상", "cap조", 0.1), ("코스피 시총 1조 미만", "cap조", 1.0)]:
    if "cap조" not in K.columns:
        continue
    P("  [%s] 연도별 해당 종목 수" % lab)
    yy = K.assign(y=K.date.str[:4])
    out = []
    for y in ["2005", "2010", "2015", "2020", "2026"]:
        z = yy[(yy.y == y) & yy["cap조"].notna()]
        if not len(z):
            continue
        d = z.groupby("date").apply(lambda gg: ((gg["cap조"] >= thr).mean() * 100) if lab.endswith("이상")
                                    else ((gg["cap조"] < thr).mean() * 100))
        out.append("%s %.0f%%" % (y, np.mean(d)))
    P("    " + " · ".join(out))

P("\n총 %.0f초" % (time.time() - t0))
# ⚠ portfolio.py 가 sys.stdout 을 갈아 치우는 통에 마지막 print 가 닫힌 버퍼를 만난다.
#   stdout 에 기대지 말고 **파일로 직접 쓴다** — 무엇이 stdout 을 건드리든 안전하다.
_out = BASE / "_p1fair_out.txt"
io.open(_out, "w", encoding="utf-8").write("\n".join(OUT))
log("결과를 %s 에 썼다" % _out.name)
