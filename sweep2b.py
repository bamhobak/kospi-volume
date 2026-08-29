# -*- coding: utf-8 -*-
"""2번 필터 다각도 스윕 — 절대수익 기준 · 학습(19~22)/검증(23~26) 분리"""
import io, sys
import numpy as np, pandas as pd
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
P = pd.read_pickle("data/p1.pkl")
Hp = np.load("data/p1_H.npy"); Lp = np.load("data/p1_L.npy"); Cp = np.load("data/p1_C.npy")
MKT = np.load("data/p1_MKT.npy")
AMT = P.amt.values
COSTV = 0.18 + np.select([AMT >= 100, AMT >= 50, AMT >= 20, AMT >= 10], [0.20, 0.30, 0.50, 0.70], default=1.00)
GP = P.gp.values.astype(int); N = len(P)
SRD = P.sr5.notna() & P.sr20.notna() & (P.sr5 < P.sr20)

def rets(h, sl=None, tp=None):
    Lm = Lp[:, :h+1]; Hm = Hp[:, :h+1]
    ks = np.where((Lm <= -sl).any(1), (Lm <= -sl).argmax(1), 999) if sl else np.full(N, 999)
    kt = np.where((Hm >= tp).any(1), (Hm >= tp).argmax(1), 999) if tp else np.full(N, 999)
    kk = np.minimum(np.minimum(ks, kt), h)
    r = Cp[np.arange(N), kk].astype(float)
    if sl is not None: r = np.where(ks <= np.minimum(kt, h), -float(sl), r)
    if tp is not None: r = np.where((kt < ks) & (kt <= h), float(tp), r)
    return r - COSTV, kk
def stat(m, h=10, sl=None, tp=None, mn=15):
    mv = m.values if hasattr(m, "values") else m
    if mv.sum() < mn: return None
    r, kk = rets(h, sl, tp); r = r[mv]; y = P.y.values[mv]
    mk = MKT[GP[mv], np.clip(kk[mv], 0, MKT.shape[1]-1)]
    dn = r[mk <= 0]
    yy = pd.Series(r).groupby(y).mean(); cnt = pd.Series(r).groupby(y).size(); ok = yy[cnt >= 3]
    return dict(n=len(r), ret=r.mean(), med=float(np.median(r)), win=(r > 0).mean()*100,
                pf=(r[r > 0].sum()/abs(r[r <= 0].sum())) if (r <= 0).any() else 99,
                pos=f"{(ok>0).sum()}/{len(ok)}", is_=r[y <= 2022].mean(), os_=r[y >= 2023].mean(),
                dn=dn.mean() if len(dn) else np.nan, ndn=len(dn), r=r, y=y)
