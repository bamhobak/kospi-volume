# -*- coding: utf-8 -*-
"""2026-11-14 밤 과거 받기 끝(NXT 장전 1분봉 2025-03~ · NXT 종목 전부 · 봉 826만) → [장전 되돌림](T5) 다시 재기.
옛 패널(pmrev5_panel_1103)은 '저가 -2.5%↓ 종목 전부 + 나머지 표본(가중 중앙)' 369일(2025-04~2026-10-08).
새 자료 = NXT 종목 전부(시장 중앙 정확) + 새 날 43일(2025-03 · 2026-10-09~11-12).
정의는 옛 패널 그대로: pT = 08:40 까지 마지막 체결(08:35 뒤) · pre = pT ÷ 어제 통합 종가(토스 일봉) · rpre = pre − 그날 중앙(전부)
  cum = 08:01~08:40 누적 거래대금(c×v) · 매수 = 08:41~45 VWAP − 봉폭 절반(r_vwhs) / 5분 최고가(r_hi) · 매도 = KRX 시가 · 비용 0.23
  규칙 = rpre ≤ -3 & cum ≤ 10.19억 & 그날 rpre 순위 ≤ 4(두꺼운 종목도 셈) · 붐비는 날(신호 10개↑) 쉼(11-13~)
    python research/t5_full_1114.py           (어제 종가: 10-08 까지 toss_daily_kr · 그 뒤는 토스 일봉 새로 받아 캐시)
"""
import sys, glob, json, math, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(BASE)); sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
C = ROOT / "cache"
CUM_MAX, REL, RANK_MAX, CROWD = 1_019_060_000, -3.0, 4, 10
COST = 0.23
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))

# ── 1. 장전 1분봉 ──
# 밤 과거 받기(bf_nxt_pre)는 예전에 받은 장전 봉(C:/temp/kp/pm_m1_1103·pm_parts·pm_parts2 — 옛 패널 재료)을 건너뛰고 빈 곳만 받았다 → 합쳐야 '전 종목'
KP = Path("C:/temp/kp")
PB = [str(KP / "pm_m1_1103.parquet")] + glob.glob(str(KP / "pm_parts" / "bars_*.parquet")) + glob.glob(str(KP / "pm_parts2" / "bars_*.parquet")) + glob.glob(str(C / "bf_nxt_pre" / "bars_*.parquet"))
B = pd.concat([pd.read_parquet(f, columns=["t", "d", "hm", "h", "l", "c", "v"]) for f in PB], ignore_index=True)
B["t"] = B.t.astype(str); B["d"] = B.d.astype(str); B["hm"] = B.hm.astype(int)
B = B.drop_duplicates(["t", "d", "hm"]); B = B[(B.hm >= 801) & (B.hm <= 850)]
P("장전 봉 %d · %d일 %s~%s" % (len(B), B.d.nunique(), B.d.min(), B.d.max()))

# ── 2. 어제 통합 종가 ──
T0 = pd.read_pickle(C / "toss_daily_kr.pkl").rename(columns={"ticker": "t", "date": "d"})[["t", "d", "tc"]]
T0["t"] = T0.t.astype(str); T0["d"] = T0.d.astype(str)
FN = C / "toss_1d_nxt_1114.parquet"
if not FN.exists():
    import collect_m1 as M
    syms = sorted(B[B.d >= "20261001"].t.unique()); rows = []
    for i, s in enumerate(syms):
        try:
            for x in (M.get("/api/v1/candles", symbol=s, interval="1d", count=40) or {}).get("candles") or []:
                rows.append((s, x["timestamp"][:10].replace("-", ""), float(x["closePrice"])))
        except Exception as ex:
            print("일봉 실패", s, repr(ex)[:80])
        time.sleep(0.25)                                   # 초당 ~4 (밤 과거 받기와 합쳐도 토스 한도 안)
        if i % 100 == 0: print("일봉", i, "/", len(syms), flush=True)
    pd.DataFrame(rows, columns=["t", "d", "tc"]).to_parquet(FN, index=False)
T1 = pd.read_parquet(FN)
T1 = T1[T1.d < "20261114"]
TC = pd.concat([T0[T0.d < "20261001"], T1], ignore_index=True).drop_duplicates(["t", "d"], keep="last")

# ── 3. KRX 시가 (m1_daysum ≤10-23, 그 뒤 KRX 1분봉 일 파일 첫 봉) ──
K = pd.read_parquet(C / "m1_daysum.parquet", columns=["t", "d", "o"]); K["t"] = K.t.astype(str); K["d"] = K.d.astype(str)
K = K[K.d >= "20250301"]
ks = []
for f in sorted(glob.glob(str(BASE / "data/m1/KR/day/*.parquet"))):
    d = Path(f).stem
    if d <= K.d.max(): continue
    x = pd.read_parquet(f, columns=["t", "ts", "o", "v"]); x = x[x.v > 0].sort_values("ts")
    f0 = x.groupby("t").first().reset_index(); f0["d"] = d; ks.append(f0[["t", "d", "o"]])
