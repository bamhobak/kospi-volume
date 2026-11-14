# -*- coding: utf-8 -*-
"""2026-11-15 사용자 "장후 낙폭 다시 재주고 · 장후 낙폭 그리고 체결 손해 줄일 수 있는 방법 있을까?"
① 다시 재기: 옛 연구 패널(nxt_full0_panel)은 장후 1분봉을 '20:00 통합 종가가 -0.7%↓ 빠진 날'만 받아 만들었다(nxt_wide.py 97줄)
   → 19:50 에 빠졌다가 20:00 전에 돌아온 종목이 빠짐(고르는 데 20:00 정보 = 미래). 11-15 밤 과거 받기 끝난 NXT 전 종목·전 날
   장후 1분봉(research/cache/bf_nxt_ah, 4,271만 봉)으로 같은 정의 패널을 새로 만들어 실전 규칙([장후 낙폭] T6: 19:50 KRX 종가 대비 -2.5%↓ ·
   낮 ±1% 빼기 · 금액 = min(상한, 19:41~50 거래대금 10%) ≥ 30만 · 깊은 순 · 하루 40종목)으로 다시 잰다.
② 체결 손해 줄이기 — 같은 패널에서:
   S1 팔기 나누기: 다음 날 NXT 장전(08:00~08:50, bf_nxt_pre) VWAP 에 일부 팔고 나머지 KRX 시가 (거래대금 비례로 나누면 √충격 합이 가장 작다)
   S2 사기 늘리기: 19:45 에 고르고 19:46~20:00 15분 VWAP 로 산다(거래대금 1.5배)
   S3 종목당 비율 k: 5·10·15%
   S4 실전 그림자 호가 기록(data/nxt/log.csv)으로 사는 쪽 √충격 모형이 맞는지
손익 = 사는 VWAP → 다음 날 KRX 시가 − 0.23 − 사고·파는 √충격(-0.25+2.40√p).
    python research/memguard.py research/t6_full_1115.py → research/reports/t6_full_1115.md"""
import sys, glob, time
from pathlib import Path
import numpy as np, pandas as pd
sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
OUT = []; P = lambda s="": (OUT.append(str(s)), print(s, flush=True))
CK = 0.23; t0 = time.time()


def impact(won, a):
    p = np.clip(won / np.where(a > 0, a, np.nan), 0, None)
    return np.nan_to_num(np.maximum(0, -0.25 + 2.40 * np.sqrt(p)), nan=5.0)


def agg_ah(f):
    b = pd.read_parquet(f, columns=["t", "d", "hm", "o", "c", "h", "v"]) if isinstance(f, str) else f
    b = b.assign(t=b.t.astype(str), d=b.d.astype(str), hm=b.hm.astype(float).astype(int))
    if "o" not in b.columns: b = b.assign(o=b.c)
    b = b[b.hm >= 1641].sort_values(["t", "d", "hm"]); b["val"] = b.c * b.v
    k = ["t", "d"]; g = b.groupby(k, sort=False)
    R = pd.DataFrame({"tc": g.c.last(), "p_first": g.o.first()})
    R["p50"] = b[b.hm <= 1950].groupby(k).c.last(); R["p45"] = b[b.hm <= 1945].groupby(k).c.last()
    R["v41"] = b[(b.hm >= 1941) & (b.hm <= 1950)].groupby(k).val.sum()
    R["v31"] = b[(b.hm >= 1931) & (b.hm <= 1945)].groupby(k).val.sum()
    L = b[b.hm >= 1951]; gl = L.groupby(k)
    R["a10"] = gl.val.sum(); R["vw"] = R.a10 / gl.v.sum().replace(0, np.nan); R["hi"] = L[L.v > 0].groupby(k).h.max()
    L2 = b[b.hm >= 1946]; g2 = L2.groupby(k)
    R["a15"] = g2.val.sum(); R["vw15"] = R.a15 / g2.v.sum().replace(0, np.nan)
    return R


def agg_pre(f):
    b = pd.read_parquet(f, columns=["t", "d", "hm", "c", "v"])
    b = b[(b.hm >= 800) & (b.hm <= 850)].copy(); b["val"] = b.c * b.v
    k = ["t", "d"]; g = b.groupby(k)
    R = pd.DataFrame({"pval": g.val.sum()}); R["pvw"] = R.pval / g.v.sum().replace(0, np.nan)
    L = b[b.hm >= 841]; gl = L.groupby(k); R["pval41"] = gl.val.sum(); R["pvw41"] = R.pval41 / gl.v.sum().replace(0, np.nan)
    return R