def show(title, rows, h=10, sl=None, tp=None):
    print(f"\n## {title}\n")
    print("| 설정 | 건수 | **절대수익** | 중앙값 | 승률 | PF | 하락구간 | 학습 | 검증 | +연도 |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for lab, m in rows:
        s = stat(m, h, sl, tp)
        if not s: print(f"| {lab} | 부족 |" + " - |" * 8); continue
        print(f"| {lab} | {s['n']} | **{s['ret']:+.2f}%** | {s['med']:+.2f}% | {s['win']:.0f}% | {s['pf']:.2f} | "
              f"{s['dn']:+.2f}%({s['ndn']}) | {s['is_']:+.2f}% | **{s['os_']:+.2f}%** | {s['pos']} |")

B = (P.quiet < 0.3) & (P.amt >= 3) & (P.ret3 <= -5) & SRD & (~P.dil)
print(f"# 2번 필터 다각도 스윕 (현행 {int(B.sum())}건)")
NOQ = (P.amt >= 3) & (P.ret3 <= -5) & SRD & (~P.dil)
NOA = (P.quiet < 0.3) & (P.ret3 <= -5) & SRD & (~P.dil)
NOR = (P.quiet < 0.3) & (P.amt >= 3) & SRD & (~P.dil)
show("① 외국인 5일 비중", [(f"외인 {v}%↑", B & (P.fwp >= v)) for v in (2, 3, 5, 7, 10)])
show("② 급등 배율", [(f"급등 {v}배↑", B & (P.surge >= v)) for v in (2, 2.5, 3, 4, 5)])
show("③ 잠잠도", [(f"잠잠 <{v}", NOQ & (P.quiet < v)) for v in (0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5)])
show("④ 거래대금", [(f"{v}억↑", NOA & (P.amt >= v)) for v in (1, 3, 5, 10, 30, 50)])
show("⑤ 3일 급락 폭", [(f"3일 {v}%↓", NOR & (P.ret3 <= v)) for v in (0, -3, -5, -7, -10, -15)])
show("⑥ 중기 주가", [("조건 없음", B), ("10일도 하락", B & (P.ret10 <= 0)), ("10일 상승", B & (P.ret10 > 0)),
      ("20일 하락", B & (P.ret20 <= 0)), ("20일 -20%↓", B & (P.ret20 <= -20)), ("20일 상승", B & (P.ret20 > 0))])
show("⑦ 시장 국면", [("조건 없음", B), ("코스피 20일선 위", B & P.k20), ("코스피 20일선 아래", B & ~P.k20),
      ("코스피 5일선 위", B & P.k5), ("5일선·20일선 둘 다 위", B & P.k5 & P.k20)])
show("⑧ 수급·공매도", [("현행", B), ("+기관도 순매수", B & (P.owp > 0)), ("+기관 2%↑", B & (P.owp >= 2)),
      ("+외국인 20일도 플러스", B & (P.fwp20 > 0)), ("공매도 조건 제거", (P.quiet < 0.3) & (P.amt >= 3) & (P.ret3 <= -5) & (~P.dil)),
      ("+공매도 비중 5% 미만", B & (P.sr5 < 5)), ("+공매도 감소폭 1%p↑", B & ((P.sr20 - P.sr5) >= 1)),
      ("유상증자 제외 안함", (P.quiet < 0.3) & (P.amt >= 3) & (P.ret3 <= -5) & SRD)])
show("⑨ 차트 위치·변동성", [("현행", B), ("+20일선 아래", B & (P.dev20 < 0)), ("+60일선 아래", B & (P.dev60 < 0)),
      ("+52주고가 -30% 이하", B & (P.nearhi < -30)), ("+52주고가 -50% 이하", B & (P.nearhi < -50)),
      ("+변동성 vol20<4", B & (P.vol20 < 4)), ("+변동성 vol20>=4", B & (P.vol20 >= 4))])
print("\n\n# 청산 규칙 (조건 현행 고정)\n")
print("| 청산 | 건수 | **절대수익** | 중앙값 | 승률 | PF | 하락구간 | 학습 | 검증 | +연도 |")
print("|---|---|---|---|---|---|---|---|---|---|")
for h in (3, 5, 10, 15, 20, 40):
    s = stat(B, h)
    print(f"| {h}일 (손절·익절 없음) | {s['n']} | **{s['ret']:+.2f}%** | {s['med']:+.2f}% | {s['win']:.0f}% | {s['pf']:.2f} | {s['dn']:+.2f}% | {s['is_']:+.2f}% | **{s['os_']:+.2f}%** | {s['pos']} |")
for sl, tp, lab in ((10, None, "손절10"), (15, None, "손절15"), (20, None, "손절20"),
                    (None, 15, "익절15"), (None, 20, "익절20"), (None, 30, "익절30"), (None, 50, "익절50"),
                    (15, 30, "손절15·익절30"), (20, 50, "손절20·익절50")):
    s = stat(B, 10, sl, tp)
    print(f"| 10일·{lab} | {s['n']} | **{s['ret']:+.2f}%** | {s['med']:+.2f}% | {s['win']:.0f}% | {s['pf']:.2f} | {s['dn']:+.2f}% | {s['is_']:+.2f}% | **{s['os_']:+.2f}%** | {s['pos']} |")
