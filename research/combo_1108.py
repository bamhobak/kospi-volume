# -*- coding: utf-8 -*-
"""② 약한 규칙 비중 조정 + ③ 놀고 있는 돈 자리(저변동 순위 포트) — 국장 계좌 (2026-11-08 사용자 "3번이랑 2번 해보고").

계좌 = portfolio.py 규칙 정의·비중·자리·우선순위(거래대금 큰 순) 그대로. 단 여기선 **매일 종가로 평가**(낙폭을 청산 때만 재면 작다).
② 규칙별 비중 배율 W[rid] (0 = 빼기) — dsr_live_1108 에서 약했던 [조용한 신고가](P1)·[저PBR 낙폭](D2)·[조정매집](P2).
③ 규칙에 안 들어간 돈(현금)의 frac 만큼을 '자리'에 넣는다:
   cash0 = 그냥 현금(이자 0, portfolio.py 와 같음) · cash25 = 연 2.5% 이자(CMA) · kospi = 코스피 지수 · lowvol = 저변동 30종목 · lowvol_big = 시총 상위 300 안 저변동 30
   저변동 30 = 매달 마지막 거래일 종가에, 거래대금 상위 50%·주가 1,000원↑·보통주·1년 기록 있는 종목 중 250일 일간등락 표준편차가 가장 작은 30종목을
   똑같이 나눠 산다(그날 종가 매수) → 다음 달 말까지. 교체 비용 = 바뀐 비율 × 0.23%. 자리에 넣고 뺄 때마다 움직인 금액 × 0.115%.
    python research/combo_1108.py      → research/reports/combo_1108.md
"""
import io, os, sys, time, math, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd

BASE = Path(__file__).resolve().parent.parent
os.chdir(BASE); sys.path.insert(0, str(BASE))
t0 = time.time()
src = (BASE / "portfolio.py").read_text(encoding="utf-8").split("# @@ANALYSIS")[0]
ns = {"__file__": str(BASE / "portfolio.py"), "__name__": "x"}
_real = sys.stdout
sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
exec(compile(src, "portfolio.py", "exec"), ns)
sys.stdout = _real; sys.stdout.reconfigure(encoding="utf-8")
S, dates, KP, KQ, IX = ns["S"], ns["dates"], ns["KP"], ns["KQ"], ns["IX"]
ND = len(dates); DI = {d: i for i, d in enumerate(dates)}
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))
print("재료 %.1f분 · 신호 %d" % ((time.time() - t0) / 60, len(S)), flush=True)

# ── 종가 행렬(매일 평가용) ──
KB = pd.concat([KP[["ticker", "date", "close", "amt20", "cap조", "pref"]], KQ[["ticker", "date", "close", "amt20", "cap조", "pref"]]], ignore_index=True)
KB = KB.drop_duplicates(["ticker", "date"]).sort_values(["ticker", "date"]).reset_index(drop=True)
TK = np.array(sorted(KB.ticker.unique())); TI = {t: i for i, t in enumerate(TK)}
di_ = KB.date.map(DI).values; ti_ = KB.ticker.map(TI).values
okm = ~pd.isna(di_)
CL = np.full((ND, len(TK)), np.nan, np.float32)
CL[di_[okm].astype(int), ti_[okm]] = KB.close.values[okm]
CLf = pd.DataFrame(CL).ffill().values                       # 거래정지·폐지 뒤는 마지막 종가
print("종가 행렬 %s %.1f분" % (CL.shape, (time.time() - t0) / 60), flush=True)

# ── 자리(sleeve) 하루 수익 ──
R = np.zeros((ND, len(TK)), np.float32)
R[1:] = CL[1:] / CLf[:-1] - 1
R = np.where(np.isfinite(R), R, 0)
LIM = np.where(np.array(dates) < "20150615", 0.155, 0.305)[:, None]   # 가격제한폭 넘는 하루 등락 = 분할·무상·이음새 가짜 → 0
R = np.where(np.abs(R) > LIM, 0, R).astype(np.float32)
VOL = pd.DataFrame(np.where(np.isfinite(CL), R, np.nan)).rolling(250, min_periods=200).std().values
AMT = np.full((ND, len(TK)), np.nan, np.float32); AMT[di_[okm].astype(int), ti_[okm]] = KB.amt20.values[okm]
CAP = np.full((ND, len(TK)), np.nan, np.float32); CAP[di_[okm].astype(int), ti_[okm]] = KB["cap조"].values[okm]
PREF = np.zeros(len(TK), bool)
for t, p in KB.groupby("ticker").pref.first().items(): PREF[TI[t]] = bool(p)
ym = np.array([d[:6] for d in dates]); mend = np.r_[ym[1:] != ym[:-1], True]


