# -*- coding: utf-8 -*-
"""H0424 공매도 과열종목 지정 → 다음 날 공매도 금지 (2026-11-17 사용자 "규칙 하나만 더 찾아줄 수 없어?").

가설: 공매도가 몰리며 급락한 종목은 장 마감 뒤(18~20시) '공매도 과열종목'으로 지정되고 다음 거래일 하루 공매도가 막힌다.
      누르던 손이 하루 빠지니 그날 되돌린다(강제된 수급 공백 — 모양이 아니라 제도).
자료: data/dart/kind_time.db (KIND 시장조치 공시 시각, 2017-04~) · research/cache/factory_px.pkl (일봉 시가·종가)
사건: 제목 '공매도 과열종목 지정(공매도 거래 금지 적용)' — 공시 날 D(장 마감 뒤) → 금지 날 D+1.  '연장'은 따로.
 ① 말한 그대로 판: D+1 시가 매수 → D+1 종가 매도(금지 당일)
 ② 변형 판: 보유 1·2·3·5·10일 · D 종가→D+1 시가(밤사이, 실전 불가 참고) · D+1 종가→D+2(금지 풀린 날) · D 낙폭 구간 · D+1 시가 갭 구간 · 시장 · 거래대금 크기 · 연장
 대조: 같은 날 · D 등락률 ±1.5%p 안 · 지정 안 된 종목(같은 바탕 조건)의 같은 보유 평균. 날 바구니 t. 비용 0.23.
 기간: 학습 2017~22 / 검증 2023~ (2020-03~2021-05 · 2023-11~2025-03 공매도 전면 금지라 사건 없음).
    python research/ssban_1117.py
"""
import math, os, sqlite3, sys, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
os.chdir(BASE)
sys.stdout.reconfigure(encoding="utf-8")
COST = 0.23
PER = (("학습 17~22", "20170101", "20221231"), ("검증 23~", "20230101", "20991231"))
OUT = []; P_ = lambda s="": (OUT.append(s), print(s, flush=True))
t_ = lambda s: s.mean() / s.std(ddof=1) * math.sqrt(len(s)) if len(s) > 2 and s.std(ddof=1) > 0 else 0.0

P = pd.read_pickle(BASE / "research" / "cache" / "factory_px.pkl")
P = P[P.date >= "20161001"]
cal = sorted(P.date.unique()); ci = {d: i for i, d in enumerate(cal)}
tk = sorted(P.ticker.unique()); ti = {t: i for i, t in enumerate(tk)}
W = lambda col: P.pivot(index="date", columns="ticker", values=col).reindex(index=cal, columns=tk).values.astype(np.float64)
OP, CL = W("open"), W("close"); del P
nd, nt = CL.shape
PC = np.vstack([np.full((1, nt), np.nan), CL[:-1]])
R1 = (CL / PC - 1) * 100                                   # 그날 등락률
rr = CL / PC; sp = (rr > 1.42) | (rr < 0.58)
blk = pd.DataFrame(sp).rolling(60, min_periods=1).max().values.astype(bool)
# 거래대금 자료가 일봉판에 없어 값(종가) 바닥만: 종가 1000원↑ · 시가 있음(거래정지 아님)
okb = (CL >= 1000) & ~blk & np.isfinite(OP) & (OP > 0)
sh = lambda A, k: np.vstack([A[k:], np.full((k, nt), np.nan)]) if k > 0 else A


def fwd(entry, exit_):                                      # % 비용 뒤, 이상값 지움
    x = (exit_ / entry - 1) * 100 - COST
    x[(np.abs(x) > 60) | ~np.isfinite(x)] = np.nan
    return x


# 금지 날 = i+1 기준 수익(사건 날 i 줄에 놓음)
O1, C1 = sh(OP, 1), sh(CL, 1)
RET = {"밤사이(D 종가→D+1 시가·참고)": fwd(CL, O1), "D+1 시가→종가": fwd(O1, C1)}
for h in (2, 3, 5, 10): RET["D+1 시가→%d일째 종가" % h] = fwd(O1, sh(CL, h))
RET["D+1 종가→D+2 종가(금지 풀린 날)"] = fwd(C1, sh(CL, 2))
RET["D+1 종가→D+2 시가"] = fwd(C1, sh(OP, 2))
GAP1 = (O1 / CL - 1) * 100                                  # D+1 시가 갭
ok1 = okb & np.vstack([okb[1:], np.zeros((1, nt), bool)])

c = sqlite3.connect("file:%s?mode=ro" % (BASE / "data" / "dart" / "kind_time.db"), uri=True)
K = pd.read_sql("select day, hm, kcode, market, title from kind where title like '공매도 과열종목%'", c); c.close()
K = K[~K.title.str.contains(r"\(.*우.*\)$|기타시장안내")]         # 우선주 따로 공시는 뺌
K["ext"] = K.title.str.contains("연장"); K["t"] = K.kcode + "0"
K = K[K.t.isin(ti) & K.day.isin(ci)].drop_duplicates(["day", "t", "ext"])
K["i"] = K.day.map(ci); K["j"] = K.t.map(ti)
K = K[ok1[K.i.values, K.j.values]]
K["r0"] = R1[K.i.values, K.j.values]; K["gap"] = GAP1[K.i.values, K.j.values]; K["px"] = CL[K.i.values, K.j.values]
for k, A in RET.items(): K[k] = A[K.i.values, K.j.values]
EV = np.zeros((nd, nt), bool); EV[K.i.values, K.j.values] = True


