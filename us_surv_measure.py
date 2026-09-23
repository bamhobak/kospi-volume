# -*- coding: utf-8 -*-
"""미장 규칙 N1~N5 의 **생존편향을 실측**한다 — 생존 종목만 vs 폐지 포함 (2026-09-23).

같은 패널(us_full.pkl)·같은 코드로 두 번 돌린다. 다른 건 **유니버스에 폐지 종목이 있느냐** 하나뿐이다.
규칙 조건은 us_verify.py(사이트 신호 건수와 대조한 정본)를 그대로 옮겼다.

같은 날 순위로 거르는 조건(거래대금 상위 40%)과 업종 60일 수익률(u)은 **집단마다 따로** 계산한다 —
폐지 종목이 들어오면 그날의 순위·업종 중앙값 자체가 바뀌고, 그것도 생존편향의 일부다.

[실적 서프라이즈](N6)는 폐지 종목의 실적 자료가 없어 여기서 잴 수 없다.

    python us_surv_measure.py
"""
import sys, time, warnings
warnings.filterwarnings("ignore")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:          # 다른 스크립트가 출력을 가로채 불러 쓸 때(us_n3_acct.py)
    pass
from pathlib import Path
import numpy as np, pandas as pd
import FinanceDataReader as fdr

BASE = Path(__file__).parent
US = BASE / "data" / "us"
SINCE = sys.argv[sys.argv.index("--since") + 1] if "--since" in sys.argv else "20160101"
UNTIL = sys.argv[sys.argv.index("--until") + 1] if "--until" in sys.argv else "20991231"
PANEL = sys.argv[sys.argv.index("--panel") + 1] if "--panel" in sys.argv else "us_full.pkl"
NAME = {"N1": "상승장 신고가", "N2": "낙폭과대", "N3": "저PBR 낙폭", "N4": "자사주 낙폭", "N5": "잔잔한 급등주"}
HOLD = {"N1": 40, "N2": 20, "N3": 60, "N4": 60, "N5": 60}   # N3 2026-09-24 40→60일
t0 = time.time()


def log(m):
    print(f"{time.strftime('%H:%M:%S')} {m}", flush=True)


log("us_full.pkl 읽는 중")
A = pd.read_pickle(BASE / "data" / PANEL)
A = A.sort_values(["ticker", "date"]).reset_index(drop=True)

# 업종 60일 수익률 — 가격 필터 **전** 전체 행으로 (us_panel.py 와 같은 순서), 집단별로
A["u_all"] = A.groupby(["date", "sic2"]).ret60.transform("median")
sv = A.grp == "생존"
A["u_surv"] = np.nan
A.loc[sv, "u_surv"] = A[sv].groupby(["date", "sic2"]).ret60.transform("median")

K = A[A.rawclose >= 3].copy()          # us_verify 와 같이 '주가 $3 이상' 행으로 거른 뒤 계산한다
del A
K["close"] = K.rawclose
ud = sorted(K.date.unique()); ADI = {d: i for i, d in enumerate(ud)}
K["di"] = K.date.map(ADI).astype(np.int32)
G = K.groupby("ticker", sort=False)
log(f"  {len(K):,}행 · 생존 {K[K.grp == '생존'].ticker.nunique():,} · 폐지 {K[K.grp == '폐지'].ticker.nunique():,}종목")

# ── 종목 자기 이력으로만 만드는 재료 (집단과 무관) — us_verify.py 그대로 ───────
R = G.close.pct_change() * 100
hi250 = G.high.transform(lambda s: s.rolling(250).max())
K["fromhi"] = (K.close / hi250 - 1) * 100


def first_event(state, back=20):
    s = state.fillna(False)
    prev = s.groupby(K.ticker).transform(lambda x: x.shift(1).rolling(back, min_periods=1).max())
    return (s & (prev.fillna(0) == 0)).fillna(False)