def sleeve(big=False, n=30):
    r = np.zeros(ND); w = None; hold = np.zeros(len(TK), bool)
    for i in range(ND):
        if w is not None: r[i] = float(R[i][hold].mean())
        if mend[i] and i > 260:
            a = AMT[i]; ok = np.isfinite(CL[i]) & np.isfinite(VOL[i]) & (CL[i] >= 1000) & ~PREF & np.isfinite(a)
            ok &= a >= np.nanpercentile(a[ok], 50)
            if big:
                c = np.where(ok & np.isfinite(CAP[i]), CAP[i], -1); ok &= c >= np.sort(c)[-300]
            idx = np.where(ok)[0]
            pick = idx[np.argsort(VOL[i][idx])[:n]]
            new = np.zeros(len(TK), bool); new[pick] = True
            turn = 1.0 if w is None else 1 - (new & hold).sum() / n
            r[i] -= turn * 0.0023
            hold = new; w = True
    return r


ix = IX.set_index("date").Close.reindex(dates).ffill()
SL = {"cash0": np.zeros(ND), "cash25": np.full(ND, 1.025 ** (1 / 252) - 1),
      "kospi": ix.pct_change().fillna(0).values,
      "lowvol": sleeve(False), "lowvol_big": sleeve(True)}
print("자리 수익 %.1f분" % ((time.time() - t0) / 60), flush=True)

# ── 계좌 ──
S = S.copy(); S["ti"] = S.ticker.map(TI)
TOD = {i: g for i, g in S.groupby("di")}


def sim(W=None, sl="cash0", frac=1.0):
    """W: {rid: 배율}. 반환 매일 평가 nav·노출."""
    W = W or {}
    eq = 1.0; V = 0.0; pos = []; nav = np.zeros(ND); expo = np.zeros(ND); sr = SL[sl]; mv = 0.0
    for i in range(ND):
        g = sr[i] * V; V += g; eq += g                       # 자리 굴림
        still = []
        for p in pos:
            if p["x"] <= i: eq += p["amt"] * ((p["exit"] / p["buy"] - 1) * 100 - p["cost"]) / 100
            else: still.append(p)
        pos = still
        T = TOD.get(i)
        if T is not None:
            inv = sum(p["amt"] for p in pos)
            for t in T.itertuples():
                m = W.get(t.rid, 1.0)
                if m <= 0: continue
                w = eq * t.pct / 100 * m
                if sum(1 for p in pos if p["rid"] == t.rid) >= t.mx or inv + w > eq or any(p["tk"] == t.ticker for p in pos): continue
                pos.append(dict(rid=t.rid, tk=t.ticker, ti=t.ti, buy=t.buy, exit=t.exit, cost=t.cost, amt=w, x=i + t.hold, d0=i))
                inv += w
        inv = sum(p["amt"] for p in pos)
        tgt = frac * max(eq - inv, 0) if sl != "cash0" else 0.0
        if sl not in ("cash0", "cash25"):
            c = abs(tgt - V) * 0.00115; eq -= c; mv += abs(tgt - V)
        V = tgt
        un = 0.0
        for p in pos:
            if i > p["d0"]:
                c = CLf[i, p["ti"]]
                if c == c: un += p["amt"] * (c / p["buy"] - 1)
        nav[i] = eq + un; expo[i] = inv / eq if eq > 0 else 0
    return nav, expo


PER = (("05~15", "20050101", "20151231"), ("16~22", "20160101", "20221231"), ("23~", "20230101", "20991231"), ("전체 05~", "20050101", "20991231"))
DA = np.array(dates)


def segs(nav):
    out = []
    for nm, a, b in PER:
        m = (DA >= a) & (DA <= b); x = nav[m]
        if len(x) < 50: out.append(None); continue
        x = x / x[0]; yrs = len(x) / 252
        cg = x[-1] ** (1 / yrs) - 1; dd = (x / np.maximum.accumulate(x) - 1).min()
        r = np.diff(np.log(x)); sh = r.mean() / r.std() * math.sqrt(252) if r.std() > 0 else 0
        out.append((cg * 100, dd * 100, sh))
    return out