# 밤 과거 받기(bf_nxt_ah)는 옛 캐시(ah_m1)에 이미 있던 종목·날은 건너뛰고 빈 날만 받았다 → 둘을 합쳐야 전 종목·전 날
_old = pd.read_parquet(ROOT / "cache" / "ah_m1.parquet")
AH_old = agg_ah(_old[[c for c in ("t", "d", "hm", "o", "c", "h", "v") if c in _old.columns]]); n_old = len(AH_old); del _old
AH = pd.concat([AH_old] + [agg_ah(f) for f in sorted(glob.glob(str(ROOT / "cache" / "bf_nxt_ah" / "bars_*.parquet")))])
AH = AH[~AH.index.duplicated()].reset_index()
print("옛 캐시 %d + 밤 받기 = %d 종목·날" % (n_old, len(AH)), flush=True)
PRE = pd.concat([agg_pre(f) for f in sorted(glob.glob(str(ROOT / "cache" / "bf_nxt_pre" / "bars_*.parquet")))])
PRE = PRE[~PRE.index.duplicated()].reset_index().rename(columns={"d": "d1"})
print("장후 %d·장전 %d 종목·날 · %.1f분" % (len(AH), len(PRE), (time.time() - t0) / 60), flush=True)

D = pd.read_parquet(ROOT / "cache" / "m1_daysum.parquet", columns=["t", "d", "o", "c", "tv1"])
cal = sorted(D.d.unique()); nxt = dict(zip(cal, cal[1:])); prv = dict(zip(cal[1:], cal))
D = D[D.d >= "20250101"].sort_values(["t", "d"])
D["o1"] = D.groupby("t").o.shift(-1); D["d1n"] = D.groupby("t").d.shift(-1); D["tv1n"] = D.groupby("t").tv1.shift(-1)
D["c0"] = D.groupby("t").c.shift(1); D["d0"] = D.groupby("t").d.shift(1)
D = D[(D.d >= "20250301") & D.o1.notna() & (D.d1n == D.d.map(nxt))].copy()
D.loc[D.d0 != D.d.map(prv), "c0"] = np.nan
D["d1"] = D.d.map(nxt)
Z = D.merge(AH, on=["t", "d"], how="inner")
# 1분봉이 분할 전 가격인 종목(예 290650 -50%) — 장후 첫 봉이 KRX 종가와 20% 넘게 다르면 KRX 종가 단위로 맞춘다
_f = Z.c / Z.p_first; _bad = (_f - 1).abs() > 0.2
for col in ("p50", "p45", "tc", "vw", "hi", "vw15"): Z.loc[_bad, col] = Z.loc[_bad, col] * _f[_bad]
Z["fx_scale"] = np.where(_bad, _f, 1.0)
print("가격 단위 맞춤 %d 종목·날(%d 종목)" % (_bad.sum(), Z.loc[_bad, "t"].nunique()), flush=True)
Z["AH50"] = (Z.p50 / Z.c - 1) * 100; Z["AH45"] = (Z.p45 / Z.c - 1) * 100; Z["AHd"] = (Z.tc / Z.c - 1) * 100
Z["dayr"] = (Z.c / Z.c0 - 1) * 100
Z["g_vw"] = (Z.o1 / Z.vw - 1) * 100 - CK; Z["g_hi"] = (Z.o1 / Z.hi - 1) * 100 - CK; Z["g_15"] = (Z.o1 / Z.vw15 - 1) * 100 - CK
V0 = pd.read_pickle(r"C:\temp\kp\nxt_v0.pkl")
Z = Z.merge(V0, on=["t", "d1"], how="left")
chk = Z.dropna(subset=["v0", "tv1n"])
ratio = float((chk.tv1n / chk.v0).median()) if len(chk) else np.nan
cor = float(np.corrcoef(np.log1p(chk.v0), np.log1p(chk.tv1n))[0, 1]) if len(chk) > 10 else np.nan
Z["v0f"] = Z.v0.fillna(Z.tv1n / ratio if ratio == ratio and cor > 0.8 else Z.a10).fillna(Z.a10)
Z = Z.merge(PRE, on=["t", "d1"], how="left")
Z["pvw"] = Z.pvw * Z.fx_scale; Z["pvw41"] = Z.pvw41 * Z.fx_scale
Z["g_pre"] = (Z.pvw / Z.vw - 1) * 100 - CK; Z["g_pre41"] = (Z.pvw41 / Z.vw - 1) * 100 - CK
HALF = set(pd.read_parquet(ROOT / "cache" / "toss_kr_1d_wide.parquet", columns=["t"]).t.astype(str).unique())
Z["half"] = Z.t.isin(HALF); Z["m"] = Z.d.str[:6]
Z = Z.dropna(subset=["g_vw", "a10"])
print("패널 %d행 · v0 대신 첫 1분(tv1) 비율 %.2f 상관 %.2f · %.1f분" % (len(Z), ratio, cor, (time.time() - t0) / 60), flush=True)