K["nh5"] = first_event(K.fromhi >= -5)
v3 = G.volume.transform(lambda s: s.rolling(3).mean())
vmo = G.volume.transform(lambda s: s.shift(3).rolling(20).mean())
K["remo"] = v3 / vmo * 100
v20 = R.groupby(K.ticker).transform(lambda s: s.rolling(20).std())
v250 = R.groupby(K.ticker).transform(lambda s: s.rolling(250).std())
K["pinr"] = v20 / v250
c20hi = G.close.transform(lambda s: s.rolling(20).max())
c20lo = G.close.transform(lambda s: s.rolling(20).min())
K["hl20"] = (c20hi / c20lo - 1) * 100
K["absr"] = R.abs().groupby(K.ticker).transform(lambda s: s.rolling(60).mean())
for k in (60, 120, 250):
    K[f"r{k}"] = (K.close / G.close.shift(k) - 1) * 100
log("  가격 재료 완료")

IX = fdr.DataReader("US500", "2004-06-01"); IX = IX[IX.Close > 0].copy()
IX["date"] = IX.index.strftime("%Y%m%d"); IX["ma60"] = IX.Close.rolling(60).mean()
UP = K.date.map(dict(zip(IX.date, IX.Close > IX.ma60))).fillna(False)
DN = ~UP

# 자사주 집행중 — 최근 88일 안에 spend 보고 (생존 buyback.pkl + 폐지 buyback_dead.pkl)
BB = pd.concat([pd.read_pickle(US / "buyback.pkl"), pd.read_pickle(US / "buyback_dead.pkl")], ignore_index=True)
BB = BB[(BB.tag == "spend") & (BB.val.astype(float) > 0)][["ticker", "filed"]].dropna()
BB["filed"] = BB.filed.astype(str)
bbmap = BB.drop_duplicates().groupby("ticker").filed.apply(lambda s: np.array(sorted(s))).to_dict()
d0 = (pd.to_datetime(K.date, format="%Y%m%d") - pd.Timedelta(days=88)).dt.strftime("%Y%m%d").values
dd, tk = K.date.values, K.ticker.values
act = np.zeros(len(K), bool)
cur, arr = None, None
for i in range(len(K)):
    if tk[i] != cur:
        cur = tk[i]; arr = bbmap.get(cur)
    if arr is None or not len(arr):
        continue
    act[i] = np.searchsorted(arr, dd[i], "right") > np.searchsorted(arr, d0[i], "left")
K["bbact"] = act
log(f"  자사주 집행중 {act.mean() * 100:.1f}%")

DEAD = ((K.pinr < 0.5) & (K.hl20 < 8)).fillna(False)
bb_state = (K.fromhi <= -30) & (K.ret20 <= -20) & K.bbact
BBNEW = first_event(bb_state)
q_state = (K.r250 >= 120) & (K.r60 > 0) & (K.r120 > 0) & (K.absr <= 1.5)
QNEW = first_event(q_state)
qage = QNEW.groupby(K.ticker).transform(
    lambda s: (np.arange(len(s)) - pd.Series(np.where(s.values, np.arange(len(s)), np.nan), index=s.index).ffill()))


def rules(mask, ucol):
    """집단(mask)마다 그날 순위·업종 중앙값을 다시 매긴다."""
    amtq = K.amt20.where(mask).groupby(K.date).rank(pct=True)
    usliq = (amtq >= 0.60).fillna(False) & mask
    u = K[ucol]
    c = {}
    c["N1"] = usliq & UP & K.nh5 & (K.remo <= 100) & ~DEAD
    c["N2"] = mask & DN & (K.ret20 <= -30) & (K.su1 >= 2) & (u <= -10) \
        & (K["부채비율"].isna() | (K["부채비율"] <= 200)) & (K.amt20 >= 2)
    c["N3"] = mask & DN & (K.PBR > 0) & (K.PBR <= 0.8) & (K.ret20 <= -10) & (K.su1 >= 2) \
        & (u <= -10) & (K.amt20 >= 2)
    c["N4"] = usliq & BBNEW
    c["N5"] = usliq & (qage <= 3)
    return {k: v.fillna(False) for k, v in c.items()}


