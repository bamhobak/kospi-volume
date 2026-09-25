# -*- coding: utf-8 -*-
"""[주봉 RSI<30](H0210) 미장 — **폐지 종목 포함 패널**로 다시 잰다 (2026-09-25).

외국 기법 141개 중 미장 1위였다(40일 중앙 +4.36 · 절삭 +1.97 · 10/11해 양수). 다만 run_spec 의 미장 패널(us_scan)은
현재 상장 종목만이라 폭락주를 사는 기법은 부풀려진다. 여기서는 us_full_2007.pkl(Tiingo 폐지 6,762종목 포함)로
  ① A 2009~15(판정에 안 쓴 과거) · B 2016~ 건별 성적 — 신호 나면 다 산다, 한 종목 보유 중 재신호 무시
  ② 같은 날 아무거나 산 중앙과의 차(40·60일 드리프트 착시 점검)
  ③ 폐지 종목 거래만 떼어 본 성적
  ④ 기존 미장 규칙(N1~N5, 폐지 포함판 us_surv_measure 정의)과 ±5일 겹침
주봉 RSI 근사 = 5일 종가 변화의 70일 와일더 평활 RSI (run_spec 명세와 같은 식).

    python research/wrsi_full.py
"""
import io, sys, contextlib, warnings
warnings.filterwarnings("ignore")
sys.argv = [sys.argv[0], "--panel", "us_full_2007.pkl", "--since", "20090101"]
from pathlib import Path
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(BASE))
with contextlib.redirect_stdout(io.StringIO()):
    import us_surv_measure as M
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd

K = M.K                                           # 주가 $3 이상 · 폐지 포함 · close=원주가
K["pxc"] = K.px if "px" in K.columns else K.close
g = K.groupby("ticker", sort=False)
c5 = g.pxc.shift(5)
u5, d5 = (K.pxc - c5).clip(lower=0), (c5 - K.pxc).clip(lower=0)
ew = lambda x: x.groupby(K.ticker, sort=False).transform(lambda s: s.ewm(alpha=1 / 70, adjust=False).mean())
K["rsiw"] = 100 * ew(u5) / (ew(u5) + ew(d5) + 1e-12)
uni = (K.amt20.groupby(K.date).rank(pct=True) >= 0.60).fillna(False)
prev = K.rsiw.groupby(K.ticker, sort=False).shift(1)
CONDS = {"원안 30 하향돌파": (K.rsiw < 30) & (prev >= 30), "<25 하향돌파": (K.rsiw < 25) & (prev >= 25),
         "<35 하향돌파": (K.rsiw < 35) & (prev >= 35)}


def dedup(cond, h):
    Z = K[(cond & uni).fillna(False)].dropna(subset=[f"n{h}"])
    Z = Z[Z.buy > 0].sort_values("di")
    keep, last = [], {}
    for t, i, ix in zip(Z.ticker.values, Z.di.values, Z.index):
        if last.get(t, -10 ** 9) >= i:
            continue
        last[t] = i + h; keep.append(ix)
    Z = Z.loc[keep].copy(); Z["r"] = Z[f"n{h}"].astype(float)
    return Z[Z.date >= "20090101"]


def st(z):
    if len(z) < 20:
        return "| %d | 표본 부족 | | | | |" % len(z)
    r = z.r; ys = z.groupby(z.date.str[:4]).r.median()
    return "| %s | %+.2f | %+.2f | %.0f%% | %d/%d | %+.2f |" % (f"{len(r):,}", r.median(), r[r <= r.quantile(0.95)].mean(),
                                                      (r > 0).mean() * 100, (ys > 0).sum(), len(ys), r.min())


BEN = {h: K[uni].dropna(subset=[f"n{h}"]).groupby("date")[f"n{h}"].median() for h in (20, 40, 60)}
print("\n## [주봉 RSI<30] 미장 — 폐지 포함 패널(us_full_2007) · 유동성 상위 40% · 익일 시가 · 비용 차감\n")
print("| 조건 | 보유 | 구간 | n | 중앙 | 절삭 | 승률 | 양수해 | 최악 | 같은날 아무거나 중앙 | 초과(중앙−기준) |")
print("|---|---|---|---|---|---|---|---|---|---|---|")
for nm, c in CONDS.items():
    for h in (20, 40, 60):
        Z = dedup(c, h)
        for lbl, z in (("A 2009~15", Z[Z.date <= "20151231"]), ("B 2016~", Z[Z.date >= "20160101"])):
            bm = z.date.map(BEN[h]).median() if len(z) else np.nan
            print("| %s | %d일 | %s %s %+.2f | %+.2f |" % (nm, h, lbl, st(z), bm, (z.r.median() - bm) if len(z) else np.nan))

Z = dedup(CONDS["원안 30 하향돌파"], 40)
dz, sz = Z[Z.grp == "폐지"], Z[Z.grp == "생존"]
print(f"\n원안 40일 — 폐지 종목 거래 {len(dz):,}건({len(dz) / max(len(Z), 1) * 100:.1f}%) 중앙 {dz.r.median():+.2f} · 생존 {sz.r.median():+.2f}")
print("연도별 중앙(40일): " + " · ".join(f"{y} {v:+.1f}({n})" for y, v, n in
                                     zip(*[list(x) for x in (Z.groupby(Z.date.str[:4]).r.median().index,
                                                             Z.groupby(Z.date.str[:4]).r.median().values,
                                                             Z.groupby(Z.date.str[:4]).size().values)])))

# ④ 기존 규칙 겹침(±5일)
C = M.rules(pd.Series(True, index=K.index), "u_all")
old = {}
for rid in ("N1", "N2", "N3", "N4", "N5"):
    O = M.dedup(C[rid], M.HOLD[rid])
    for t, i in zip(O.ticker.values, O.di.values):
        old.setdefault(t, []).append((i, rid))
hit, by = 0, {}
for t, i in zip(Z.ticker.values, Z.di.values):
    rs = {r for j, r in old.get(t, []) if abs(j - i) <= 5}
    if rs:
        hit += 1
        for r in rs:
            by[r] = by.get(r, 0) + 1
print(f"\n기존 미장 규칙과 ±5일 겹침: {hit / max(len(Z), 1) * 100:.0f}% · " + " ".join(f"{k} {v}" for k, v in sorted(by.items())))
