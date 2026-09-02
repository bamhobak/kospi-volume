# -*- coding: utf-8 -*-
"""상승장 세 번째 규칙 탐색 — 기존 두 규칙의 축을 재조합하되 종목이 겹치지 않는 것.

기존 상승장 규칙
  [조용한 신고가] 신고가 근처 · 거래량 침체(r16<120) · 저변동(vol20<=2) · 외인 5일 매수
                  · 아직 안 오름(ret20<=5) · 대형(거래대금 200억+)
  [외인 매집]     시총 1~10조 · 외인 20일 매수 · 기관은 안 삼(ow60<0.4) · 거래량 평소수준
                  · 고점 -15% 이내 · 저점대비 +70% · 내부자 신고

두 규칙이 함께 쓰는 축(수급·거래량상태·고점거리)을 방향이나 문턱을 달리해 조합한다.
겹침이 크면 새 규칙이 아니라 기존 규칙의 변형일 뿐이므로, 같은 종목·같은 시기를
얼마나 피하는지를 채택 기준에 넣는다.

규율: 조건은 학습(2018~22)만 보고 고르고 검증(2023~)은 확인용.
게이트 ✅ = 학습CI>0 & 붐제외CI>0 & 전체중앙>0 & 붐제외중앙>0 & 상위5%제거평균>0
겹침 = 새 규칙 신호 중 기존 두 규칙이 ±10거래일 안에 같은 종목을 잡은 비율
"""
import io, sys, gc, itertools
from pathlib import Path
import numpy as np, pandas as pd
import FinanceDataReader as fdr

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
BASE = Path(__file__).parent
HOLD = 40                      # 기존 두 규칙(40·60일)의 중간

IX = fdr.DataReader("KS11", "2017-01-01"); IX = IX[IX.Close > 0].copy()
IX["date"] = IX.index.strftime("%Y%m%d")
UP60 = dict(zip(IX.date, IX.Close > IX.Close.rolling(60).mean())); del IX; gc.collect()

COLS = ["ticker","date","close","open","low","buy","cost","dil","amt20","marcap",
        "fromhi","fromlo","r16","rw1","fw5","fw20","fw60","ow5","ow20","ow60",
        "vol20","sr20","ret20","ret60","ret120","su1","clv","dma20","dma60","u","srd","n40"]
K = pd.read_pickle(BASE/"data/kp_ow.pkl")
K = K[[c for c in COLS if c in K.columns]].sort_values(["ticker","date"]).reset_index(drop=True)
INS = pd.read_pickle(BASE/"data/insider_feat.pkl")[["ticker","date","ins60"]]
n0 = len(K); K = K.merge(INS, on=["ticker","date"], how="left"); assert len(K) == n0
del INS; gc.collect()
K["pref"] = ~K.ticker.str.endswith("0")
K.loc[K.marcap/1e4 > 2000, "marcap"] = np.nan
K["cap조"] = K.marcap/1e4
K["yr"] = K.date.str[:4]
K["up"] = K.date.map(UP60).fillna(False)
dates = sorted(K.date.unique()); K["di"] = K.date.map({d:i for i,d in enumerate(dates)})

BASEU = ((~K.pref) & (K.close >= 1000) & (~K.dil.fillna(False)) & (K.amt20.fillna(0) >= 30) & K.up)
# 기존 두 규칙 (겹침 측정용)
P1 = ((~K.pref) & (K.close>=1000) & (~K.dil.fillna(False)) & (K.amt20.fillna(0)>=200)
      & (K.fromhi>=-10) & (K.r16<120) & (K.rw1<=120) & (K.fw5>=3) & (K.fw60>=1)
      & (K.vol20<=2) & (K.sr20<=0.5) & (K.ret20<=5))
P7 = (BASEU & (K["cap조"]>=1) & (K["cap조"]<10) & (K.fw20>=1) & (K.ow60<0.4)
      & (K.r16>=100) & (K.r16<150) & (K.fromhi>=-15) & (K.fromlo>=70) & (K.ins60.fillna(0)>0))
