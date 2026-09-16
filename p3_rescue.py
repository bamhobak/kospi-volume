# -*- coding: utf-8 -*-
"""**[폭락반등] 구조하기 — 손절·트레일·국면 조건** (2026-09-16 요청).

물음: "2008·2011 같은 시장에서만 불리한 규칙은, 잘 안 걸리게 하거나 손절·트레일로 막을 수 있어?"

해부에서 나온 것:
  2008 중앙 **-8.56**(40%·60건) · 2011 **-4.00**(29%·7건)  ← 계단식으로 내려가는 위기에서 실패
  2018 +13.40(87%) · 2020 **+35.35(98%·308건)** · 2022 +9.50 · 2023~26 +18.92
  전체 509건 중 308건(60%)이 2020년.

두 갈래로 막아 본다.
  **A. 손절·트레일** — 거래별로 걸리니 사건 수에 안 기댄다. 과적합 위험이 적다.
  **B. 국면 조건** — 2008·2011 을 피하는 축을 찾는다.
     ⚠ 사건이 **둘뿐**이라 "그 둘을 빼는 조건" 은 과적합이다. 그래서 문턱을 여러 칸으로
        훑어 **단조성**을 보고, 설명이 되는 축만 남긴다.

⚠ 트레일 체결 가정: portfolio.py 는 발동 당일 `고점*(1-t)` 에 팔린다고 본다. 이건 **낙관**이다
   ([[us-trail-fill-artifact]] — 미장에서 보수판으로 바꾸니 낙폭 규칙이 망가졌다).
   여기서는 **낙관판과 보수판(다음날 시가 매도)을 나란히** 낸다.

판정은 새 기준 — 무제한 자금 · 전 신호 동일금액 · 유니버스 초과는 안 본다.

    python p3_rescue.py
"""
import os, sys, time, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from pathlib import Path

BASE = Path(__file__).parent
W = 128
HOLD = 20
OUT = []
t0 = time.time()


def P(x=""):
    OUT.append(x)


def log(m):
    print("%s %s" % (time.strftime("%H:%M:%S"), m), file=sys.stderr, flush=True)


def sec(t):
    P("\n" + "=" * W + "\n" + t + "\n" + "=" * W)


log("portfolio.py 에서 P3 조건 가져오는 중")
SRC = (BASE / "portfolio.py").read_text(encoding="utf-8")
HEAD = SRC.split("# 신호를 한 표로 모은다", 1)[0]
ns = {"__file__": str(BASE / "portfolio.py")}
exec(compile(HEAD, "portfolio.py", "exec"), ns)
KP, RULES, IX = ns["KP"], ns["RULES"], ns["IX"]
_, hold, stop0, pct, mx, cond = RULES["P3"]
assert hold == HOLD and stop0 is None

K = KP.sort_values(["ticker", "date"]).reset_index(drop=True)
g = K.groupby("ticker", sort=False)
# 보유 20일 동안의 종가·저가·시가 경로
CL = np.column_stack([g.close.shift(-i).values for i in range(1, HOLD + 1)])
LO = np.column_stack([g.low.shift(-i).values for i in range(1, HOLD + 1)])
OP = np.column_stack([g.open.shift(-i).values for i in range(1, HOLD + 1)])
m = cond.fillna(False).values & K.buy.notna().values & (K.buy.values > 0)
SIG = K[m].copy()
BUY = SIG.buy.values.astype(float)
COST = SIG.cost.values.astype(float)
cl, lo, op = CL[m], LO[m], OP[m]
log("  P3 신호 %s건" % f"{len(SIG):,}")