def row(lab, nav, expo=None):
    s = segs(nav)
    cells = " | ".join("" if z is None else "%+.1f%% / %.1f%% / %.2f" % z for z in s)
    P("| %s | %s | %s |" % (lab, cells, "" if expo is None else "%.0f%%" % (expo[DA >= "20050101"].mean() * 100)))


HD = "| 판 | 2005~15 연·낙폭·샤프 | 2016~22 | 2023~ | 전체 2005~ | 규칙 노출 |"
P("# 약한 규칙 비중 조정 · 놀고 있는 돈 자리 — 국장 계좌 · %s" % time.strftime("%Y-%m-%d")); P("")
P("- portfolio.py 규칙·비중·자리·거래대금 큰 순 그대로, **매일 종가 평가**(낙폭이 청산 기준보다 깊게 나온다) · 칸 = 연 수익 / 최대낙폭 / 샤프"); P("")
P("## ② 약한 규칙 비중 (0배 = 빼기)"); P(""); P(HD); P("|---|---|---|---|---|---|")
GRID = [("기준(지금)", {}),
        ("[조용한 신고가] 0", {"P1": 0}), ("[조용한 신고가] 0.5", {"P1": 0.5}),
        ("[저PBR 낙폭] 0", {"D2": 0}), ("[저PBR 낙폭] 0.5", {"D2": 0.5}),
        ("[조정매집] 0", {"P2": 0}), ("[조정매집] 0.5", {"P2": 0.5}),
        ("신고가·저PBR 둘 다 0.5", {"P1": 0.5, "D2": 0.5}), ("신고가·저PBR 둘 다 0", {"P1": 0, "D2": 0}),
        ("강도 맞춤: 약한 둘 0.5 · [폭락반등]·[외인 매집] 1.5", {"P1": 0.5, "D2": 0.5, "P3": 1.5, "P7": 1.5}),
        ("[폭락반등]·[외인 매집] 1.5만", {"P3": 1.5, "P7": 1.5})]
BASEN = None
for lab, W in GRID:
    nav, ex = sim(W); row(lab, nav, ex)
    if BASEN is None: BASEN = (nav, ex)
    print("  %.1f분" % ((time.time() - t0) / 60), flush=True)
P("")
P("## ③ 놀고 있는 돈 자리 — 자리 혼자(100% 들고 있을 때)"); P("")
P("| 자리 | 2005~15 | 2016~22 | 2023~ | 전체 2005~ | |"); P("|---|---|---|---|---|---|")
for k in ("kospi", "lowvol", "lowvol_big"):
    row(k, np.cumprod(1 + SL[k]))
P("")
P("## ③ 규칙 계좌 + 남는 돈을 자리에"); P(""); P(HD); P("|---|---|---|---|---|---|")
for sl in ("cash0", "cash25", "kospi", "lowvol", "lowvol_big"):
    for fr in ((1.0,) if sl.startswith("cash") else (0.5, 1.0)):
        nav, ex = sim({}, sl, fr); row("%s %d%%" % (sl, fr * 100), nav, ex)
        print("  %.1f분" % ((time.time() - t0) / 60), flush=True)
P("")
P("## 해마다 (전체 2005~) — 기준 / 저변동 100% / 코스피 100% / 저변동 자리 혼자"); P("")
nb, _ = BASEN; nl, _ = sim({}, "lowvol", 1.0); nk, _ = sim({}, "kospi", 1.0); sv = np.cumprod(1 + SL["lowvol"]); ki = ix.values
P("| 해 | 기준 | +저변동 자리 | +코스피 자리 | 저변동 혼자 | 코스피 |"); P("|---|---|---|---|---|---|")
for y in sorted(set(d[:4] for d in dates)):
    m = np.where(np.array([d[:4] for d in dates]) == y)[0]
    if y < "2005" or len(m) < 20: continue
    a, b = m[0] - 1 if m[0] > 0 else m[0], m[-1]
    f = lambda x: "%+.1f%%" % ((x[b] / x[a] - 1) * 100)
    P("| %s | %s | %s | %s | %s | %s |" % (y, f(nb), f(nl), f(nk), f(sv), f(ki)))
(BASE / "research" / "reports").mkdir(exist_ok=True)
(BASE / "research" / "reports" / "combo_1108.md").write_text("\n".join(OUT), encoding="utf-8")
print("끝 %.1f분" % ((time.time() - t0) / 60))
