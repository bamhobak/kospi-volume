# -*- coding: utf-8 -*-
"""상승장 2호 마지막 칸 — '같은날 내부자 둘 이상이 샀다'.

앞 단계에서 금액 기준(100만$↑)은 **복권형으로 기각**됐다:
  상위 1%가 전체 수익의 43.0% · 상위 5%가 **107.3%** — 상위 5%를 빼면 나머지 합이 마이너스다.
  절삭평균 -0.17 · 스트레스(2006~15) -0.47 · 3/10. N1 의 약점을 그대로 복제한다.

예외가 한 칸 있었다 — **같은날 신고 2건 이상**(서로 다른 내부자 둘 이상이 같은 날 매수):
  승률 59.0% · 중앙 +1.66 · **절삭 +0.09(양수)** · 초과 +1.33 · 학CI +0.22 · 양수해 10/11
금액이 아니라 **사람 수**로 거르는 쪽이다. 한 사람이 크게 사는 것보다 여럿이 같이 사는 게
합의된 신호라는 해석이 붙고, 복권형도 덜하다.

⚠ 이전에 이 계열에서 정의 사고가 있었다 — bn 을 '거래 줄 수' 로 세어 '4인' 이 사실은 한 사람의
   분할매수였다. 여기서는 **신고 식별자(accession)의 고유 개수**로 센다.

  ① 인원 문턱 × 보유일 (기준선 셋 나란히)
  ② 복권형 — 중앙 · 절삭 · 상위 1%/5% 비중
  ③ 스트레스 2006~2015
  ④ 계좌 — 미장 4규칙에 다섯째로 얹었을 때

    python us_bull6.py
"""
import sys, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
src = open(Path(__file__).parent / "us_bull5.py", encoding="utf-8").read()
exec(src.split('print("\\n" + "=" * 168)')[0].split('"""', 2)[2])

print("\n" + "=" * 168); print("① 인원 문턱 × 보유일"); print("=" * 168); print(HDR)
for n in (2, 3, 4):
    for h in (20, 40):
        show(f"  신고 {n}건 이상 · {h}일", BASEC & (K.bn >= n), h=h)
    print()
print("  ── 금액을 곁들이면 ──")
show("  2건↑ & 합계 30만$↑ · 20일", BASEC & (K.bn >= 2) & (K.bv >= 3e5), h=20)
show("  2건↑ & 합계 100만$↑ · 20일", BASEC & (K.bn >= 2) & (K.bv >= 1e6), h=20)

print("\n" + "=" * 168); print("② 복권형 점검"); print("=" * 168)
for nm, c, h in (("신고 2건↑ · 20일", K.bn >= 2, 20), ("신고 2건↑ · 40일", K.bn >= 2, 40),
                 ("신고 3건↑ · 20일", K.bn >= 3, 20)):
    d = dd(BASEC & c, h)
    if len(d) < 60: continue
    d["ex"] = d.r - d.date.map(BENS[("act", h)]); tot = d.r.sum()
    print(f"\n  ■ {nm} ({len(d):,}건 · 하루 {len(d)/NDAY:.2f}종목)")
    print(f"     승률 {(d.r>0).mean()*100:.1f}% · 평균 {d.r.mean():+.2f} · 중앙 {d.r.median():+.2f} · "
          f"상위5% 절삭 {d.r[d.r<=d.r.quantile(.95)].mean():+.2f}")
    print(f"     상위 1%가 수익의 {d.r.nlargest(max(1,len(d)//100)).sum()/tot*100:>5.1f}% · "
          f"상위 5%가 {d.r.nlargest(max(1,len(d)//20)).sum()/tot*100:>5.1f}%")
    print("     연도별 초과: " + " ".join(f"{y[2:]}:{v:+.1f}"
          for y, v in d.groupby(d.date.str[:4]).ex.mean().items()))

print("\n" + "=" * 168); print("③ 스트레스 2006~2015"); print("=" * 168); print(HDR)
for n in (2, 3):
    for h in (20, 40):
        show(f"  신고 {n}건↑ · {h}일 · 06~15", BASEC & (K.bn >= n), h=h, lo="20060101", hi="20151231")

# ── ④ 계좌 ───────────────────────────────────────────────────────────
print("\n" + "=" * 168); print("④ 계좌 — 미장 4규칙에 다섯째로 (30시드)"); print("=" * 168)
B2 = pd.read_pickle(BASE / "data/us/buyback.pkl")
SP = B2[B2.tag == "spend"].copy()
SP["days"] = (pd.to_datetime(SP.end, errors="coerce") - pd.to_datetime(SP.start, errors="coerce")).dt.days
SP = SP[(SP.days >= 60) & (SP.days <= 200) & (SP.val > 0)]
SP = SP.sort_values("days").drop_duplicates(["ticker", "filed"], keep="first")
SP = SP.rename(columns={"filed": "date"})[["ticker", "date", "val"]].rename(columns={"val": "bbv"})
K = K.merge(SP, on=["ticker", "date"], how="left")
g2 = K.groupby("ticker", sort=False)
K["sp60"] = g2.bbv.transform(lambda s: s.rolling(60, min_periods=1).count()) > 0
K["a20b"] = g2.volume.transform(lambda s: s.shift(3).rolling(20).mean())
K["re_mo"] = K.vm3 / K.a20b * 100
_w = (K.fromhi >= -5).fillna(False)
_sn = (_w.groupby(K.ticker).shift(1).fillna(False).astype(bool)
       .groupby(K.ticker).transform(lambda s: s.rolling(20, min_periods=1).max()).fillna(0) > 0)
