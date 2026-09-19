# -*- coding: utf-8 -*-
"""**H0081 공매도 거래 비중 바닥 회피 — 기존 국내 9규칙에 얹기** (2026-09-19).

축 스캔에서 유일하게 통제를 견딘 축: 공매도 거래 비중(5일 평균)이 **낮을수록** 이후 수익이 나쁘다
(공매도 가능 종목끼리 ρ 학습·검증 1.00, 변동성×규모 9칸 중 8칸 유지). 좋은 쪽도 절대 수익이 음수라
단독 매수 규칙은 못 되고, **기존 규칙이 사는 종목에서 바닥을 빼면 나아지나**가 물음이다.

  ① 거래 단위 — 9규칙 신호 중 바닥 30% 가 실제로 더 나빴나. **같은 달 안 짝비교**([[p4-credit-adopted]])
     로 폭락장 쏠림을 뺀다.
  ② 계좌 — 바닥 20·30·40% 빼기(이웃 칸) · 공매도 불가(0) 종목까지 빼기. 300시드 짝비교 ·
     구간 3분할(홀드아웃 05~15 · 학습 16~22 · 검증 23~26) · 다중검정.

재료: krx short_volume vol_rto(당일 장 마감 뒤 공시 → 시차 0), 5일 평균. 날짜별로 **공매도가 된 종목
(>0) 안에서** 백분위. 그날 0 인 종목이 80%↑ 이면 **금지일** — 조건을 끈다(원래대로 산다).
0 인 종목(공매도 대상 아님)은 기본으로 그대로 사고, 빼는 건 별도 변형으로만 본다.

    python research/sv_overlay.py        → research/reports/H0081_overlay.md
"""
import io, os, sqlite3, sys, time, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(BASE))
from verdict import deflated_sharpe, log_trials

NS = 300
OUT = []; t0 = time.time()
NM = {"P1": "조용한 신고가", "P2": "조정매집", "P3": "폭락반등", "P4": "업종붕괴 이탈", "P5": "자사주 낙폭",
      "P6": "깊은 이격", "P7": "외인 매집", "D1": "낙폭과대", "D2": "저PBR 낙폭"}


def P(x=""):
    OUT.append(x)


def log(m):
    print("%s %s" % (time.strftime("%H:%M:%S"), m), file=sys.stderr, flush=True)


# ── 기존 규칙 신호 ────────────────────────────────────────────────────
log("portfolio.py 재구성")
SRC = (BASE / "portfolio.py").read_text(encoding="utf-8")
HEAD, REST = SRC.split("# 신호를 한 표로 모은다", 1)
MID = "# 신호를 한 표로 모은다" + REST.split("# @@ANALYSIS", 1)[0]
os.environ["SKIP"] = ""
_real = sys.stdout
ns = {"__file__": str(BASE / "portfolio.py")}
exec(compile(HEAD, "portfolio.py", "exec"), ns)
exec(compile(MID, "portfolio.py", "exec"), ns)
_keep = sys.stdout; sys.stdout = _real
S0 = ns["S"].copy(); sim = ns["simulate"]
log("  신호 %s건" % f"{len(S0):,}")

# ── 공매도 거래 비중 ──────────────────────────────────────────────────
log("공매도 거래 비중")
c = sqlite3.connect("file:%s?mode=ro" % (BASE / "data/krx_daily.db"), uri=True)
V = pd.read_sql("SELECT ticker, date, vol_rto FROM short_volume", c); c.close()
V = V.sort_values(["ticker", "date"]).reset_index(drop=True)
V["sv5"] = V.groupby("ticker", sort=False).vol_rto.rolling(5, min_periods=5).mean().reset_index(level=0, drop=True)
V = V.dropna(subset=["sv5"])
zero_share = V.groupby("date").sv5.apply(lambda s: (s <= 0).mean())
BAN = set(zero_share[zero_share >= 0.80].index)
pos = V.sv5 > 0
V["svp"] = np.nan
V.loc[pos, "svp"] = V[pos].groupby("date").sv5.rank(pct=True)
S0 = S0.merge(V[["ticker", "date", "sv5", "svp"]], on=["ticker", "date"], how="left")
S0["ban"] = S0.date.isin(BAN)
S0["r"] = (S0.exit / S0.buy - 1) * 100 - S0.cost
S0["ym"] = S0.date.str[:6]
ban_years = sorted({d[:4] for d in BAN})
log("  금지일 %d일 (%s)" % (len(BAN), ", ".join(ban_years)))

# ── ① 거래 단위 ──────────────────────────────────────────────────────
P("# H0081 공매도 거래 비중 바닥 회피 — 기존 국내 9규칙에 얹기")
P("")
P("- 금지일(그날 공매도 0 종목 80%%↑) %d일 · 해당 연도 %s — 이날은 조건을 끈다" % (len(BAN), ", ".join(ban_years)))
act = S0[~S0.ban]
P("- 신호 %s건 중 금지일 아님 %s건 · 그중 공매도 된 종목(>0) %s건 · 0(대상 아님) %s건"
  % (f"{len(S0):,}", f"{len(act):,}", f"{int(act.svp.notna().sum()):,}", f"{int((act.sv5 <= 0).sum()):,}"))