OLD = pd.read_pickle(r"C:\temp\kp\nxt_full0_panel.pkl")
OLD["d1"] = OLD.d.map(nxt); OLD = OLD.merge(V0, on=["t", "d1"], how="left"); OLD["v0f"] = OLD.v0.fillna(OLD.a10); OLD["v41"] = OLD.v41.fillna(0)
OLD["half"] = True


def rule(z, ah="AH50", th=-2.5, w=1.0, v="v41"):
    return z[(z[ah] <= th) & ~((z.dayr.abs() <= w).fillna(False)) & (0.10 * z[v] >= 30e4)]


YR = lambda z: [("2025", z[z.d < "20260101"]), ("2026", z[z.d >= "20260101"])]


def per_trade(z, px="g_vw", buy="a10"):
    r = z[px] - impact(100e4, z[buy].values) - impact(100e4, z.v0f.values)
    return r


def acct(z, Cap, cap, k=0.10, px="g_vw", buy="a10", v="v41", sell="open", maxn=40):
    """깊은 순으로 계좌가 찰 때까지 · 종목당 min(cap, k×v) — 날마다 손익(원)"""
    ah = "AH45" if v == "v31" else "AH50"
    z = z.sort_values(["d", ah]).copy()
    z["rk"] = z.groupby("d").cumcount(); z = z[z.rk < maxn]
    amt = np.minimum(cap, k * z[v].values); amt = np.where(amt >= 30e4, amt, 0)
    cum = pd.Series(amt, index=z.index).groupby(z.d.values).cumsum().values
    amt = np.clip(Cap - (cum - amt), 0, amt); amt = np.where(amt >= 30e4, amt, 0)
    ok = amt > 0; z = z[ok]; amt = amt[ok]
    bi = impact(amt, z[buy].values)
    if sell == "open":
        r = z[px].values - bi - impact(amt, z.v0f.values); si = impact(amt, z.v0f.values)
    else:                                                  # 장전 VWAP + 시가 나누기(거래대금 비례)
        pv = z.pval.fillna(0).values if sell == "split" else z.pval41.fillna(0).values
        gp = (z.g_pre if sell == "split" else z.g_pre41).values
        f = np.where(pv > 0, pv / (pv + z.v0f.values), 0); f = np.where(np.isnan(gp), 0, f)
        si = f * impact(amt * f, pv) + (1 - f) * impact(amt * (1 - f), z.v0f.values)
        r = f * np.nan_to_num(gp) + (1 - f) * z[px].values - bi - si
    pnl = pd.Series(amt * r / 100, index=z.index)
    dp = pnl.groupby(z.d.values).sum(); mp = pnl.groupby(z.m.values).sum()
    return dict(n=len(z), inv=amt.sum(), pnl=pnl.sum(), m25=mp[mp.index < "202601"].mean(), m26=mp[mp.index >= "202601"].mean(),
                pos=(mp > 0).sum(), nm=len(mp), worst=dp.min(), bi=float(np.sum(amt * bi / 100)), si=float(np.sum(amt * si / 100)),
                ret=float(np.sum(amt * r) / amt.sum()) if amt.sum() else 0)


P("# [장후 낙폭] 다시 재기 + 체결 손해 줄이기 (2026-11-15)\n")
P("- 새 패널: NXT 전 종목 장후 1분봉 %d 종목·날(%s~%s) · 옛 패널: 20:00 통합 종가 -0.7%%↓ 날만 받은 %d행" % (len(Z), Z.d.min(), Z.d.max(), len(OLD)))
P("- 실전 규칙: 19:50 KRX 종가 대비 -2.5%%↓ · 낮 ±1%% 빼기 · 19:41~50 거래대금 10%% ≥ 30만 · 사는 VWAP 19:51~20:00 · 다음 날 KRX 시가 · 비용 0.23 + 사고·파는 √충격")
P("- 다음 날 시가 첫 1분 거래대금: 옛 캐시(nxt_v0) 없는 건 m1 요약 첫 1분 거래대금(비율 %.2f·상관 %.2f) 으로 대신\n" % (ratio, cor))

