# -*- coding: utf-8 -*-
"""1번 필터 다각도 스윕 — 절대수익 기준 · 학습(19~22)/검증(23~26) 분리"""
import io, sys
import numpy as np, pandas as pd
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
P = pd.read_pickle("data/p1.pkl")
Hp = np.load("data/p1_H.npy"); Lp = np.load("data/p1_L.npy"); Cp = np.load("data/p1_C.npy")
MKT = np.load("data/p1_MKT.npy")
YS = list(range(2019, 2027))
AMT = P.amt.values
COSTV = 0.18 + np.select([AMT >= 100, AMT >= 50, AMT >= 20, AMT >= 10], [0.20, 0.30, 0.50, 0.70], default=1.00)
GP = P.gp.values.astype(int)

def exits(h, sl=None, tp=None):
    """벡터화 청산: 첫 터치 우선 (손절 > 익절 > 만기)"""
    Lm = Lp[:, :h+1]; Hm = Hp[:, :h+1]
    hit_s = (Lm <= -sl) if sl else np.zeros(Lm.shape, bool)
    hit_t = (Hm >= tp) if tp else np.zeros(Hm.shape, bool)
    ks = np.where(hit_s.any(1), hit_s.argmax(1), 999)
    kt = np.where(hit_t.any(1), hit_t.argmax(1), 999)
    kk = np.minimum(np.minimum(ks, kt), h)
    r = Cp[np.arange(len(P)), kk].astype(float)
    r = np.where(ks <= np.minimum(kt, h), -sl if sl else r, r)
    r = np.where((kt < ks) & (kt <= h), tp if tp else r, r)
    return r - COSTV, kk
def alpha_free(h, sl=None, tp=None):
    r, kk = exits(h, sl, tp)
    return r
def stat(mask, h=10, sl=15, tp=30):
    d = P[mask]
    if len(d) < 15: return None
    r = alpha_free(h, sl, tp)[mask.values if hasattr(mask, "values") else mask]
    y = d.y.values
    yy = pd.Series(r).groupby(y).mean(); cnt = pd.Series(r).groupby(y).size(); ok = yy[cnt >= 3]
    mk = MKT[GP[mask.values if hasattr(mask, "values") else mask], h]
    dn = r[mk <= 0]
    return dict(n=len(r), ret=r.mean(), med=np.median(r), win=(r > 0).mean()*100,
                pf=(r[r>0].sum()/abs(r[r<=0].sum())) if (r<=0).any() else 99,
                pos=f"{(ok>0).sum()}/{len(ok)}",
                is_=r[(y<=2022)].mean(), os_=r[(y>=2023)].mean(),
                dn=dn.mean() if len(dn) else np.nan, ndn=len(dn))