K = pd.concat([K] + ks, ignore_index=True)
DAYS = sorted(set(K.d) | set(B.d)); PREV = {DAYS[i]: DAYS[i - 1] for i in range(1, len(DAYS))}

# ── 4. 패널 (08:40) ──
T_ = 840
s = B[(B.hm <= T_) & (B.v > 0)].sort_values(["t", "d", "hm"])
last = s.groupby(["t", "d"]).agg(pT=("c", "last"), hmT=("hm", "last"))
cum = B[B.hm <= T_].assign(val=lambda z: z.c * z.v).groupby(["t", "d"]).val.sum().rename("cum")
w = B[(B.hm > T_) & (B.hm <= T_ + 5)]
agg = w.assign(val=w.c * w.v).groupby(["t", "d"]).agg(val5=("val", "sum"), v5=("v", "sum"), hi5=("h", "max"), hmean=("h", "mean"), lmean=("l", "mean"))
agg["vw5"] = agg.val5 / agg.v5.replace(0, np.nan)
S = last.join(cum).join(agg, how="left").reset_index()
S = S[S.hmT >= T_ - 5]
S["pd"] = S.d.map(PREV)
S = S.merge(TC.rename(columns={"d": "pd", "tc": "tc_y"}), on=["t", "pd"], how="left").merge(K, on=["t", "d"], how="left")
S = S[S.tc_y.notna()]
S["pre"] = (S.pT / S.tc_y - 1) * 100
S = S[S.pre.abs() < 30]
S["mpre"] = S.groupby("d").pre.transform("median"); S["rpre"] = S.pre - S.mpre
S["rk"] = S.groupby("d").rpre.rank(method="first")
S["r_vw"] = ((S.o / S.vw5 - 1) * 100 - COST).clip(-40, 60)
S["hs"] = (S.hmean - S.lmean) / 2 / S.vw5 * 100
S["r_vwhs"] = (S.r_vw - S.hs).clip(-40, 60)
S["r_hi"] = ((S.o / S.hi5 - 1) * 100 - COST).clip(-40, 60)
base = S[(S.rpre <= REL) & (S.cum <= CUM_MAX)]
S["nsig"] = S.d.map(base.groupby("d").size()).fillna(0)
S.to_pickle(r"C:\temp\kp\t5_full_panel_1114.pkl")
P("패널 %d 종목-날 · %d일 · 하루 종목 중앙 %d · 시가 없는 신호 %d" % (len(S), S.d.nunique(), S.groupby("d").size().median(),
  int(base.o.isna().sum())))

# ── 5. 옛 패널과 대조(겹친 날) ──
O = pd.read_pickle(r"C:\temp\kp\pmrev5_panel_1103.pkl"); O = O[(O.tm == 840) & O.rpre.notna() & O.o.notna() & (O.pre.abs() < 30)].copy()
O["rk"] = O.groupby("d").rpre.rank(method="first")
ob = O[(O.rpre <= REL) & (O.cum <= CUM_MAX)]; oR = ob[ob.rk <= RANK_MAX]
nR = S[(S.rpre <= REL) & (S.cum <= CUM_MAX) & (S.rk <= RANK_MAX) & S.r_vwhs.notna()]
od = set(O.d)
a = set(zip(oR.t, oR.d)); b = set(zip(nR[nR.d.isin(od)].t, nR[nR.d.isin(od)].d))
mm = (O.pre - O.rpre).groupby(O.d).median().rename("old").to_frame().join(S.groupby("d").mpre.first().rename("new"), how="inner")
P("\n## 0. 옛 패널과 대조 (겹친 %d일)\n" % len(mm))
P("- 시장 중앙: 옛(표본 가중) − 새(전부) 차이 평균 %+.2f%%p · 절댓값 중앙 %.2f%%p · 0.5%%p 넘게 다른 날 %d일" % (
  (mm.old - mm.new).mean(), (mm.old - mm.new).abs().median(), int(((mm.old - mm.new).abs() > 0.5).sum())))
P("- 규칙 신호(순위 4 안): 옛 %d건 · 새 %d건 · 겹침 %d · 옛에만 %d · 새에만 %d" % (len(a), len(b), len(a & b), len(a - b), len(b - a)))
P("- 같은 날들 건당(연구 기준): 옛 %+.2f%% · 새 %+.2f%%" % (oR.r_vwhs.mean(), nR[nR.d.isin(od)].r_vwhs.mean()))


