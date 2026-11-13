# -*- coding: utf-8 -*-
"""2026-11-14 사용자 "제안하는 거 했을 때 수익률 승률 수익금 어떻게 달라지는지" — [장전 되돌림] 장후 필터 변형 돈 계산.
금액 = 실전 설정 그대로: 종목당 100만 × 계단(시장 대비 -5%p↓ 3배 · -4%p↓ 2배 · 그 밖 1배, nxt_pre.STEPS)
체결 손해 = 11-03 T5 금액 실측과 같게: 매수 5분(08:41~45) 거래대금의 10% 까지만 체결 · 충격 max(0, -0.25 + 2.40√(체결÷5분 거래대금)) %
수익 = r_vwhs(08:41~45 VWAP − 봉폭 절반 → KRX 시가, 비용 0.23 뒤) − 충격
    python research/t5_money_1114.py"""
import sys, glob, math
from pathlib import Path
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent; C = ROOT / "cache"
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
OUT = []; P = lambda s="": (OUT.append(s), print(s, flush=True))
CUM = 1_019_060_000
S = pd.read_pickle(r"C:\temp\kp\t5_full_panel_1114.pkl")
K = pd.read_parquet(C / "m1_daysum.parquet", columns=["t", "d", "c"]); K["t"] = K.t.astype(str); K["d"] = K.d.astype(str); K = K[K.d >= "20250101"]; ks = []
for f in sorted(glob.glob(str(BASE / "data/m1/KR/day/*.parquet"))):
    d = Path(f).stem
    if d <= K.d.max(): continue
    x = pd.read_parquet(f, columns=["t", "ts", "c", "v"]); x = x[x.v > 0].sort_values("ts")
    g = x.groupby("t").agg(c=("c", "last")).reset_index(); g["d"] = d; ks.append(g)
K = pd.concat([K] + ks, ignore_index=True).sort_values(["t", "d"]); K["kpc"] = K.groupby("t").c.shift(1)
S = S.merge(K[["t", "d", "kpc"]], on=["t", "d"], how="left")
S["ah"] = (S.tc_y / S.kpc - 1) * 100


def rule(ahmax=None):
    m = (S.rpre <= -3) & (S.cum <= CUM)
    if ahmax is not None: m &= S.ah.fillna(0) <= ahmax
    sig = S[m]; ns = sig.groupby("d").size()
    Z = sig[sig.rk <= 4].copy(); Z["ns"] = Z.d.map(ns)              # 순위는 지금처럼 그날 전 종목 깊이 순
    Z = Z[(Z.ns < 10) & Z.r_vwhs.notna() & (Z.val5 > 0)].copy()
    Z["want"] = 1e6 * np.where(Z.rpre <= -5, 3, np.where(Z.rpre <= -4, 2, 1))
    Z["fill"] = np.minimum(Z.want, 0.10 * Z.val5)
    Z["imp"] = np.maximum(0, -0.25 + 2.40 * np.sqrt(Z.fill / Z.val5))
    Z["ret"] = Z.r_vwhs - Z.imp
    Z["pnl"] = Z.fill * Z.ret / 100
    return Z


ND = S.d.nunique()
PER = (("전체 412일(2025-03~11-12)", "20250301", "20261112"), ("2025-07~2026-10-08(안정기)", "20250701", "20261008"), ("새 날 10-09~11-12", "20261009", "20261112"))
V = (("지금 판", None), ("장후 +2%↑ 빼기", 2.0), ("**장후 +1.5%↑ 빼기**", 1.5), ("장후 +1%↑ 빼기", 1.0), ("장후 +0.5%↑ 빼기", 0.5))
for pn, a, b in PER:
    days = S[(S.d >= a) & (S.d <= b)].d.unique(); nd = len(days); months = len(set(d[:6] for d in days))
    P("\n## %s · 거래일 %d일\n" % (pn, nd))
    P("| 판 | 건수(하루) | 건당 연구 기준 | 승률 | 건당 체결 손해 뒤 | 승률(손해 뒤) | 수익금 합 | 달 평균 | 연 환산 | 최악의 날 | 최악의 달 | 플러스 달 | 하루 최대 투입 |")
    P("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for nm, ah in V:
        Z = rule(ah); Z = Z[(Z.d >= a) & (Z.d <= b)]
        if not len(Z): P("| %s | 0 | | | | | | | | | | | |" % nm); continue
        dd = Z.groupby("d").pnl.sum(); mm = dd.groupby(dd.index.str[:6]).sum().reindex(sorted(set(d[:6] for d in days)), fill_value=0)
        P("| %s | %d (%.2f) | %+.2f%% | %.0f%% | %+.2f%% | %.0f%% | %+.0f만 | %+.0f만 | %+.0f만 | %+.0f만 | %+.0f만 | %d/%d | %.0f만 |" % (
            nm, len(Z), len(Z) / nd, Z.r_vwhs.mean(), (Z.r_vwhs > 0).mean() * 100, Z.ret.mean(), (Z.ret > 0).mean() * 100, Z.pnl.sum() / 1e4,
            mm.mean() / 1e4, Z.pnl.sum() / nd * 250 / 1e4, dd.min() / 1e4, mm.min() / 1e4, int((mm > 0).sum()), len(mm), Z.groupby("d").fill.sum().max() / 1e4))
Z0, Z1 = rule(None), rule(1.0)
out = Z0[~Z0.set_index(["t", "d"]).index.isin(Z1.set_index(["t", "d"]).index)]
P("\n장후 +1%%↑ 빼기로 빠지는 거래(전체): %d건 · 건당 손해 뒤 %+.2f%% · 승률 %.0f%% · 수익금 %+.0f만" % (len(out), out.ret.mean(), (out.ret > 0).mean() * 100, out.pnl.sum() / 1e4))
new_in = Z1[~Z1.set_index(["t", "d"]).index.isin(Z0.set_index(["t", "d"]).index)]
P("새로 들어오는 거래(빈 순위 자리 대신 — 순위는 그대로라 0이어야 정상): %d건" % len(new_in))
(ROOT / "reports" / "t5_money_1114.md").write_text("# [장전 되돌림] 장후 필터 돈 계산 (11-14)\n" + "\n".join(OUT), encoding="utf-8")