P("")
P("## ① 거래 단위 — 규칙이 산 종목 중 바닥 30%가 더 나빴나 (보유기간 끝 종가 청산·비용 차감)")
P("")
P("| 규칙 | 바닥30% n | 바닥30% 중앙 | 나머지 n | 나머지 중앙 | 같은 달 짝비교(바닥−나머지) | 짝 달 수 | 0종목 n / 중앙 |")
P("|---|---|---|---|---|---|---|---|")


def pair_month(X, flag):
    d = []
    for ym, g in X.groupby("ym"):
        a = g[flag]; b = g[~flag]
        if len(a) and len(b):
            d.append(a.r.mean() - b.r.mean())
    return (np.mean(d) if d else np.nan), len(d)


for rid in list(NM) + ["전체"]:
    X = act if rid == "전체" else act[act.rid == rid]
    X = X[X.svp.notna()]
    lo = X.svp <= 0.30
    pm, nm = pair_month(X, lo)
    Z = act if rid == "전체" else act[act.rid == rid]
    z0 = Z[Z.sv5 <= 0]
    P("| %s | %d | %+.2f | %d | %+.2f | %+.2f | %d | %d / %s |" % (
        rid if rid == "전체" else "%s [%s]" % (rid, NM[rid]), lo.sum(), X[lo].r.median() if lo.sum() else np.nan,
        (~lo).sum(), X[~lo].r.median() if (~lo).sum() else np.nan, pm, nm, len(z0),
        ("%+.2f" % z0.r.median()) if len(z0) else "-"))

# ── ② 계좌 ───────────────────────────────────────────────────────────
def variant(cut=None, drop_zero=False):
    keep = pd.Series(True, index=S0.index)
    if cut is not None:
        keep &= ~((~S0.ban) & (S0.svp <= cut))
    if drop_zero:
        keep &= ~((~S0.ban) & (S0.sv5 <= 0))
    return S0[keep].drop(columns=["sv5", "svp", "ban", "r", "ym"]).reset_index(drop=True)


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
    mo = C.assign(ym=C.date.str[:6]).groupby("ym").nav.last().pct_change().dropna() * 100
    return dict(nav=nav, mdd=mdd, expo=C.expo.mean() * 100, navs=np.array(navs), mo=mo,
                hold=c15, mid=c22 / c15, late=nav / c22, n=len(Z))


CFG = [("지금 (그대로)", dict()), ("바닥 20% 빼기", dict(cut=0.20)), ("바닥 30% 빼기 (원안)", dict(cut=0.30)),
       ("바닥 40% 빼기", dict(cut=0.40)), ("바닥 30% + 0종목 빼기", dict(cut=0.30, drop_zero=True))]
R = {}
for lbl, kw in CFG:
    log(lbl)
    R[lbl] = run(variant(**kw))
    log("  %.2f배" % R[lbl]["nav"])
B = R[CFG[0][0]]
P("")
P("## ② 계좌 — %d시드 짝비교 (지금 대비 이긴 시드 수)" % NS)
P("")
P("| 구성 | 신호 | 노출 | 자산 | 낙폭 | 시드 중앙 | 시드 최악 | 자산 이긴 시드 |")
P("|---|---|---|---|---|---|---|---|")
for lbl, _ in CFG:
    r = R[lbl]
    w = "—" if r is B else "%d/%d" % (int((r["navs"] > B["navs"]).sum()), NS)
    P("| %s | %s | %.0f%% | %.2f배 | %.1f%% | %.2f배 | %.2f배 | %s |" % (
        lbl, f"{r['n']:,}", r["expo"], r["nav"], r["mdd"], np.median(r["navs"]), r["navs"].min(), w))
P("")
P("## 구간 3분할")
P("")
P("| 구성 | 홀드아웃 05~15 | 학습 16~22 | 검증 23~26 | 전체 |")
P("|---|---|---|---|---|")
for lbl, _ in CFG:
    r = R[lbl]
    P("| %s | %.2f배 | %.2f배 | %.2f배 | %.2f배 |" % (lbl, r["hold"], r["mid"], r["late"], r["nav"]))
NT = len(CFG) - 1
P("")
P("## 다중검정 (월수익 · 돌린 구성 %d개 · 진짜일 확률 0.90↑ 통과)" % NT)
P("")
P("| 구성 | 샤프 | 문턱 | 진짜일 확률 |")
P("|---|---|---|---|")
for lbl, _ in CFG:
    d = deflated_sharpe(R[lbl]["mo"], NT)
    if d:
        P("| %s | %.3f | %.3f | %.1f%% |" % (lbl, d["sr"], d["sr0"], d["dsr"] * 100))
P("")
P("총 %.0f초" % (time.time() - t0))
log_trials("H0081_overlay", len(CFG) * 10 + (len(NM) + 1))
rp = ROOT / "reports" / "H0081_overlay.md"
rp.write_text("\n".join(OUT) + "\n", encoding="utf-8")
print("\n".join(OUT))
