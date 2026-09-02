# -*- coding: utf-8 -*-
"""신용잔고를 기존 규칙에 보조 필터로 얹어본다 (코스피 규칙 한정).

신용잔고를 모은 이유: 우리 규칙 대부분이 낙폭 매수인데 '왜 빠졌나' 를 가르는 축이 없었다.
반대매매 압력으로 밀린 것과 정상 조정은 성격이 다를 수 있다.

주의 — 커버리지 착시
  신용잔고는 코스피 93% / 코스닥 27%(수집 중) 다. 조건을 걸면 데이터 없는 신호가
  통째로 빠지는데 그건 필터 효과가 아니다. 그래서 '신용 데이터 있는 신호만' 을
  별도 기준선으로 두고, 거기서 얼마나 좋아지는지로 판단한다.

규율: 조건은 학습(2018~22)만 보고 고르고 검증(2023~)은 확인용.
게이트 ✅ = 학습CI>0 & 붐제외CI>0 & 전체중앙>0 & 붐제외중앙>0 & 상위5%제거평균>0
"""
import io, sys, gc, sqlite3
from pathlib import Path
import numpy as np, pandas as pd

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
BASE = Path(__file__).parent
src = (BASE / "portfolio.py").read_text(encoding="utf-8")
ns = {"__file__": str(BASE / "portfolio.py")}
class _Sink(io.TextIOWrapper):
    def write(self, *a, **k): return 0
real = sys.stdout; sys.stdout = _Sink(io.BytesIO(), encoding="utf-8")
exec(compile(src.split("# 신호를 한 표로 모은다")[0], "portfolio.py", "exec"), ns)
sys.stdout = real
KP, RULES = ns["KP"], ns["RULES"]
NAME = {"P1":"조용한 신고가","P2":"조정매집","P3":"폭락반등","P4":"업종붕괴 이탈",
        "P5":"자사주 낙폭","P6":"깊은 이격","P7":"외인 매집"}

# ── 신용잔고 병합 ────────────────────────────────────────────────
_c = sqlite3.connect(f"file:{BASE}/data/kis/market.db?mode=ro", uri=True, timeout=600)
CR = pd.read_sql("SELECT date,ticker,loan_rmnd,loan_rmnd_rate FROM credit", _c); _c.close()
CR = CR.sort_values(["ticker", "date"])
g = CR.groupby("ticker", sort=False)
CR["cr_chg20"] = (CR.loan_rmnd / g.loan_rmnd.shift(20) - 1) * 100     # 신용잔고 20일 증감(%)
CR["cr_chg5"] = (CR.loan_rmnd / g.loan_rmnd.shift(5) - 1) * 100
mu = g.loan_rmnd_rate.transform(lambda x: x.rolling(120).mean())
sd = g.loan_rmnd_rate.transform(lambda x: x.rolling(120).std()).replace(0, np.nan)
CR["cr_z"] = (CR.loan_rmnd_rate - mu) / sd                            # 평소 대비 신용비율
n0 = len(KP)
KP = KP.merge(CR[["date","ticker","loan_rmnd_rate","cr_chg20","cr_chg5","cr_z"]],
              on=["ticker","date"], how="left")
assert len(KP) == n0
del CR, g, mu, sd; gc.collect()
KP["yr"] = KP.date.str[:4]
dates = sorted(KP.date.unique()); KP["di"] = KP.date.map({d:i for i,d in enumerate(dates)})
HAS = KP.loan_rmnd_rate.notna()
print(f"신용잔고 병합 — 코스피 채움 {HAS.mean()*100:.0f}%")

def boot(v, k, seed=127, n=2000):
    if len(v) < 20: return None
    rng = np.random.default_rng(seed)
    d = pd.DataFrame({"r": np.asarray(v), "ym": np.asarray(k)})
    by = {m: gg.r.to_numpy() for m, gg in d.groupby("ym")}; ms = list(by)
    if len(ms) < 3: return None
    return np.percentile([np.concatenate([by[x] for x in rng.choice(ms,len(ms),replace=True)]).mean()
                          for _ in range(n)], [2.5,97.5])