OLD = {}                                  # ticker -> 기존 규칙이 잡은 di 목록
for m in (P1, P7):
    z = K[m.fillna(False)]
    for t, i in zip(z.ticker.values, z.di.values): OLD.setdefault(t, []).append(i)
print(f"유니버스 {int(BASEU.sum()):,}행 · 기존 [조용한 신고가] {int(P1.sum()):,} · [외인 매집] {int(P7.sum()):,}")

def boot(v, k, seed=127, n=2000):
    if len(v) < 25: return None
    rng = np.random.default_rng(seed)
    d = pd.DataFrame({"r": np.asarray(v), "ym": np.asarray(k)})
    by = {m: gg.r.to_numpy() for m, gg in d.groupby("ym")}; ms = list(by)
    if len(ms) < 3: return None
    return np.percentile([np.concatenate([by[x] for x in rng.choice(ms,len(ms),replace=True)]).mean()
                          for _ in range(n)], [2.5,97.5])

def dedup(m):
    X = K[m.fillna(False)].dropna(subset=["n40"]).sort_values("di")
    keep, last = [], {}
    for t, i, ix in zip(X.ticker.values, X.di.values, X.index):
        if last.get(t,-10**9) >= i: continue
        last[t] = i + HOLD; keep.append(ix)
    return X.loc[keep]

def overlap(Z):
    """기존 두 규칙이 ±10거래일 안에 같은 종목을 잡았나"""
    if not len(Z): return 100.0
    hit = 0
    for t, i in zip(Z.ticker.values, Z.di.values):
        for j in OLD.get(t, ()):
            if abs(j - i) <= 10: hit += 1; break
    return hit/len(Z)*100

def stat(m, tag=None, quiet=False, minn=40):
    Z = dedup(m)
    if len(Z) < minn:
        if not quiet and tag: print(f"  {tag:<38} {len(Z):>4} (부족)")
        return None
    r = Z.n40.values; ym = Z.date.str[:6]
    zi, zo, nb = Z[Z.date<"20230101"], Z[Z.date>="20230101"], Z[Z.yr<"2025"]
    ci, cn = boot(zi.n40.values, zi.date.str[:6]), boot(nb.n40.values, nb.date.str[:6])
    cut = np.percentile(r,95); t5 = r[r<=cut].mean()
    med = float(np.median(r)); mnb = float(np.median(nb.n40)) if len(nb) else np.nan
    lo = ci[0] if ci is not None else np.nan; ln = cn[0] if cn is not None else np.nan
    ok = bool(lo>0 and ln>0 and med>0 and mnb>0 and t5>0)
    ov = overlap(Z); yrs = Z.groupby("yr").n40.mean()
    d = dict(n=len(Z), r=r.mean(), win=(r>0).mean()*100, med=med, t5=t5,
             IS=zi.n40.mean(), OS=zo.n40.mean() if len(zo) else np.nan,
             nb=nb.n40.mean() if len(nb) else np.nan, ok=ok, ov=ov,
             pos=int((yrs>0).sum()), ny=len(yrs), ci=ci, cn=cn,
             top=Z.groupby("yr").n40.size().max()/len(Z)*100, Z=Z)
    if not quiet and tag:
        f = lambda x: f"[{x[0]:+.1f},{x[1]:+.1f}]" if x is not None else "-"
        print(f"  {tag:<38} {d['n']:>4} {d['r']:>+7.2f} {d['win']:>4.0f}% {med:>+7.2f} {t5:>+7.2f} "
              f"{d['IS']:>+7.2f} {d['OS']:>+7.2f} {d['nb']:>+7.2f} {d['pos']}/{d['ny']:<2} "
              f"{ov:>4.0f}% {d['top']:>4.0f}% {f(ci):>13}{'  ✅' if ok else ''}")
    return d

