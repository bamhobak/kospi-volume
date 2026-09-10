# -*- coding: utf-8 -*-
"""[잔잔한 급등주] 확장 조사 ② — 우리가 가진 재료를 얹어 본다.

미장 재료 목록(전부 우리가 직접 모은 것)
  · 내부자 Form 4      data/us_ins.pkl        (공시일 기준 · bv60/sv60/bcap)
  · 자사주 집행        data/us/buyback.pkl    (companyfacts · 12.3만 행)
  · 13F 기관보유       data/us/f13_hold.pkl   (2013~ · 보유주식수·기관 수)
  · SEC 재무           data/us/fin.pkl        (equity·ni·shares → 흑자·ROE·희석)
  · 매크로             data/us/fred.pkl       (VIX·NFCI·장단기금리차)
  · 패널 내장          PBR·PER·부채비율·시총·공매도(srd)

**왜 재료를 얹나:** 지금 후보는 순수 가격 규칙이라 '왜 오르는지' 를 모른다.
1년에 두 배 오른 종목은 실적이 받쳐주는 쪽과 스토리뿐인 쪽이 섞여 있다.
그걸 가를 수 있으면 신호가 줄면서 질이 오른다 — [[us-buyback-rule-n4]] 가 그 방식이었다.

**주의:** 재료를 얹으면 거의 항상 성적이 좋아 보인다(조건을 더 걸었으니).
그래서 **여집합**을 반드시 함께 낸다. 여집합이 나쁘지 않으면 그 재료는 힘이 없는 것이고
그냥 표본을 줄인 것뿐이다([[youtube51-test]] 재료 얹기 전량 기각의 교훈).

    python us_tech9.py
"""
import sys, time, gc, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
from vp_lib import boot_ci

BASE = Path(__file__).parent; TR1, VA0 = "20221231", "20230101"
MAT = BASE / "data/us_mat.pkl"
def log(m): print(f"{time.strftime('%H:%M:%S')} {m}", flush=True)

if not MAT.exists():
    log("재료판을 만든다 (한 번만 · 이후 재사용)")
    COLS = ["date", "ticker", "close", "rawclose", "pref", "amt20", "marcap", "PBR", "PER",
            "부채비율", "vol20", "ret60", "ret120", "ret250", "n20", "n40", "n60", "buy",
            "srd", "volume", "fromhi", "bv60", "sv60", "bcap", "bn60"]
    K = pd.read_pickle(BASE / "data/us_ins.pkl")
    K = K[[c for c in COLS if c in K.columns]].copy(); gc.collect()
    K = K[((~K.pref.fillna(False)) & (K.rawclose >= 3)).fillna(False)]
    K = K.sort_values(["ticker", "date"]).reset_index(drop=True)
    log(f"  기본 {len(K):,}행 · 내부자 열 {[c for c in ('bv60','sv60','bcap') if c in K.columns]}")

    # ── 자사주 — 집행 종료일(end) 기준. 공시일(filed) 이전에는 알 수 없다 ──
    B = pd.read_pickle(BASE / "data/us/buyback.pkl")
    B = B[(B.val > 0) & B.ticker.notna()].copy()
    B["d"] = B.filed.astype(str)                      # 공시일에 알게 된다(미래참조 방지)
    B = B.sort_values("d").groupby(["ticker", "d"], as_index=False).val.sum()
    B = B.rename(columns={"d": "date", "val": "bbval"})
    K = K.merge(B, on=["ticker", "date"], how="left")
    g = K.groupby("ticker", sort=False)
    K["bb250"] = g.bbval.transform(lambda s: s.fillna(0).rolling(250, min_periods=1).sum())
    K["bbcap"] = K.bb250 / (K.marcap * 1e6) * 100     # 1년 자사주 집행액 / 시총 (%)
    del B; gc.collect(); log("  자사주 붙임")

    # ── 13F — 분기 보고. pdate(기준일) 이후 45일에나 공개되므로 fdate(제출일)로 붙인다 ──
    F = pd.read_pickle(BASE / "data/us/f13_hold.pkl")
    F = F[F.ticker.notna()].copy()
    F["date"] = F.fdate.astype(str)
    F = F.sort_values("date").groupby(["ticker", "date"], as_index=False).agg(
        f13sh=("sh", "sum"), f13n=("ninst", "max"))
    K = K.merge(F, on=["ticker", "date"], how="left")
    g = K.groupby("ticker", sort=False)
    for c in ("f13sh", "f13n"):
        K[c] = g[c].ffill()
    K["f13n_ch"] = K.f13n - g.f13n.shift(65)          # 기관 수 한 분기 변화
    K["f13sh_ch"] = (K.f13sh / g.f13sh.shift(65) - 1) * 100
    del F; gc.collect(); log("  13F 붙임")

    # ── SEC 재무 — filed 기준 ──
    FN = pd.read_pickle(BASE / "data/us/fin.pkl")
    FN = FN[FN.ticker.notna()].copy(); FN["date"] = FN.filed.astype(str)
    FN = FN.sort_values("date").groupby(["ticker", "date"], as_index=False).agg(
        equity=("equity", "last"), ni=("ni", "last"), shares=("shares", "last"))
    K = K.merge(FN, on=["ticker", "date"], how="left")
    g = K.groupby("ticker", sort=False)
    for c in ("equity", "ni", "shares"):
        K[c] = g[c].ffill()
    K["roe"] = K.ni / K.equity * 100
    K["dilu"] = (K.shares / g.shares.shift(250) - 1) * 100      # 1년 주식수 증가율(희석)
    del FN; gc.collect(); log("  재무 붙임")

    # ── 매크로 ──
    FR = pd.read_pickle(BASE / "data/us/fred.pkl")
    FR = FR.reset_index(); FR.columns = ["date"] + list(FR.columns[1:])
    FR["date"] = pd.to_datetime(FR.date).dt.strftime("%Y%m%d")
    K = K.merge(FR[["date", "VIXCLS", "NFCI", "T10Y2Y"]], on="date", how="left")
    for c in ("VIXCLS", "NFCI", "T10Y2Y"):
        K[c] = K[c].ffill()
    del FR; gc.collect(); log("  매크로 붙임")

    K["r1"] = K.groupby("ticker", sort=False).close.pct_change() * 100
    K["q"] = K.groupby("ticker", sort=False).r1.transform(lambda s: s.abs().rolling(60).mean())
    K["multi"] = (K.ret60 > 0) & (K.ret120 > 0) & (K.ret250 > 0)
    for c in K.columns:
        if K[c].dtype == np.float64: K[c] = K[c].astype("float32")
    K.to_pickle(MAT); log(f"저장 {MAT} · {len(K):,}행 · 열 {len(K.columns)}")
