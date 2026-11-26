# -*- coding: utf-8 -*-
"""2026-11-26 [장후 낙폭] — 나스닥 선물보다 더 빠진 종목만 사면(H0438). 사용자 "장후 낙폭이랑 나스닥 선물지수랑 수치 비교해서 더 빠진 것만 사는 거 … 수익률이랑 승률 수익 조정할 수 있는지"
  바탕 = 지금 실전 조건(11-05): 장후 등락(19:50 ÷ KRX 종가) ≤ -2.5% · 낮 등락 ±1% 안이면 뺌 · 깊은 순 계좌 3천만 · 종목당 min(500만, 19:41~50 거래대금 10%) · 30만 미만 안 삼
  패널 = C:/temp/kp/nxt_full0_panel.pkl(2025-03~2026-10). 손익 = 19:51~20:00 VWAP 매수 → 다음 날 KRX 시가 - 0.23 - 사고·파는 √충격. (nxt_deep_1125 와 같은 틀)
  선물 = 야후 NQ=F 1시간 봉(C:/temp/kp/nq_1h_1126.json). 살 때(19:51) 아는 값만 — 19:00 KST 봉 시가까지.
    nq_ah  = 19:00 KST ÷ 15:00 KST - 1 (한국 장후 시간 동안의 선물 움직임)        nq_ah16 = 19:00 ÷ 16:00
    nq_chg = 19:00 KST ÷ 앞선 미국장 15시대(ET) 봉 종가 - 1 (앱의 '선물 등락률')
  말한 그대로 = 지금 조건 가운데 (장후 등락 - 선물) 이 문턱보다 깊은 것만 산다
  변형 = ① 선물 몫을 0.37배(장후 시장 평균이 선물을 따라가는 기울기)만 뺌 ② 선물 등락률 대비 ③ 아예 조건을 '선물 대비 -2.5%↓'로 바꿈(선물 오른 날 덜 빠진 종목도 들어옴)
         ④ 선물 방향으로 날 거르기 ⑤ 선물 방향으로 그날 한도 절반
    python research/memguard.py research/nxt_nqrel_1126.py → research/reports/nxt_nqrel_1126.md
  11-05 nxt_nq_1105 는 옛 조건(시장 대비 -2·-3)·건당만. H0433 은 19:50 야간 선물·QQQ 로 '쉬기'(기각)."""
import sys, json
from pathlib import Path
import numpy as np, pandas as pd
sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent
OUT = []; P = lambda s="": (OUT.append(str(s)), print(s, flush=True))


def impact(won, a):
    p = np.clip(won / np.where(a > 0, a, np.nan), 0, None)
    return np.maximum(0, -0.25 + 2.40 * np.sqrt(p))


# ── 선물 ──
J = json.load(open(r"C:\temp\kp\nq_1h_1126.json", encoding="utf-8"))["chart"]["result"][0]
q = J["indicators"]["quote"][0]
N = pd.DataFrame({"o": q["open"], "c": q["close"]}, index=pd.to_datetime(J["timestamp"], unit="s", utc=True)).dropna()
N = N[~N.index.duplicated()]
et = N.index.tz_convert("America/New_York")
settle = N.c[et.hour == 15]; settle.index = et[et.hour == 15].strftime("%Y%m%d"); settle = settle.groupby(level=0).last()
sd = settle.index.values


def at(ts):
    i = N.index.searchsorted(ts)
    return N.o.iloc[i] if i < len(N) and 0 <= (N.index[i] - ts).total_seconds() <= 1800 else np.nan


def feats(days):
    rows = []
    for d in days:
        p19, p15, p16 = (at(pd.Timestamp(d + h, tz="UTC")) for h in (" 10:00", " 06:00", " 07:00"))
        prev = sd[sd < d]
        rows.append((d, (p19 / p15 - 1) * 100, (p19 / p16 - 1) * 100, (p19 / settle[prev[-1]] - 1) * 100 if len(prev) else np.nan))
    return pd.DataFrame(rows, columns=["d", "nq_ah", "nq_ah16", "nq_chg"])