N1S = (BASEC & _w & ~_sn & (K.re_mo <= 100)).fillna(False)
PURE = ((K.fromhi <= -30) & K.sp60 & (K.ret20 <= -20)).fillna(False)
_s2 = (PURE.groupby(K.ticker).shift(1).fillna(False).astype(bool)
       .groupby(K.ticker).transform(lambda s: s.rolling(20, min_periods=1).max()).fillna(0) > 0)
N4S = (PURE & ~_s2 & UNI).fillna(False)
DN = K.ixup == False
U2 = K.amt20.fillna(0) >= 2.0
DEBT = K["부채비율"] if "부채비율" in K.columns else pd.Series(np.nan, index=K.index)
D1c = (U2 & DN & (K.ret20 <= -30) & (K.su1 >= 2) & (K.u <= -10) & (DEBT.isna() | (DEBT <= 200))).fillna(False)
D2c = (U2 & DN & (K.PBR > 0) & (K.PBR <= 0.8) & (K.ret20 <= -10) & (K.su1 >= 2) & (K.u <= -10)).fillna(False)
def tb(cond, h):
    d = dd(cond, h); d = d[d.buy > 0].copy(); d["ret"] = d.r; d["hold"] = h
    return d[["date", "ticker", "hold", "ret", "di", "amt20"]]
def sim(parts, ds, seed=None):
    S = pd.concat([t.assign(rid=r, pct=p, mx=m) for r, t, p, m in parts],
                  ignore_index=True).sort_values("di").reset_index(drop=True)
    rng = np.random.default_rng(seed) if seed is not None else None
    nav, held, cnt = 1.0, {}, {}; peak, mdd, npos = 1.0, 0.0, []
    byd = {d: gg for d, gg in S[S.date.isin(set(ds))].groupby("date")}
    for d in ds:
        di = ADI[d]
        for k in [k for k, v in held.items() if v[0] <= di]:
            nav *= 1 + held.pop(k)[1] / 100; cnt[k[0]] = cnt.get(k[0], 0) - 1
        peak = max(peak, nav); mdd = min(mdd, nav / peak - 1); npos.append(len(held))
        gg = byd.get(d)
        if gg is None: continue
        gg = (gg.sample(frac=1, random_state=int(rng.integers(1 << 30))) if rng is not None
              else gg.sort_values("amt20", ascending=False, na_position="last"))
        for r_ in gg.itertuples():
            if cnt.get(r_.rid, 0) >= r_.mx: continue
            k = (r_.rid, r_.ticker, d)
            if k in held or sum(x[3] for x in held.values()) + r_.pct / 100 > 1.0: continue
            held[k] = (di + int(r_.hold), r_.ret * r_.pct / 100, r_.rid, r_.pct / 100)
            cnt[r_.rid] = cnt.get(r_.rid, 0) + 1
    for v in held.values(): nav *= 1 + v[1] / 100
    return nav, mdd * 100, float(np.mean(npos))
PER = [("학습", "20160101", "20221231"), ("검증", "20230101", "20991231"), ("기준", "20160101", "20991231")]
DS = {p[0]: [d for d in ud if p[1] <= d <= p[2]] for p in PER}
BASE4 = [("D1", tb(D1c, 20), 5, 3), ("D2", tb(D2c, 40), 5, 3),
         ("N1", tb(N1S, 40), 10, 4), ("N4", tb(N4S, 60), 5, 3)]
print(f"  {'구성':<30}{'학습':>10}{'검증':>10}{'기준':>10}{'낙폭':>7}{'동시보유':>9}{'랜중앙':>10}{'랜최악':>10}")
def row(nm, extra=None):
    parts = BASE4 + ([extra] if extra else [])
    res = [sim(parts, DS[p[0]]) for p in PER]
    R = np.array([sim(parts, DS["기준"], seed=k)[0] for k in range(30)])
    print(f"  {nm:<30}" + "".join(f"{x[0]:>9.2f}배" for x in res)
          + f"{res[2][1]:>6.0f}%{res[2][2]:>8.1f}개{np.median(R):>9.2f}배{R.min():>9.2f}배", flush=True)
row("미장 4규칙 (현행)")
for n, h, pct, mx in ((2, 20, 5, 3), (2, 40, 5, 3), (3, 20, 5, 3), (2, 20, 10, 2)):
    row(f"+ 내부자 {n}건↑ · {h}일 · {mx}×{pct}%",
        ("I", tb(BASEC & (K.bn >= n), h), pct, mx))
try:
    import verdict; verdict.log_trials("us_bull2nd", 30)
except Exception as e: print(e)