HDR = (f"  {'조건':<38} {'n':>4} {'평균':>7} {'승률':>5} {'중앙':>7} {'상5뺀':>7} {'IS':>7} {'OS':>7} "
       f"{'붐제외':>7} {'양수년':>5} {'겹침':>5} {'최다年':>5} {'학습CI':>13}")
print(f"\n## 0) 기존 두 규칙 (기준선 · 40일 보유로 통일해 비교)\n{HDR}")
stat(P1, "[조용한 신고가]"); stat(P7, "[외인 매집]")

# ── 신용잔고: 기존 두 규칙이 전혀 쓰지 않는 새 정보축 (이번에 수집) ──
import sqlite3
_c = sqlite3.connect(f"file:{BASE}/data/kis/market.db?mode=ro", uri=True, timeout=600)
CR = pd.read_sql("SELECT date,ticker,loan_rmnd,loan_rmnd_rate FROM credit", _c); _c.close()
CR = CR.sort_values(["ticker","date"])
_g = CR.groupby("ticker", sort=False)
CR["cr_chg20"] = (CR.loan_rmnd/_g.loan_rmnd.shift(20)-1)*100          # 신용잔고 20일 증감(%)
_mu = _g.loan_rmnd_rate.transform(lambda x: x.rolling(120).mean())
_sd = _g.loan_rmnd_rate.transform(lambda x: x.rolling(120).std()).replace(0, np.nan)
CR["cr_z"] = (CR.loan_rmnd_rate - _mu) / _sd                          # 평소 대비 신용비율
_n = len(K)
K = K.merge(CR[["date","ticker","loan_rmnd_rate","cr_chg20","cr_z"]], on=["ticker","date"], how="left")
assert len(K) == _n
del CR, _g, _mu, _sd; gc.collect()
print(f"신용잔고 병합 — 채움 {K.loan_rmnd_rate.notna().mean()*100:.0f}% "
      f"(상승장 유니버스 내 {K.loc[BASEU.values,'loan_rmnd_rate'].notna().mean()*100:.0f}%)")

# ── 후보 조건 풀: 두 규칙이 쓰는 축을 방향·문턱을 달리해 만든다 ──
IS_M = BASEU & (K.date < "20230101")
C = {
 # 수급 — 기존은 외인 매수 중심. 기관 쪽과 개인 이탈을 본다
 "기관 20일 매수(ow20≥1)":      K.ow20 >= 1,
 "기관 60일 매수(ow60≥1)":      K.ow60 >= 1,
 "외인·기관 동시(fw20≥1&ow20≥1)": (K.fw20 >= 1) & (K.ow20 >= 1),
 "외인 60일 강함(fw60≥3)":      K.fw60 >= 3,
 # 거래량 상태 — 기존은 침체(<120) 또는 평소(100~150). 급증 구간을 본다
 "거래량 급증(r16≥150)":        K.r16 >= 150,
 "거래량 극침체(r16<80)":        K.r16 < 80,
 "단기 급증(rw1≥150)":          K.rw1 >= 150,
 # 고점거리 — 기존은 -10%·-15% 이내. 눌림 구간을 본다
 "고점 -25~-10%":              (K.fromhi < -10) & (K.fromhi >= -25),
 "고점 -40~-25%":              (K.fromhi < -25) & (K.fromhi >= -40),
 # 가격 위치·추세
 "저점대비 +100%↑":             K.fromlo >= 100,
 "저점대비 30~70%":             (K.fromlo >= 30) & (K.fromlo < 70),
 "20일선 아래(dma20<0)":        K.dma20 < 0,
 "20일 조정(ret20≤-5)":         K.ret20 <= -5,
 "60일 상승(ret60≥20)":         K.ret60 >= 20,
 # 규모 — 기존은 1~10조 / 거래대금 200억+
 "시총 3천억~1조":               (K["cap조"] >= 0.3) & (K["cap조"] < 1),
 "시총 10조↑":                  K["cap조"] >= 10,
 # 변동성·공매도
 "저변동(vol20≤1.5)":           K.vol20 <= 1.5,
 "공매도 감소(srd)":             K.srd == True,
 "내부자 신고(ins60>0)":         K.ins60.fillna(0) > 0,
 "업종 강세(u≥10)":              K.u >= 10,
 # 신용잔고 — 기존 두 규칙이 안 쓰는 축. 빚내서 산 물량 상태를 본다
 "신용잔고 20일 -10%↓":         K.cr_chg20 <= -10,
 "신용잔고 20일 -20%↓":         K.cr_chg20 <= -20,
 "신용잔고 20일 +20%↑":         K.cr_chg20 >= 20,
 "신용비율 평소보다 낮음(z≤-1)":   K.cr_z <= -1,
 "신용비율 평소보다 높음(z≥1)":    K.cr_z >= 1,
 "신용비율 절대낮음(≤0.5%)":      K.loan_rmnd_rate <= 0.5,
}
print(f"\n## 1) 후보 조건 단독 (상승장 · 40일 보유)\n{HDR}")
single = {}
for nm, c in C.items():
    d = stat(BASEU & c, nm)
    if d: single[nm] = (d, c)