def st(Z, col="r_vwhs"):
    Z = Z[Z[col].notna()]
    if not len(Z): return None
    d = Z.groupby("d")[col].mean(); sd = d.std(ddof=1) if len(d) > 1 else np.nan
    return dict(n=len(Z), days=len(d), mean=Z[col].mean(), win=(Z[col] > 0).mean() * 100, dmean=d.mean(),
                t=d.mean() / sd * math.sqrt(len(d)) if sd and sd > 0 else 0.0, dpos=(d > 0).mean() * 100, hi=Z.r_hi.mean())


def row(nm, Z):
    a = st(Z)
    if not a: P("| %s | 0 | | | | |" % nm); return
    P("| %s | %d건 · %d일 | %+.2f%% | %.0f%% | %+.2f%% (t %.1f · 플러스 날 %.0f%%) | %+.2f%% |" % (nm, a["n"], a["days"], a["mean"], a["win"], a["dmean"], a["t"], a["dpos"], a["hi"]))


def head(): P("| 판 | 표본 | 건당(연구 기준) | 승률 | 날 바구니 | 최고가에 샀다면 |"); P("|---|---|---|---|---|---|")


PER = (("2025-03 (새 날 · NXT 첫 달)", "20250301", "20250331"), ("2025-04~12 (옛 학습)", "20250401", "20251231"),
       ("2026-01~10-08 (옛 검증)", "20260101", "20261008"), ("**2026-10-09~11-03 (새 날 · 실전 전)**", "20261009", "20261103"),
       ("2026-11-04~11-12 (실전 기간)", "20261104", "20261112"))


def rule(rel=REL, rank=RANK_MAX, crowd=CROWD, cmax=CUM_MAX):
    Z = S[(S.rpre <= rel) & (S.cum <= cmax)]
    if rank: Z = Z[Z.rk <= rank]
    if crowd: Z = Z[Z.nsig < crowd]
    return Z


P("\n## 1. 지금 규칙(-3%p · 얇음 · 순위 4 안 · 신호 10개↑ 날 쉼) — 기간별\n"); head()
R = rule()
for nm, lo, hi in PER: row(nm, R[(R.d >= lo) & (R.d <= hi)])
row("전체 %d일" % S.d.nunique(), R)
P("\n새 날 실전 전(10-09~11-03) 거래 목록:")
for r in R[(R.d >= "20261009") & (R.d <= "20261103")].sort_values(["d", "rk"]).itertuples():
    P("  %s %s 순위 %d · 시장 대비 %+.1f%%p · 누적 %.1f억 · 연구 %+.2f%% · 최고가 %+.2f%% · 그날 신호 %d" % (r.d, r.t, r.rk, r.rpre, r.cum / 1e8, r.r_vwhs, r.r_hi, r.nsig))

P("\n## 2. 변형 — 새 날 둘(2025-03 · 2026-10-09~11-03)만 / 전체\n")
P("| 변형 | 새 날 표본 | 새 날 건당 | 새 날 날 바구니 | 전체 건당 | 전체 날 바구니(t) |"); P("|---|---|---|---|---|---|")
NEWD = lambda Z: Z[((Z.d >= "20250301") & (Z.d <= "20250331")) | ((Z.d >= "20261009") & (Z.d <= "20261103"))]
for nm, kw in (("지금 판", {}), ("붐비는 날 쉼 없음", dict(crowd=None)), ("순위 제한 없음", dict(rank=None)), ("순위·쉼 둘 다 없음", dict(rank=None, crowd=None)),
               ("깊이 -4%p", dict(rel=-4.0)), ("깊이 -2.5%p", dict(rel=-2.5)), ("순위 2 안", dict(rank=2)), ("얇음 없음(누적 제한 X)", dict(cmax=1e15))):
    Z = rule(**kw); a, b = st(NEWD(Z)), st(Z)
    P("| %s | %s | %s | %s | %+.2f%% | %+.2f%% (t %.1f) |" % (nm, ("%d건 · %d일" % (a["n"], a["days"])) if a else "0", ("%+.2f%%" % a["mean"]) if a else "-",
      ("%+.2f%%" % a["dmean"]) if a else "-", b["mean"], b["dmean"], b["t"]))

P("\n## 3. 붐비는 날 — 전체 기간, 그날 신호 수별 (순위 4 안, 쉼 없이)\n"); head()
R0 = rule(crowd=None)
for nm, lo, hi in (("1~2개", 0, 2), ("3~5개", 2, 5), ("6~9개", 5, 9), ("10개↑", 9, 9999)):
    row(nm, R0[(R0.nsig > lo) & (R0.nsig <= hi)])
(ROOT / "reports" / "t5_full_1114.md").write_text("# [장전 되돌림] NXT 전 종목 장전 1분봉으로 다시 재기 (11-14)\n\n" + "\n".join(OUT), encoding="utf-8")