def dedup(cond, h):
    Z = K[cond].dropna(subset=[f"n{h}"])
    Z = Z[Z.buy > 0].sort_values("di")
    keep, last = [], {}
    for t, i, ix in zip(Z.ticker.values, Z.di.values, Z.index):
        if last.get(t, -10 ** 9) >= i:
            continue
        last[t] = i + h
        keep.append(ix)
    Z = Z.loc[keep]
    return Z[(Z.date >= SINCE) & (Z.date <= UNTIL)]


def st(r):
    r = r.astype(float)
    if not len(r):
        return dict(n=0)
    up, dn = r[r > 0].sum(), -r[r < 0].sum()
    return dict(n=len(r), avg=r.mean(), med=r.median(), win=(r > 0).mean() * 100,
                pf=up / dn if dn > 0 else np.nan, trim=r[r <= r.quantile(0.95)].mean(), worst=r.min())


RES = {}
for vname, mask, ucol in (("생존만", K.grp == "생존", "u_surv"), ("폐지 포함", pd.Series(True, index=K.index), "u_all")):
    C = rules(mask, ucol)
    for rid, cond in C.items():
        h = HOLD[rid]
        Z = dedup(cond, h)
        RES[(rid, vname)] = (st(Z[f"n{h}"]), Z)
    log(f"  {vname} 끝")

f = lambda v: f"{v:+.2f}%" if v == v else "—"
_per = f"{SINCE[:4]}~{UNTIL[:4]}" if UNTIL < "2099" else f"{SINCE[:4]}~"
print(f"\n## 생존 종목만 vs 폐지 포함 — 건별 ({_per}, 신호 나면 다 산다)\n")
print("| 규칙 | 보유 | 생존만 건수 | 평균 | 승률 | 상위5% 뺀 | → 폐지 포함 건수 | 평균 | 승률 | 상위5% 뺀 | 평균 차이 |")
print("|---|---|---|---|---|---|---|---|---|---|---|")
for rid in NAME:
    a, _ = RES[(rid, "생존만")]; b, Zb = RES[(rid, "폐지 포함")]
    print(f"| [{NAME[rid]}] | {HOLD[rid]}일 | {a['n']:,} | {f(a['avg'])} | {a['win']:.0f}% | {f(a['trim'])} | "
          f"{b['n']:,} | {f(b['avg'])} | {b['win']:.0f}% | {f(b['trim'])} | **{b['avg'] - a['avg']:+.2f}%p** |")

print("\n## 폐지 포함판에서 — 폐지 종목 거래만 떼어 보면\n")
print("| 규칙 | 전체 건수 | 폐지 종목 거래 | 비중 | 폐지 종목 평균 | 생존 종목 평균 | 폐지 종목 최악 |")
print("|---|---|---|---|---|---|---|")
for rid in NAME:
    b, Zb = RES[(rid, "폐지 포함")]
    h = HOLD[rid]
    dz, sz = Zb[Zb.grp == "폐지"][f"n{h}"], Zb[Zb.grp == "생존"][f"n{h}"]
    print(f"| [{NAME[rid]}] | {len(Zb):,} | {len(dz):,} | {len(dz) / max(len(Zb), 1) * 100:.0f}% | "
          f"{f(dz.mean())} | {f(sz.mean())} | {f(dz.min())} |")

print("\n## 연도별 평균 — 생존만 → 폐지 포함\n")
ys = [str(y) for y in range(int(SINCE[:4]), min(int(UNTIL[:4]), 2026) + 1)]
print("| 규칙 | " + " | ".join(ys) + " |")
print("|---|" + "---|" * len(ys))
for rid in NAME:
    h = HOLD[rid]
    za, zb = RES[(rid, "생존만")][1], RES[(rid, "폐지 포함")][1]
    cells = []
    for y in ys:
        a = za[za.date.str[:4] == y][f"n{h}"]; b = zb[zb.date.str[:4] == y][f"n{h}"]
        cells.append(f"{a.mean():+.1f}→{b.mean():+.1f}" if len(a) and len(b) else "·")
    print(f"| [{NAME[rid]}] | " + " | ".join(cells) + " |")
log(f"끝 ({(time.time() - t0) / 60:.1f}분)")