else:
    log("재료판 읽는 중")
    K = pd.read_pickle(MAT)

ud = sorted(K.date.unique()); K["di"] = K.date.map({d: i for i, d in enumerate(ud)}).astype(np.int32)
UNI = (K.groupby("date").amt20.rank(pct=True) >= 0.6).fillna(False)
BEN = {h: K[UNI].dropna(subset=[f"n{h}"]).groupby("date")[f"n{h}"].mean() for h in (20, 40, 60)}
NDAY = len([d for d in ud if d >= "20160101"])
def trim(r):
    r = pd.Series(r).dropna()
    return r[r <= r.quantile(0.95)].mean() if len(r) else np.nan
BT = {h: trim(K[UNI & (K.date >= "20160101")][f"n{h}"].dropna().astype(float)) for h in (20, 40, 60)}
log(f"준비 완료 · {len(K):,}행")

def dd(cond, h, lo="20160101", hi="20991231"):
    X = K[(cond & UNI).fillna(False)].dropna(subset=[f"n{h}"])
    X = X[(X.date >= lo) & (X.date <= hi)].sort_values("di")
    keep, last = [], {}
    for t, i, ix in zip(X.ticker.values, X.di.values, X.index):
        if last.get(t, -10**9) >= i: continue
        last[t] = i + h; keep.append(ix)
    d = X.loc[keep].copy()
    d["r"] = d[f"n{h}"].astype(float); d["ex"] = d.r - d.date.map(BEN[h]); d["ym"] = d.date.str[:6]
    return d[d.r.notna()]

HDR = (f"  {'조건':<34} {'n':>6} {'동시':>5} {'승률':>6} {'평균':>7} {'중앙':>7} {'절삭Δ':>7} "
       f"{'초과':>7} {'학습':>7} {'검증':>7} {'CI':>7} {'연양수':>7}")