def show(title, rows, h=10, sl=15, tp=30):
    print(f"\n## {title}\n")
    print("| 설정 | 건수 | **절대수익** | 중앙값 | 승률 | PF | 하락구간 | 학습 | 검증 | +연도 |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for lab, m in rows:
        s = stat(m, h, sl, tp)
        if not s: print(f"| {lab} | 부족 |" + " - |" * 8); continue
        print(f"| {lab} | {s['n']} | **{s['ret']:+.2f}%** | {s['med']:+.2f}% | {s['win']:.0f}% | {s['pf']:.2f} | "
              f"{s['dn']:+.2f}%({s['ndn']}) | {s['is_']:+.2f}% | **{s['os_']:+.2f}%** | {s['pos']} |")

BASE = (P.quiet < 0.5) & (P.amt >= 50) & (P.ret10.between(0, 20)) & P.k20 & P.rs.notna() & (P.rs > 0) \
       & P.sr5.notna() & P.sr20.notna() & (P.sr5 < P.sr20)
print(f"# 1번 필터 다각도 스윕 (현행 {int(BASE.sum())}건)")
show("① 외국인 5일 비중", [(f"외인 {v}%↑", BASE & (P.fwp >= v)) for v in (2, 3, 5, 7, 10, 15)])
show("② 급등 배율", [(f"급등 {v}배↑", BASE & (P.surge >= v)) for v in (2, 2.5, 3, 4, 5)])
show("③ 잠잠도", [(f"잠잠 <{v}", (P.amt >= 50) & (P.ret10.between(0, 20)) & P.k20 & P.rs.notna() & (P.rs > 0)
                 & P.sr5.notna() & (P.sr5 < P.sr20) & (P.quiet < v)) for v in (0.2, 0.3, 0.4, 0.5, 0.6, 0.7)])
show("④ 거래대금", [(f"{v}억↑", (P.quiet < 0.5) & (P.ret10.between(0, 20)) & P.k20 & P.rs.notna() & (P.rs > 0)
                 & P.sr5.notna() & (P.sr5 < P.sr20) & (P.amt >= v)) for v in (10, 30, 50, 100, 200, 500)])
B0 = (P.quiet < 0.5) & (P.amt >= 50) & P.k20 & P.rs.notna() & (P.rs > 0) & P.sr5.notna() & (P.sr5 < P.sr20)
show("⑤ 최근 10일 주가 구간", [("0~20% (현행)", B0 & P.ret10.between(0, 20)), ("0~10%", B0 & P.ret10.between(0, 10)),
      ("0~30%", B0 & P.ret10.between(0, 30)), ("-10~20%", B0 & P.ret10.between(-10, 20)),
      ("5~20%", B0 & P.ret10.between(5, 20)), ("10~30%", B0 & P.ret10.between(10, 30)),
      ("조건 없음", B0), ("하락(≤0)", B0 & (P.ret10 <= 0))])
show("⑥ 업종 상대강도", [(f"rs > {v}%", (P.quiet < 0.5) & (P.amt >= 50) & (P.ret10.between(0, 20)) & P.k20
                    & P.sr5.notna() & (P.sr5 < P.sr20) & P.rs.notna() & (P.rs > v)) for v in (-99, 0, 3, 5, 10)])
show("⑦ 기관·외국인 추가 조건", [("현행", BASE), ("+기관도 순매수", BASE & (P.owp > 0)),
      ("+기관 2%↑", BASE & (P.owp >= 2)), ("+외국인 20일도 2%↑", BASE & (P.fwp20 >= 2)),
      ("+유상증자 90일 제외", BASE & (~P.dil)), ("+코스피 5일선도 위", BASE & P.k5)])
show("⑧ 차트 위치", [("현행", BASE), ("+20일선 위", BASE & (P.dev20 > 0)), ("+60일선 위", BASE & (P.dev60 > 0)),
      ("+52주고가 -10% 이내", BASE & (P.nearhi > -10)), ("+52주고가 -30% 이하", BASE & (P.nearhi < -30)),
      ("+변동성 하위(vol20<3)", BASE & (P.vol20 < 3)), ("+3일 상승", BASE & (P.ret3 > 0)),
      ("+3일 하락", BASE & (P.ret3 <= 0))])
print("\n\n# 청산 규칙 (조건은 현행 고정)\n")
print("| 청산 | 건수 | **절대수익** | 중앙값 | 승률 | PF | 하락구간 | 학습 | 검증 | +연도 |")
print("|---|---|---|---|---|---|---|---|---|---|")
for h in (3, 5, 10, 15, 20, 40):
    for sl, tp in ((15, 30),):
        s = stat(BASE, h, sl, tp)
        print(f"| {h}일·손절15·익절30 | {s['n']} | **{s['ret']:+.2f}%** | {s['med']:+.2f}% | {s['win']:.0f}% | {s['pf']:.2f} | {s['dn']:+.2f}% | {s['is_']:+.2f}% | **{s['os_']:+.2f}%** | {s['pos']} |")
for sl, tp, lab in ((None, None, "손절·익절 없음"), (10, None, "손절10"), (15, None, "손절15"), (20, None, "손절20"),
                    (None, 20, "익절20"), (None, 30, "익절30"), (15, 20, "손절15·익절20"), (10, 30, "손절10·익절30"),
                    (20, 50, "손절20·익절50")):
    s = stat(BASE, 10, sl, tp)
    print(f"| 10일·{lab} | {s['n']} | **{s['ret']:+.2f}%** | {s['med']:+.2f}% | {s['win']:.0f}% | {s['pf']:.2f} | {s['dn']:+.2f}% | {s['is_']:+.2f}% | **{s['os_']:+.2f}%** | {s['pos']} |")