P("## ① 다시 재기 — 한 건 100만 (사고·파는 충격 뒤)\n")
P("| 패널 | 해 | 달 평균 건수 | 건당 평균 | 중앙 | 승률 | 최고가 매수 건당 |"); P("|---|---|---|---|---|---|---|")
Zn = rule(Z); Zh = Zn[Zn.half]; Zo = rule(OLD)
for nm, z in (("옛 패널(20:00 -0.7%↓ 날만)", Zo), ("새 · 시총 상위 절반(실전 대상)", Zh), ("새 · NXT 전 종목", Zn)):
    for y, q in YR(z):
        if not len(q): continue
        r = per_trade(q); rh = q.g_hi - impact(100e4, q.a10.values) - impact(100e4, q.v0f.values)
        P("| %s | %s | %.0f | %+.2f%% | %+.2f%% | %.0f%% | %+.2f%% |" % (nm, y, len(q) / q.m.nunique(), r.mean(), r.median(), (r > 0).mean() * 100, rh.mean()))
key = lambda z: set(zip(z.t, z.d))
ko, kh = key(Zo[Zo.d <= Zh.d.max()]), key(Zh)
miss = Zh[[k_ not in ko for k_ in zip(Zh.t, Zh.d)]]
P("\n- 같은 기간 실전 대상 신호 %d건 중 옛 패널에 없던 것 **%d건(%.0f%%)** — 이 건들 한 건 100만 건당 %+.2f%%·승률 %.0f%% (20:00 통합 종가 등락 중앙 %+.2f%%) / 옛 패널에도 있던 것 %+.2f%%" % (
    len(Zh), len(miss), len(miss) / max(1, len(Zh)) * 100, per_trade(miss).mean(), (per_trade(miss) > 0).mean() * 100, miss.AHd.median(),
    per_trade(Zh[[k_ in ko for k_ in zip(Zh.t, Zh.d)]]).mean()))
P("- 옛 패널에만 있고 새 패널엔 없는 것 %d건(받기 빈칸 또는 정의 차이)\n" % len(ko - key(Zn)))

P("## ① 계좌 — 실전 5천만(종목당 500만) · 큰 판 1억(종목당 1,500만) · 금액 = min(상한, 19:41~50 거래대금 10%)\n")
P("| 패널 | 판 | 건수 | 달 평균 2025 / 2026 | 합계 | 플러스 달 | 최악의 날 | 투입 대비 건당 | 사는 충격 / 파는 충격 |"); P("|---|---|---|---|---|---|---|---|---|")
for nm, z in (("옛 패널", Zo), ("새 · 상위 절반", Zh), ("새 · 전 종목", Zn)):
    for lab, Cap, cap in (("실전 5천만", 5e7, 500e4), ("큰 판 1억", 1e8, 1500e4)):
        a = acct(z, Cap, cap)
        P("| %s | %s | %d | %+.0f / %+.0f만 | %+.0f만 | %d/%d | %+.0f만 | %+.2f%% | %.0f / %.0f만 |" % (nm, lab, a["n"], a["m25"] / 1e4, a["m26"] / 1e4, a["pnl"] / 1e4, a["pos"], a["nm"], a["worst"] / 1e4, a["ret"], a["bi"] / 1e4, a["si"] / 1e4))