def run(mask, hold, stop, tag, quiet=False, minn=25):
    col = f"n{hold}"
    if col not in KP.columns: print(f"  {tag}: n{hold} 없음"); return None
    if stop:
        gg = KP.groupby("ticker", sort=False)
        lo = pd.concat([gg.low.shift(-i) for i in range(hold)], axis=1).min(axis=1)
        r_all = np.where((lo <= KP.buy*(1-stop)).fillna(False), -stop*100 - KP.cost, KP[col])
    else:
        r_all = KP[col].values
    m = mask.fillna(False).values
    X = KP[m].copy(); X["r"] = r_all[m]
    X = X.dropna(subset=["r"]).sort_values("di")
    keep, last = [], {}
    for t, i, ix in zip(X.ticker.values, X.di.values, X.index):
        if last.get(t,-10**9) >= i: continue
        last[t] = i + hold; keep.append(ix)
    Z = X.loc[keep]
    if len(Z) < minn:
        if not quiet: print(f"  {tag:<34} {len(Z):>4} (부족)")
        return None
    zi, zo, nb = Z[Z.date<"20230101"], Z[Z.date>="20230101"], Z[Z.yr<"2025"]
    ci, cn = boot(zi.r.values, zi.date.str[:6]), boot(nb.r.values, nb.date.str[:6])
    cut = np.percentile(Z.r.values, 95); t5 = Z.r.values[Z.r.values<=cut].mean()
    med = float(np.median(Z.r)); mnb = float(np.median(nb.r)) if len(nb) else np.nan
    lo_ = ci[0] if ci is not None else np.nan; ln = cn[0] if cn is not None else np.nan
    ok = bool(lo_>0 and ln>0 and med>0 and mnb>0 and t5>0)
    yrs = Z.groupby("yr").r.mean()
    f = lambda x: f"[{x[0]:+.1f},{x[1]:+.1f}]" if x is not None else "-"
    if not quiet:
        print(f"  {tag:<34} {len(Z):>4} {Z.r.mean():>+7.2f} {(Z.r>0).mean()*100:>4.0f}% {med:>+7.2f} "
              f"{t5:>+7.2f} {zi.r.mean():>+7.2f} {zo.r.mean() if len(zo) else np.nan:>+7.2f} "
              f"{int((yrs>0).sum())}/{len(yrs):<2} {f(ci):>13}{'  ✅' if ok else ''}")
    return dict(n=len(Z), r=Z.r.mean(), win=(Z.r>0).mean()*100, IS=zi.r.mean(),
                OS=zo.r.mean() if len(zo) else np.nan, ok=ok, med=med)

CRC = {
 "신용잔고 20일 -10%↓":  KP.cr_chg20 <= -10,
 "신용잔고 20일 -20%↓":  KP.cr_chg20 <= -20,
 "신용잔고 20일 +10%↑":  KP.cr_chg20 >= 10,
 "신용잔고 5일 -5%↓":    KP.cr_chg5 <= -5,
 "신용비율 z≤-0.5":     KP.cr_z <= -0.5,
 "신용비율 z≥+0.5":     KP.cr_z >= 0.5,
 "신용비율 ≤0.5%":      KP.loan_rmnd_rate <= 0.5,
 "신용비율 ≥2%":        KP.loan_rmnd_rate >= 2,
}
HDR = (f"  {'조건':<34} {'n':>4} {'평균':>7} {'승률':>5} {'중앙':>7} {'상5뺀':>7} "
       f"{'IS':>7} {'OS':>7} {'양수년':>5} {'학습CI':>13}")
for rid in ["P1","P2","P3","P4","P5","P6","P7"]:
    K_, hold, stop, pct, mx, cond = RULES[rid]
    # 주의: 위에서 KP 를 merge 로 새 객체로 바꿨으므로 RULES 안의 패널과 동일성 비교를
    # 하면 안 된다. 행 순서·길이가 보존되므로 조건 Series 는 그대로 쓸 수 있다.
    if rid == "P5":       # 결합 패널(KB) 로 정의돼 있어 코스피 부분만 다시 만든다
        cond = (ns["base"](KP,3) & ns["dn60"](KP) & KP.bb & (KP.ret60<=-20))
    print(f"\n{'='*128}\n#### [{NAME[rid]}] — {hold}일 보유"
          + (f" · 손절 -{int(stop*100)}%" if stop else "") + f"\n{'='*128}\n{HDR}")
    base = run(cond, hold, stop, "현재 (전체 신호)")
    fair = run(cond & HAS, hold, stop, "신용 데이터 있는 신호만 ← 기준")
    if fair is None: continue
    for nm, c in CRC.items():
        d = run(cond & HAS & c, hold, stop, nm)
        if d and d["r"] > fair["r"] + 1 and d["IS"] > fair["IS"] and d["OS"] > fair["OS"]:
            print(f"      ↑ 기준 대비 평균 {d['r']-fair['r']:+.2f}%p · 학습·검증 모두 개선")
print("\n※ '신용 데이터 있는 신호만' 과 비교해야 한다. 전체 신호와 비교하면")
print("  커버리지 차이(코스피 93%)가 필터 효과처럼 보인다.")