# 학습구간 성적이 유니버스 평균보다 나은 것만 조합 후보로
base_is = dedup(BASEU)
base_is = base_is[base_is.date < "20230101"].n40.mean()
good = {k: v for k, v in single.items() if v[0]["IS"] > base_is}
print(f"\n  유니버스 학습 평균 {base_is:+.2f}% · 이를 넘긴 조건 {len(good)}개")

print(f"\n## 2) 2개 조합 — 게이트 통과 & 겹침 40% 미만만 표시\n{HDR}")
found = []
for (n1,(d1,c1)),(n2,(d2,c2)) in itertools.combinations(good.items(), 2):
    d = stat(BASEU & c1 & c2, quiet=True)
    if d and d["ok"] and d["ov"] < 40 and d["n"] >= 50:
        found.append((f"{n1} + {n2}", c1 & c2, d))
found.sort(key=lambda x: -x[2]["r"])
for tag, c, d in found[:12]:
    stat(BASEU & c, tag[:38])
if not found: print("  (게이트를 통과하면서 겹침이 낮은 2개 조합 없음)")

print("")
print("## 2b) 3개 조합 — 게이트 통과 & 겹침<40% & 검증(OS)>0 & 최다연도<45%")
print(HDR)
_n3 = len(good)*(len(good)-1)*(len(good)-2)//6
print(f"  (조건 {len(good)}개에서 {_n3}개 조합 검사 — 다중검정이라 우연히 통과하는 것이 섞인다.")
print("   구조가 납득되고 검증구간까지 버티는 것만 후보로 볼 것)")
_before = len(found)
for (n1,(d1,c1)),(n2,(d2,c2)),(n3,(d3,c3)) in itertools.combinations(good.items(), 3):
    d = stat(BASEU & c1 & c2 & c3, quiet=True, minn=40)
    if d and d["ok"] and d["ov"] < 40 and d["OS"] > 0 and d["top"] < 45:
        found.append((f"{n1} + {n2} + {n3}", c1 & c2 & c3, d))
found.sort(key=lambda x: -x[2]["r"])
print(f"  통과 {len(found)-_before}개")
for tag, c, d in found[:12]:
    stat(BASEU & c, tag[:38])

print(f"\n## 3) 상위 후보의 연도별 분포")
for tag, c, d in found[:5]:
    Z = d["Z"]; yr = Z.groupby("yr").n40.agg(["mean","size"])
    print(f"  {tag[:46]}")
    print("    " + " ".join(f"{i}:{r['mean']:+.0f}%({int(r['size'])})" for i, r in yr.iterrows())
          + f"   최다연도 {d['top']:.0f}% · 겹침 {d['ov']:.0f}%")
print("\n※ 겹침이 낮아야 '새 규칙'이다. 높으면 기존 규칙의 변형일 뿐이다.")
print("  학습에서 골랐으므로 OS(검증)에서 무너지면 과적합 — 채택 전 반드시 확인할 것.")