Z = pd.read_pickle(r"C:\temp\kp\nxt_full0_panel.pkl")
cal = sorted(pd.read_parquet(ROOT / "cache/m1_daysum.parquet", columns=["d"]).d.unique()); nx = dict(zip(cal, cal[1:]))
Z["d1"] = Z.d.map(nx)
Z = Z.merge(pd.read_pickle(r"C:\temp\kp\nxt_v0.pkl"), on=["t", "d1"], how="left")
Z["v0f"] = Z.v0.fillna(Z.a10); Z["v41"] = Z.v41.fillna(0)
A = 100e4
Z["r"] = Z.g_vw - impact(A, Z.a10.values) - impact(A, Z.v0f.values)
Z = Z.merge(feats(sorted(Z.d.unique())), on="d", how="left")
alld = Z.d.nunique(); nqd = Z.d[Z.nq_ah.notna()].nunique()
Z["x1"] = Z.AH50 - Z.nq_ah                 # 선물(장후 시간)보다 더 빠진 몫
Z["x37"] = Z.AH50 - 0.37 * Z.nq_ah         # 선물 몫을 0.37배만
Z["xc"] = Z.AH50 - Z.nq_chg                # 선물 등락률 대비
Z["x16"] = Z.AH50 - Z.nq_ah16
mid = (Z.dayr.abs() <= 1.0).fillna(False)
B_all = Z[(Z.AH50 <= -2.5) & ~mid]
U = Z[~mid & Z.nq_ah.notna() & Z.nq_chg.notna()].copy(); U["L"] = U.d < "20260101"
B = U[U.AH50 <= -2.5].copy()
LM = Z.m[Z.d < "20260101"].nunique(); VM = Z.m[Z.d >= "20260101"].nunique()
P("# [장후 낙폭] 나스닥 선물보다 더 빠진 종목만 사기 (2026-11-26, H0438)\n")
P("- 바탕: 지금 실전 조건 %d건(선물 값 없는 날 빼기 전 %d건) · %s~%s · %d일 · 학습(2025) %d달 / 검증(2026) %d달 · 선물 있는 날 %d/%d" % (len(B), len(B_all), B.d.min(), B.d.max(), B.d.nunique(), LM, VM, nqd, alld))
P("- 패널에 든 종목의 장후 등락 범위: 가장 얕은 값 %+.2f%% (조건을 바꾸는 판은 이 범위 안에서만 새 종목이 들어온다)" % Z.AH50.max())
P("- 한 건 100만 기준 건당(비용·충격 뒤) 학습 %+.2f%% / 검증 %+.2f%% · 이긴 비율 %.0f%% / %.0f%%" % (B.r[B.L].mean(), B.r[~B.L].mean(), (B.r[B.L] > 0).mean() * 100, (B.r[~B.L] > 0).mean() * 100))
dd = B.groupby("d").agg(r=("r", "mean"), nq_ah=("nq_ah", "first"), nq_chg=("nq_chg", "first"), n=("t", "size"))
P("- 날 바구니 성적 × 선물 상관: 장후 시간 선물 %+.2f · 선물 등락률 %+.2f / 건별 성적 × (장후 등락 - 선물) 상관 %+.2f · × 장후 등락 %+.2f" % (dd.r.corr(dd.nq_ah), dd.r.corr(dd.nq_chg), B.r.corr(B.x1), B.r.corr(B.AH50)))
P("- 걸린 건수가 몰리는 곳: 장후 시간 선물 -0.5%%↓ 날 %d건(%.0f%%) · ±0.5%% 안 %d건 · +0.5%%↑ 날 %d건" % ((B.nq_ah <= -0.5).sum(), (B.nq_ah <= -0.5).mean() * 100, (B.nq_ah.abs() < 0.5).sum(), (B.nq_ah >= 0.5).sum()))