P("\n## ② 체결 손해 줄이기 — 새 패널 · 상위 절반 · 큰 판 1억(종목당 1,500만)\n")
P("| 방법 | 건수 | 달 평균 2025 / 2026 | 합계 | 플러스 달 | 최악의 날 | 투입 대비 건당 | 사는 충격 / 파는 충격 |"); P("|---|---|---|---|---|---|---|---|")
Zh45 = rule(Z[Z.half], ah="AH45", v="v31")
for lab, z, kw in (("기준: 19:51~20:00 사기 · 시가에 다 팔기", Zh, {}),
                   ("S1 팔기 나누기: 장전 08:00~08:50 VWAP + 시가(거래대금 비례)", Zh, dict(sell="split")),
                   ("S1' 팔기 나누기: 장전 08:41~08:50 VWAP + 시가", Zh, dict(sell="split41")),
                   ("S2 19:45 고르고 19:46~20:00 15분 사기", Zh45, dict(px="g_15", buy="a15", v="v31", k=0.10 * 10 / 15)),
                   ("S2+S1 둘 다", Zh45, dict(px="g_15", buy="a15", v="v31", k=0.10 * 10 / 15, sell="split")),
                   ("S3 종목당 거래대금 5%", Zh, dict(k=0.05)),
                   ("S3 종목당 거래대금 15%", Zh, dict(k=0.15)),
                   ("S3 종목당 거래대금 20%", Zh, dict(k=0.20))):
    a = acct(z, 1e8, 1500e4, **kw)
    P("| %s | %d | %+.0f / %+.0f만 | %+.0f만 | %d/%d | %+.0f만 | %+.2f%% | %.0f / %.0f만 |" % (lab, a["n"], a["m25"] / 1e4, a["m26"] / 1e4, a["pnl"] / 1e4, a["pos"], a["nm"], a["worst"] / 1e4, a["ret"], a["bi"] / 1e4, a["si"] / 1e4))
P("\n- 같은 표 실전 5천만(종목당 500만):\n")
P("| 방법 | 합계 | 달 평균 2025 / 2026 | 사는 충격 / 파는 충격 |"); P("|---|---|---|---|")
for lab, z, kw in (("기준", Zh, {}), ("S1 장전+시가 나누기", Zh, dict(sell="split")), ("S2 15분 사기", Zh45, dict(px="g_15", buy="a15", v="v31", k=0.10 * 10 / 15)),
                   ("S2+S1", Zh45, dict(px="g_15", buy="a15", v="v31", k=0.10 * 10 / 15, sell="split"))):
    a = acct(z, 5e7, 500e4, **kw)
    P("| %s | %+.0f만 | %+.0f / %+.0f만 | %.0f / %.0f만 |" % (lab, a["pnl"] / 1e4, a["m25"] / 1e4, a["m26"] / 1e4, a["bi"] / 1e4, a["si"] / 1e4))
q = Zh.dropna(subset=["g_pre"])
P("\n- 참고(충격 없이 건당): 시가에 팔기 %+.2f%% · 장전 08:00~50 VWAP 에 팔기 %+.2f%% · 08:41~50 %+.2f%% (장전 체결 있는 %d건) · 장전 거래대금 중앙 %.1f억 vs 시가 첫 1분 %.1f억" % (
    q.g_vw.mean(), q.g_pre.mean(), q.g_pre41.mean(), len(q), q.pval.median() / 1e8, q.v0f.median() / 1e8))

P("\n## ② S4 실전 그림자 호가로 사는 충격 모형 확인 (data/nxt/log.csv, 19:50 매도 호가 10단계를 타고 산 평균 단가)\n")
L = pd.read_csv(BASE / "data" / "nxt" / "log.csv")
rows = []
for sz in (100, 300, 500, 1000):
    c = "r_%d만" % sz
    x = L[["r_ask", c, "val1951_2000", "v1941_50"]].copy(); x[c] = pd.to_numeric(x[c], errors="coerce"); x = x.dropna(subset=["r_ask", c])
    if not len(x): continue
    real = (x.r_ask - x[c]); a = x.val1951_2000.fillna(x.v1941_50)
    model = impact(sz * 1e4, a.values)
    rows.append((sz, len(x), real.median(), real.mean(), np.nanmedian(model), np.nanmean(model), (L[c] == "벽부족").mean() * 100))
P("| 한 종목 금액 | 건수 | 실제 호가 타고 산 추가 비용 중앙 / 평균 | 모형(√충격) 중앙 / 평균 | 호가 10단계 모자람 |"); P("|---|---|---|---|---|")
for sz, n, rm, ra, mm, ma, wl in rows:
    P("| %d만 | %d | %.2f / %.2f%%p | %.2f / %.2f%%p | %.0f%% |" % (sz, n, rm, ra, mm, ma, wl))
(ROOT / "reports" / "t6_full_1115.md").write_text("\n".join(OUT), encoding="utf-8")
Z.to_pickle(r"C:\temp\kp\t6_full_panel_1115.pkl")
print("끝 %.1f분" % ((time.time() - t0) / 60))