def ctrl(i, r0, k):                                          # 같은 날 · D 등락률 ±1.5%p · 지정 안 된 종목 평균
    m = ok1[i] & ~EV[i] & (np.abs(R1[i] - r0) <= 1.5)
    v = RET[k][i][m]; v = v[np.isfinite(v)]
    return v.mean() if len(v) >= 5 else np.nan


P_("# H0424 공매도 과열종목 지정 → 다음 날 공매도 금지 (2026-11-17)\n")
P_("사건 %d건(지정 %d · 연장 %d) · 날 %d · %s~%s · 비용 %.2f 뒤 · D 등락률 중앙 %.1f%%" % (len(K), (~K.ext).sum(), K.ext.sum(), K.day.nunique(), K.day.min(), K.day.max(), COST, K.r0.median()))
P_("연도별 지정 건수: " + " · ".join("%s %d" % (y, n) for y, n in K[~K.ext].day.str[:4].value_counts().sort_index().items()))
Z0 = K[~K.ext].copy()
for k in RET: Z0["c_" + k] = [ctrl(i, r, k) for i, r in zip(Z0.i.values, Z0.r0.values)]


def row(name, Z, k):
    cells = []
    for _, a, b in PER:
        z = Z[(Z.day >= a) & (Z.day <= b)].dropna(subset=[k])
        if len(z) < 20: cells.append("%d건 | – | – | – | –" % len(z)); continue
        d = z.groupby("day")[k].mean(); e = (z[k] - z["c_" + k]).dropna(); ed = z.assign(e=z[k] - z["c_" + k]).groupby("day").e.mean().dropna()
        cells.append("%d·%d | %+.2f%% (중앙 %+.2f·승 %.0f%%) | %+.2f%% (t%.1f) | %+.2f (t%.1f) | %s" % (
            len(z), len(d), z[k].mean(), z[k].median(), (z[k] > 0).mean() * 100, d.mean(), t_(d), ed.mean() if len(ed) else float("nan"), t_(ed),
            " ".join("%s:%+.1f" % (y[2:], v) for y, v in z.groupby(z.day.str[:4])[k].mean().items())))
    P_("| %s | %s | %s |" % (name, cells[0], cells[1]))


HD = "| 판 | 학습 건·날 | 건당(중앙·승률) | 날 바구니(t) | 같은 날 닮은 낙폭 대비(t) | 연도별 | 검증 건·날 | 건당(중앙·승률) | 날 바구니(t) | 대조 대비(t) | 연도별 |\n|---|---|---|---|---|---|---|---|---|---|---|"
P_("\n## 1. 말한 그대로 + 보유 변형 (지정 전체)\n"); P_(HD)
for k in RET: row(k, Z0, k)
P_("\n## 2. D 낙폭 구간 × (D+1 시가→종가 · 3일 · 5일)\n"); P_(HD)
for nm, m in (("D ≤ -10%", Z0.r0 <= -10), ("D -10~-5%", (Z0.r0 > -10) & (Z0.r0 <= -5)), ("D -5~0%", (Z0.r0 > -5) & (Z0.r0 <= 0)), ("D > 0%", Z0.r0 > 0)):
    for k in ("D+1 시가→종가", "D+1 시가→3일째 종가", "D+1 시가→5일째 종가"): row(nm + " · " + k[4:], Z0[m], k)
P_("\n## 3. D+1 시가 갭 구간 × (시가→종가 · 3일)\n"); P_(HD)
for nm, m in (("갭 ≤ -3%", Z0.gap <= -3), ("갭 -3~-1%", (Z0.gap > -3) & (Z0.gap <= -1)), ("갭 -1~+1%", (Z0.gap > -1) & (Z0.gap < 1)), ("갭 +1~+3%", (Z0.gap >= 1) & (Z0.gap < 3)), ("갭 ≥ +3%", Z0.gap >= 3)):
    for k in ("D+1 시가→종가", "D+1 시가→3일째 종가"): row(nm + " · " + k[4:], Z0[m], k)
P_("\n## 4. 시장 · 가격대 · 연장\n"); P_(HD)
for nm, Z in (("유가증권", Z0[Z0.market == "유가증권"]), ("코스닥", Z0[Z0.market == "코스닥"]), ("종가 1만원↑", Z0[Z0.px >= 10000]), ("종가 1만원↓", Z0[Z0.px < 10000])):
    for k in ("D+1 시가→종가", "D+1 시가→3일째 종가"): row(nm + " · " + k[4:], Z, k)
ZE = K[K.ext].copy()
for k in RET: ZE["c_" + k] = [ctrl(i, r, k) for i, r in zip(ZE.i.values, ZE.r0.values)]
for k in ("D+1 시가→종가", "D+1 시가→3일째 종가"): row("연장 · " + k[4:], ZE, k)
P_("\n## 5. 붐비는 날(그날 지정 종목 수)\n"); P_(HD)
Z0["n"] = Z0.groupby("day").t.transform("size")
for nm, m in (("하루 1~2건", Z0.n <= 2), ("3~9건", (Z0.n >= 3) & (Z0.n <= 9)), ("10건↑", Z0.n >= 10)):
    for k in ("D+1 시가→종가", "D+1 시가→3일째 종가"): row(nm + " · " + k[4:], Z0[m], k)
Z0.to_pickle("C:/temp/kp/ssban_ev.pkl")
(ROOT / "reports" / "ssban_1117.md").write_text("\n".join(OUT), encoding="utf-8")