def acct(z, Cap=3000e4, cap=500e4, k=0.10, px="g_vw"):
    z = z.sort_values(["d", "AH50"])
    Capv = z.capd.values if "capd" in z.columns else Cap
    amt = np.full(len(z), cap, float)
    if k: amt = np.minimum(amt, k * z.v41.values)
    amt = np.where(amt >= 30e4, amt, 0)
    cum = pd.Series(amt, index=z.index).groupby(z.d.values).cumsum().values
    amt = np.clip(Capv - (cum - amt), 0, amt)
    ok = amt >= 30e4; z = z[ok]; amt = amt[ok]
    r = z[px].values - impact(amt, z.a10.values) - impact(amt, z.v0f.values)
    pnl = pd.Series(r / 100 * amt / 1e4, index=z.index)
    pm = pnl.groupby(z.m.values).sum(); dp = pnl.groupby(z.d.values).sum()
    return dict(L=pnl[z.d < "20260101"].sum() / LM, V=pnl[z.d >= "20260101"].sum() / VM, tot=pnl.sum(), pm=(pm > 0).sum(), nm=len(pm), worst=dp.min() if len(dp) else 0, n=len(z), pnl=pnl, dp=dp,
                used=amt.sum() / 1e4 / z.d.nunique() if len(z) else 0, win=(pnl > 0).mean() * 100 if len(z) else 0, dwin=(dp > 0).mean() * 100 if len(dp) else 0, ret=pnl.sum() / (amt.sum() / 1e4) * 100 if len(z) else 0)


rng = np.random.default_rng(7)
def ci_diff(a, b):
    """빠진 건 건당 - 남은 건 건당, 달 묶음 부트스트랩 95%"""
    ms = sorted(set(a.m) | set(b.m)); out = []
    ga = a.groupby("m").r.agg(["sum", "count"]).reindex(ms).fillna(0).values; gb = b.groupby("m").r.agg(["sum", "count"]).reindex(ms).fillna(0).values
    for _ in range(2000):
        k = rng.integers(0, len(ms), len(ms)); sa = ga[k].sum(0); sb = gb[k].sum(0)
        if sa[1] and sb[1]: out.append(sa[0] / sa[1] - sb[0] / sb[1])
    return (np.percentile(out, 2.5), np.percentile(out, 97.5)) if out else (np.nan, np.nan)


def bands(title, col, EDG, src=None):
    src = B if src is None else src
    P("\n## %s (한 건 100만 기준)\n" % title)
    P("| 구간 | 날 수 | 건 학/검 | 건당 학습 | 건당 검증 | 이긴 비율 학/검 | 날 바구니 평균 | 가장 나쁜 날 바구니 | -5%↓ 건 비율 |"); P("|---|---|---|---|---|---|---|---|---|")
    for a, b in zip(EDG, EDG[1:]):
        g = src[(src[col] > a) & (src[col] <= b)]; l, v = g[g.L], g[~g.L]
        lab = "%+g%%↓" % b if a == -99 else "%+g%%↑" % a if b == 99 else "%+g ~ %+g%%" % (a, b)
        f = lambda s: "%+.2f%%" % s.r.mean() if len(s) else "-"
        w = lambda s: "%.0f%%" % ((s.r > 0).mean() * 100) if len(s) else "-"
        db = g.groupby("d").r.mean()
        P("| %s | %d | %d / %d | %s | %s | %s / %s | %s | %s | %s |" % (lab, g.d.nunique(), len(l), len(v), f(l), f(v), w(l), w(v), "%+.2f%%" % db.mean() if len(db) else "-", "%+.2f%%" % db.min() if len(db) else "-", "%.0f%%" % ((g.r <= -5).mean() * 100) if len(g) else "-"))