def path_ret(mode, val):
    """mode: 'base' | 'stop_opt' | 'stop_con' | 'trail_opt' | 'trail_con'"""
    n = len(BUY)
    last = cl[:, -1]
    if mode == "base":
        px = last.copy(); ok = np.zeros(n, bool)
    elif mode == "stop_opt":
        # 저가가 문턱에 닿으면 **그 가격에** 팔린다고 본다(낙관 — 갭하락이면 못 판다)
        thr = BUY * (1 - val)
        hit = lo <= thr[:, None]
        ok = hit.any(axis=1)
        px = np.where(ok, thr, last)
    elif mode == "stop_con":
        # 종가가 문턱 아래면 **다음날 시가**에 판다(보수 — 실제로 낼 수 있는 주문)
        thr = BUY * (1 - val)
        hit = cl <= thr[:, None]
        ok = hit.any(axis=1)
        i = np.where(ok, hit.argmax(axis=1), HOLD - 1)
        nxt = np.where(i + 1 < HOLD, op[np.arange(n), np.minimum(i + 1, HOLD - 1)], last)
        px = np.where(ok, np.where(np.isnan(nxt), cl[np.arange(n), i], nxt), last)
    elif mode in ("trail_opt", "trail_con"):
        run = np.maximum.accumulate(np.column_stack([BUY, cl]), axis=1)[:, 1:]
        hit = cl <= run * (1 - val)
        ok = hit.any(axis=1)
        i = np.where(ok, hit.argmax(axis=1), HOLD - 1)
        if mode == "trail_opt":
            px = np.where(ok, run[np.arange(n), i] * (1 - val), last)
        else:
            nxt = np.where(i + 1 < HOLD, op[np.arange(n), np.minimum(i + 1, HOLD - 1)], last)
            px = np.where(ok, np.where(np.isnan(nxt), cl[np.arange(n), i], nxt), last)
    r = (px / BUY - 1) * 100 - COST
    return pd.Series(r, index=SIG.index), ok


def st(v):
    v = v.dropna()
    if len(v) < 5:
        return None
    tr = v[v <= v.quantile(0.95)].mean()
    return dict(n=len(v), mean=v.mean(), med=v.median(), trim=tr,
                win=(v > 0).mean() * 100, worst=v.min())


SEG = [("전체", "20050101", "20301231"), ("홀드 05~15", "20050101", "20151231"),
       ("2008", "20080101", "20081231"), ("2011", "20110101", "20111231"),
       ("2020", "20200101", "20201231"), ("16~26", "20160101", "20301231")]
D = SIG.date.values


def line(lbl, r, extra=""):
    cells = ""
    for _, a, b in SEG:
        s = st(r[(D >= a) & (D <= b)])
        cells += ("%9.2f" % s["med"]) if s else "%9s" % "—"
    return "  %-22s%s%s" % (lbl, cells, extra)


sec("① 손절·트레일 — 구간별 **중앙값** (보유 20일)")
P("  %-22s" % "구성" + "".join("%9s" % s[0] for s in SEG))
base, _ = path_ret("base", 0)
P(line("기준 (없음)", base))
P()
for v in (0.10, 0.15, 0.20, 0.25):
    r, ok = path_ret("stop_opt", v)
    P(line("손절 -%d%% (낙관)" % (v * 100), r, "   발동 %.0f%%" % (ok.mean() * 100)))
P()
for v in (0.10, 0.15, 0.20, 0.25):
    r, ok = path_ret("stop_con", v)
    P(line("손절 -%d%% (보수)" % (v * 100), r, "   발동 %.0f%%" % (ok.mean() * 100)))
P()
for v in (0.08, 0.10, 0.12, 0.15):
    r, ok = path_ret("trail_opt", v)
    P(line("트레일 -%d%% (낙관)" % (v * 100), r, "   발동 %.0f%%" % (ok.mean() * 100)))
P()
for v in (0.08, 0.10, 0.12, 0.15):
    r, ok = path_ret("trail_con", v)
    P(line("트레일 -%d%% (보수)" % (v * 100), r, "   발동 %.0f%%" % (ok.mean() * 100)))
P("\n  ※ 낙관판은 발동 당일 그 가격에 팔린다고 본다 — 갭하락이면 실제로는 못 판다.")
P("    **보수판이 진짜 값**이다. 둘이 크게 갈리면 그 개선은 체결 가정이 만든 것이다.")