OK = []
def show(tag, cond, h=60, sink=True):
    d = dd(cond, h)
    if len(d) < 60: print(f"  {tag:<34} {len(d):>6}  (표본 부족)"); return
    tr = d[d.date <= TR1]; va = d[d.date >= VA0]
    ci = boot_ci(d.groupby("ym").ex.mean()); yr = d.groupby(d.date.str[:4]).ex.mean()
    dtm = trim(d.r) - BT[h]; per = len(d) / NDAY
    print(f"  {tag:<34} {len(d):>6,} {per*h:>5.0f} {(d.r>0).mean()*100:>5.1f}% {d.r.mean():>7.2f} "
          f"{d.r.median():>7.2f} {dtm:>7.2f} {d.ex.mean():>7.2f} {tr.ex.mean():>7.2f} "
          f"{va.ex.mean():>7.2f} {ci:>7.2f} {int((yr>0).sum()):>4}/{len(yr)}")
    if sink and dtm > 0 and d.ex.mean() > 0 and va.ex.mean() > 0 and ci > 0 and (yr > 0).sum() >= len(yr) * 0.72:
        OK.append((tag, h, len(d), per * h, d.ex.mean(), va.ex.mean(), ci, int((yr > 0).sum()), len(yr)))

BASECOND = K.multi & (K.ret250 >= 120) & (K.q <= 1.5)
W = 138
print("\n" + "=" * W)
print("① 기준 — 재료 없는 [잔잔한 급등주] (1년 120%↑ · 잔잔 ≤1.5%)")
print("=" * W); print(HDR)
for h in (20, 40, 60): show(f"  {h}일 보유", BASECOND, h)

print("\n" + "=" * W)
print("② 재료를 얹는다 — 그리고 **여집합을 반드시 함께** (60일 보유)")
print("=" * W); print(HDR)
MATS = [
    ("내부자 60일 순매수 > 0", K.bv60 > K.sv60),
    ("내부자 매수 있음(bn60>0)", K.bn60 > 0),
    ("내부자 매도만 있음", (K.sv60 > 0) & (K.bv60 <= 0)),
    ("자사주 1년 집행 시총 1%↑", K.bbcap >= 1),
    ("기관 수 한 분기 증가", K.f13n_ch > 0),
    ("기관 보유주식 5%↑ 증가", K.f13sh_ch >= 5),
    ("흑자 (ni>0)", K.ni > 0),
    ("ROE 10%↑", K.roe >= 10),
    ("희석 없음 (1년 주식수 +5% 미만)", K.dilu < 5),
    ("희석 큼 (1년 주식수 +20%↑)", K.dilu >= 20),
    ("부채비율 200% 이하", K["부채비율"] <= 200),
    ("PBR 있음 & 5 이하", (K.PBR > 0) & (K.PBR <= 5)),
    ("공매도 비중 낮음(srd 하위50%)", K.srd <= K[UNI].srd.median()),
    ("시총 $1B↑", K.marcap >= 1000),
    ("시총 $1B 미만", K.marcap < 1000),
    ("VIX 25 미만", K.VIXCLS < 25),
    ("금융여건 완화(NFCI<0)", K.NFCI < 0),
]
for nm, m in MATS:
    show(f"  + {nm}", BASECOND & m.fillna(False))
    show(f"     └ 여집합", BASECOND & ~m.fillna(False), sink=False)

print("\n" + "=" * W)
print("③ 살아남은 재료를 겹쳐 본다 (60일 보유)")
print("=" * W); print(HDR)
CORE = BASECOND
show("  기준", CORE)
show("  + 흑자 + 희석없음", CORE & (K.ni > 0).fillna(False) & (K.dilu < 5).fillna(False))
show("  + 흑자 + 내부자 순매수", CORE & (K.ni > 0).fillna(False) & (K.bv60 > K.sv60).fillna(False))
show("  + 흑자 + 기관수 증가", CORE & (K.ni > 0).fillna(False) & (K.f13n_ch > 0).fillna(False))
show("  + 희석없음 + 기관수 증가", CORE & (K.dilu < 5).fillna(False) & (K.f13n_ch > 0).fillna(False))
show("  + 흑자 + 희석없음 + 기관수↑",
     CORE & (K.ni > 0).fillna(False) & (K.dilu < 5).fillna(False) & (K.f13n_ch > 0).fillna(False))

print("\n" + "=" * W)
print("④ 집안 잣대 통과 (절삭Δ>0 · 초과>0 · 검증>0 · CI>0 · 연양수 72%↑)")
print("=" * W)
if OK:
    for tag, h, n, sim, ex, va, ci, y, ny in OK:
        print(f"  ✅ {tag.strip():<34} {h}일 · {n:>5,}건 · 동시 {sim:>4.0f}종목 · "
              f"초과 {ex:+.2f} · 검증 {va:+.2f} · CI {ci:+.2f} · 양수해 {y}/{ny}")
else:
    print("  통과 없음")