bands("1) 지금 조건 건을 장후 시간 선물(15→19시) 구간별로", "nq_ah", [-99, -1, -0.5, -0.2, 0.2, 0.5, 99])
bands("2) 지금 조건 건을 선물 등락률(앞선 미국장 종가→19시) 구간별로", "nq_chg", [-99, -2, -1, -0.3, 0.3, 1, 99])
bands("3) 지금 조건 건을 '장후 등락 - 선물(장후 시간)' 구간별로 — 선물보다 얼마나 더 빠졌나", "x1", [-99, -10, -7, -5, -4, -3, -2.5, -2, 99])
bands("3-1) 선물이 내린 날(장후 시간 선물 -0.3%↓)만 — '장후 등락 - 선물' 구간별", "x1", [-99, -7, -5, -4, -3, -2.5, -2, 99], B[B.nq_ah <= -0.3])

b0 = acct(B); h0 = acct(B, px="g_hi")
w5 = lambda a: a["dp"].nsmallest(5).sum()
HDR = ("| 판 | 사는 건(지금 대비) | 건당 학/검 | 이긴 비율 학/검 | 빠진-남은 95% 구간 | 계좌 20달 합계(만) | 지금 대비 | 월 학/검(만) | 넣은 돈 대비 | 이긴 건·이긴 날 | 플러스 달 | 최악의 날(만) | 나쁜 날 5개 합(만) | 나아진 달/못한 달 | 최고가 매수 합계(지금 대비) |\n"
       "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
cells = 0
def line(lab, K, count=True):
    global cells
    if count: cells += 1
    a = acct(K); h = acct(K, px="g_hi")
    X = B.loc[B.index.difference(K.index)]
    lo, hi = ci_diff(X, K) if len(X) > 10 and len(K) > 10 else (np.nan, np.nan)
    pa = a["pnl"].groupby(K.loc[a["pnl"].index, "m"]).sum(); pb = b0["pnl"].groupby(B.loc[b0["pnl"].index, "m"]).sum()
    d = (pa.reindex(pb.index).fillna(0) - pb)
    f = lambda s: "%+.2f" % s.r.mean() if len(s) else "-"
    w = lambda s: "%.0f%%" % ((s.r > 0).mean() * 100) if len(s) else "-"
    P("| %s | %d (%+d) | %s / %s | %s / %s | %s | %+.0f | %+.0f | %+.0f / %+.0f | %+.2f%% | %.0f%% · %.0f%% | %d/%d | %+.0f | %+.0f | %d / %d | %+.0f (%+.0f) |" % (
        lab, len(K), len(K) - len(B), f(K[K.L]), f(K[~K.L]), w(K[K.L]), w(K[~K.L]), "-" if np.isnan(lo) else "%+.2f~%+.2f" % (lo, hi), a["tot"], a["tot"] - b0["tot"], a["L"], a["V"], a["ret"], a["win"], a["dwin"],
        a["pm"], a["nm"], a["worst"], w5(a), (d > 0.5).sum(), (d < -0.5).sum(), h["tot"], h["tot"] - h0["tot"]))

def head(t): P("\n## %s\n" % t); P(HDR); line("지금(그냥 장후 -2.5%↓)", B, count=False)

head("4) 말한 그대로 — 지금 조건 가운데 선물(장후 시간)보다 더 빠진 것만 (계좌 3천만 · 깊은 순)")
for th in (-2.0, -2.5, -3.0, -3.5, -4.0):
    line("장후 등락 - 선물 ≤ %g%%" % th, B[B.x1 <= th])
head("4-1) 대조 — 선물을 안 보고 그냥 장후 등락 문턱만 더 깊게 (4)와 같은 건수가 되도록)")
for th in (-2.5, -3.0, -3.5, -4.0):
    n_ = int((B.x1 <= th).sum()); thq = B.AH50.sort_values().iloc[n_ - 1]
    line("그냥 장후 등락 ≤ %.2f%%(선물 대비 %g%% 와 같은 건수)" % (thq, th), B[B.AH50 <= thq])
head("5) 변형 — 선물 재는 법 바꾸기 (지금 조건 가운데서 고름)")
for th in (-2.5, -3.0):
    line("선물 몫 0.37배만 빼고 ≤ %g%%" % th, B[B.x37 <= th])
for th in (-2.5, -3.0, -4.0):
    line("선물 등락률 대비 ≤ %g%%" % th, B[B.xc <= th])
for th in (-2.5, -3.0):
    line("16→19시 선물 대비 ≤ %g%%" % th, B[B.x16 <= th])
head("6) 변형 — 조건 자체를 '선물 대비'로 바꿈 (선물이 오른 날엔 덜 빠진 종목도 산다)")
for col, nm in (("x1", "장후 시간 선물 대비"), ("x37", "선물 몫 0.37배 대비"), ("xc", "선물 등락률 대비")):
    line("%s ≤ -2.5%%" % nm, U[U[col] <= -2.5])
    thq = U[col].sort_values().iloc[len(B) - 1]
    line("%s ≤ %.2f%%(지금과 같은 건수)" % (nm, thq), U[U[col] <= thq])
head("7) 변형 — 선물 방향으로 날 거르기 (그날은 안 삼)")
for lab, m in (("장후 시간 선물 +0.3%↑ 날 쉼", B.nq_ah >= 0.3), ("장후 시간 선물 +0.5%↑ 날 쉼", B.nq_ah >= 0.5), ("선물 등락률 +1%↑ 날 쉼", B.nq_chg >= 1), ("장후 시간 선물 -0.5%↓ 날 쉼", B.nq_ah <= -0.5),
               ("장후 시간 선물 -1%↓ 날 쉼", B.nq_ah <= -1), ("선물 등락률 -1%↓ 날 쉼", B.nq_chg <= -1), ("선물 등락률 -2%↓ 날 쉼", B.nq_chg <= -2)):
    line(lab, B[~m])
head("8) 변형 — 선물 방향으로 그날 한도만 절반(1,500만)")
for lab, m in (("장후 시간 선물 +0.5%↑ 날 절반", B.nq_ah >= 0.5), ("선물 등락률 +1%↑ 날 절반", B.nq_chg >= 1), ("장후 시간 선물 -0.5%↓ 날 절반", B.nq_ah <= -0.5), ("장후 시간 선물 -1%↓ 날 절반", B.nq_ah <= -1), ("선물 등락률 -1%↓ 날 절반", B.nq_chg <= -1)):
    K = B.copy(); K["capd"] = np.where(m, 1500e4, 3000e4); line(lab, K)

P("\n## 9) 계좌에서 가장 나빴던 날 8개 — 그날 선물\n")
P("| 날 | 그날 손익(만) | 산 종목 수 | 장후 시간 선물 | 선물 등락률 | 장후 시장 평균 | 선물보다 3%p↑ 더 빠진 종목 손익(만) | 그 밖 종목 손익(만) |"); P("|---|---|---|---|---|---|---|---|")
for d in b0["dp"].nsmallest(8).index:
    ix = [i for i in b0["pnl"].index if B.d[i] == d]; g = B.loc[ix]; p = b0["pnl"][ix]
    deep = (g.x1 <= -3).values
    P("| %s | %+.0f | %d | %+.2f%% | %+.2f%% | %+.2f%% | %+.0f | %+.0f |" % (d, p.sum(), len(ix), g.nq_ah.iloc[0], g.nq_chg.iloc[0], g.mkt.iloc[0], p[deep].sum(), p[~deep].sum()))
P("\n- 하루 평균 쓰는 돈(지금): %.0f만 · 계좌 손익은 깊은 순으로 3천만까지라, 뺀 자리는 다음 종목이 채운다" % b0["used"])
P("\n시험 칸 %d" % cells)
(ROOT / "reports" / "nxt_nqrel_1126.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