sec("② 손절·트레일 전체 성적 — 절삭평균까지")
P("  %-22s%8s%9s%9s%9s%8s%10s" % ("구성", "n", "평균", "중앙", "절삭", "승률", "최악"))
for lbl, mo, v in [("기준 (없음)", "base", 0),
                   ("손절 -15% (보수)", "stop_con", 0.15), ("손절 -20% (보수)", "stop_con", 0.20),
                   ("손절 -25% (보수)", "stop_con", 0.25),
                   ("트레일 -10% (보수)", "trail_con", 0.10), ("트레일 -15% (보수)", "trail_con", 0.15),
                   ("손절 -15% (낙관)", "stop_opt", 0.15), ("트레일 -10% (낙관)", "trail_opt", 0.10)]:
    r, _ = path_ret(mo, v)
    s = st(r)
    P("  %-22s%8s%+9.2f%+9.2f%+9.2f%7.0f%%%+10.1f"
      % (lbl, f"{s['n']:,}", s["mean"], s["med"], s["trim"], s["win"], s["worst"]))

# ── B. 국면 축 ────────────────────────────────────────────────────────
log("국면 재료 만드는 중")
IX = IX.sort_values("date").reset_index(drop=True)
IX["dd"] = (IX.Close / IX.Close.cummax() - 1) * 100          # 지수 고점 대비 낙폭
IX["r20"] = (IX.Close / IX.Close.shift(20) - 1) * 100
IX["r60"] = (IX.Close / IX.Close.shift(60) - 1) * 100
below = (IX.Close < IX.ma60).astype(int)
IX["belowN"] = below.groupby((below == 0).cumsum()).cumsum()  # 60일선 아래 **연속일수**
try:
    VK = pd.read_csv(BASE / "data/vkospi.csv", dtype={"date": str}, encoding="utf-8-sig")
    IX["vk"] = IX.date.map(dict(zip(VK.date, VK.close)))
except Exception as e:
    IX["vk"] = np.nan
    log("  vkospi 실패 %r" % (e,))
MAP = {c: dict(zip(IX.date, IX[c])) for c in ("dd", "r20", "r60", "belowN", "vk")}
for c in MAP:
    SIG[c] = SIG.date.map(MAP[c])

sec("③ 국면 축 — 2008·2011 을 가르는 것이 있나 (기준 · 손절 없음)")
P("  ⚠ 사건이 둘뿐이라 '그 둘을 빼는 조건' 은 과적합이다. **문턱을 훑어 단조인지**를 본다.\n")
AX = [("지수 60일선 아래 연속일수", "belowN", [(0, 20), (20, 40), (40, 60), (60, 100), (100, 1e9)]),
      ("지수 고점대비 낙폭", "dd", [(-1e9, -35), (-35, -25), (-25, -15), (-15, 0)]),
      ("지수 20일 수익률", "r20", [(-1e9, -15), (-15, -8), (-8, 0), (0, 1e9)]),
      ("지수 60일 수익률", "r60", [(-1e9, -25), (-25, -15), (-15, -5), (-5, 1e9)]),
      ("VKOSPI", "vk", [(0, 20), (20, 30), (30, 40), (40, 1e9)])]
for nm, col, bins in AX:
    P("  [%s]" % nm)
    P("    %-18s%8s%9s%9s%9s%8s%10s" % ("구간", "n", "평균", "중앙", "절삭", "승률", "2008비율"))
    for a, b in bins:
        sel = ((SIG[col] > a) & (SIG[col] <= b)).values
        s = st(base[sel])
        lab = ("%g~%g" % (a, b)).replace("-1e+09", "").replace("1e+09", "")
        if not s:
            P("    %-18s%8s  (부족)" % (lab, int(sel.sum()))); continue
        y08 = (SIG.date.values[sel] < "20120101").mean() * 100
        P("    %-18s%8s%+9.2f%+9.2f%+9.2f%7.0f%%%9.0f%%"
          % (lab, f"{s['n']:,}", s["mean"], s["med"], s["trim"], s["win"], y08))
    P()

P("\n총 %.0f초" % (time.time() - t0))
sys.stdout.reconfigure(encoding="utf-8")
print("\n".join(OUT))
