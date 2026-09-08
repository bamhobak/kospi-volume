# -*- coding: utf-8 -*-
"""국내 차트 강의 2편(성승현·머니리포트) 실측 — 영상 oG_qNER4ELo 전사본에서 뽑은 매매법.

영상에서 실제로 '기법' 으로 못박아 말한 것만 고른다(전사본 문장번호 병기).
  M1 월봉 12평 돌파 매수 · 이탈 매도            (639) "패턴이고 나발이고 없이 이것만"
       · 판정은 **월말 종가** 기준, 장중 아님    (806~812)
       · 거래는 1년에 두세 번뿐이라 수수료 걱정 없다 (706)
       · 깨졌을 때 나가기만 하면 이후 하락은 안 겪는다 (588)
  M2 일봉 240평선(=242평) 지지 — 월봉 12평만큼 중요 (838)
  M3 240일선 지지 쌍바닥 → 12평 돌파            (822)
  M4 돌파 시 거래량 수반(몸통 길이에 비례)       (242, 547, 734)
  M5 박스권 상단 돌파에서 진입(박스 안 매매는 변동성 매매) (612)
  M6 12평 지지 + '몸통' 전고점 재돌파            (802)
  M7 지수가 12평/240 아래면 그 시장 신규매수 금지 (818)

M1 은 진입신호가 아니라 **보유 시스템**이라 우리 규칙 틀(고정 보유일)로는 못 잰다.
그래서 A 부(월 단위 포트폴리오 곡선, 항상보유와 머리맞대기)와 B 부(진입신호로 환산해
우리 게이트로 판정)를 따로 돌린다. 판정 기준은 늘 쓰던 것 —
학습 2016~22 / 검증 2023~26 / 유니버스 대비 초과 / 중앙값 / 월블록 CI.
"""
import io, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
import FinanceDataReader as fdr
import verdict

BASE = Path(__file__).parent
TR0, TR1, VA0 = "20160101", "20221231", "20230101"

def load(f, mk):
    K = pd.read_pickle(BASE / "data" / f).sort_values(["ticker", "date"]).reset_index(drop=True)
    K["mk"] = mk
    K["pref"] = ~K.ticker.str.endswith("0")
    g = K.groupby("ticker", sort=False)
    K["ma240"] = g.close.transform(lambda s: s.rolling(240, min_periods=240).mean())
    K["hi60p"] = g.high.transform(lambda s: s.rolling(60, min_periods=60).max().shift(1))
    K["body_hi"] = g.close.transform(lambda s: s.rolling(120, min_periods=60).max().shift(1))
    return K

KP = load("panel_kp.pkl", "KOSPI")
KQ = load("panel_kq.pkl", "KOSDAQ")

def base(K, amt=3):
    return ((~K.pref) & (K.close >= 1000) & (~K.dil.fillna(False)) & (K.amt20.fillna(0) >= amt))

# ══════════════════════════════════════════════════════════════════════
# A부. 월봉 12평 시스템 — 항상 보유와 머리 맞대기
# ══════════════════════════════════════════════════════════════════════
# 규칙: 월말 **종가**로 12개월 이평 위/아래를 판정하고, 그 판정으로 **다음 달**을 보유한다.
# 체결가는 월말 다음 거래일 시가(패널의 buy). 미리보기 없음.
def monthly(K):
    Z = K[base(K)].copy()
    Z["m"] = Z.date.str[:6]
    last = Z.groupby(["ticker", "m"], sort=False).tail(1).copy()
    last = last.sort_values(["ticker", "m"])
    g = last.groupby("ticker", sort=False)
    last["ma12"] = g.close.transform(lambda s: s.rolling(12, min_periods=12).mean())
    last["P"] = last.buy
    last["Pn"] = g.P.shift(-1)
    last["mret"] = (last.Pn / last.P - 1) * 100
    last["above"] = last.close > last.ma12
    last["mn"] = g.m.shift(-1)
    return last.dropna(subset=["mret", "ma12", "mn"])

def curve(M, cost=1.15):
    rows = []
    for mn, g in M.groupby("mn"):
        on = g[g.above]
        rows.append((mn, on.mret.mean() if len(on) else 0.0, g.mret.mean(), len(on), len(g)))
    C = pd.DataFrame(rows, columns=["m", "sys", "bh", "non", "nall"]).sort_values("m")
    sw = M.assign(prev=M.groupby("ticker").above.shift(1)).dropna(subset=["prev"])
    tr = sw.groupby("mn").apply(lambda g: (g.above != g.prev).mean() * cost)
    C["sys"] = C.sys - C.m.map(tr).fillna(0)
    return C

def mdd(c):
    v = (1 + c / 100).cumprod()
    return float((v / v.cummax() - 1).min() * 100)

print("=" * 104)
print("A부. 월봉 12평 시스템 — 돌파하면 매수, 깨지면 매도 (월말 종가 판정 · 다음날 시가 체결)")
print("=" * 104)
for K, mk in ((KP, "코스피"), (KQ, "코스닥")):
    M = monthly(K)
    C = curve(M)
    trn = M.assign(prev=M.groupby("ticker").above.shift(1)).dropna(subset=["prev"])
    per_yr = (trn.above != trn.prev).mean() * 12
    print(f"\n[{mk}] 월 {len(C)}개 · 보유비율 평균 {(C.non / C.nall).mean() * 100:.0f}% · "
          f"종목당 연 매매 {per_yr:.1f}회")
    for pn, lo, hi in (("학습 2016~22", "201601", "202212"), ("검증 2023~26", "202301", "209912"),
                       ("스트레스 2005~15", "200501", "201512"), ("전구간 2005~26", "200501", "209912")):
        z = C[(C.m >= lo) & (C.m <= hi)]
        if len(z) < 12:
            continue
        s = (1 + z.sys / 100).prod(); b = (1 + z.bh / 100).prod(); yr = len(z) / 12
        print(f"  {pn:<16} 12평 {s:>7.2f}배(연{(s ** (1 / yr) - 1) * 100:>6.1f}%) 낙폭{mdd(z.sys):>6.0f}%  |  "
              f"항상보유 {b:>7.2f}배(연{(b ** (1 / yr) - 1) * 100:>6.1f}%) 낙폭{mdd(z.bh):>6.0f}%  |  "
              f"월평균 초과 {z.sys.mean() - z.bh.mean():+.2f}%p")
    yz = C.assign(y=C.m.str[:4]).groupby("y").agg(
        s=("sys", lambda x: ((1 + x / 100).prod() - 1) * 100),
        b=("bh", lambda x: ((1 + x / 100).prod() - 1) * 100))
    print("  연도별 (12평 / 항상보유, %)")
    print("   " + "  ".join(f"{i}:{r.s:+.0f}/{r.b:+.0f}" for i, r in yz.iterrows()))

# ══════════════════════════════════════════════════════════════════════
# B부. 진입신호로 환산 — 우리 게이트로 판정
# ══════════════════════════════════════════════════════════════════════
HS = [5, 20, 60]
UNI = {}
for K in (KP, KQ):
    for h in HS:
        UNI[(id(K), h)] = K.dropna(subset=[f"n{h}"]).groupby("date")[f"n{h}"].mean()

def dedup(K, m, h):
    X = K[m.fillna(False)].dropna(subset=[f"n{h}"]).copy()
    di = {d: i for i, d in enumerate(sorted(K.date.unique()))}
    X["di"] = X.date.map(di)
    X = X.sort_values("di")
    keep, last = [], {}
    for t, i, ix in zip(X.ticker.values, X.di.values, X.index):
        if last.get(t, -10 ** 9) >= i:
            continue
        last[t] = i + h
        keep.append(ix)
    return X.loc[keep]

def report(K, name, m, h):
    X = dedup(K, m, h)
    X = X[X.date >= TR0]
    col = f"n{h}"
    if len(X) < 40:
        return f"  {name:<32}{len(X):>6}건  표본부족"
    X["ex"] = X[col] - X.date.map(UNI[(id(K), h)])
    tr = X[X.date <= TR1]; va = X[X.date >= VA0]
    mo = X.assign(mm=X.date.str[:6]).groupby("mm").ex.mean()
    ci = verdict.boot_ci(mo, 0.10)
    ly = X[X.date >= "20260101"].ex
    return (f"  {name:<32}{len(X):>6}건 초과{X.ex.mean():>+6.2f}%p 중앙{X.ex.median():>+6.2f} "
            f"승률{(X[col] > 0).mean() * 100:>3.0f}% | 학{tr.ex.mean():>+5.2f} 검{va.ex.mean():>+5.2f} "
            f"CI{ci:>+5.2f} | 26년{ly.mean() if len(ly) else float('nan'):>+5.2f}({len(ly)}건)")

def sigs(K):
    g = K.groupby("ticker", sort=False)
    c, ma = K.close, K.ma240
    above = c > ma
    prev = (g.close.shift(1) <= g.ma240.shift(1))
    near = (K.low <= ma * 1.03) & (c > ma)
    vol = K.su1 >= 1.5
    body = (c - K.open) / K.open * 100 >= 2
    box = c > K.hi60p
    dbl = (K.fromlo.fillna(0) <= 25) & near
    bhi = (c > K.body_hi) & above
    b = base(K)
    return {
        "M2 240일선 상향돌파": b & above & prev,
        "M2 240일선 돌파+거래량1.5": b & above & prev & vol,
        "M2 240일선 지지(언저리)": b & near,
        "M3 저점권 240 지지(쌍바닥)": b & dbl,
        "M4 240돌파+장대양봉+거래량": b & above & prev & vol & body,
        "M5 박스(60일) 상단 돌파": b & box,
        "M5 박스돌파 + 240 위": b & box & above,
        "M5 박스돌파+240위+거래량": b & box & above & vol,
        "M6 몸통 전고점 재돌파+240위": b & bhi,
        "M6 전고점재돌파+거래량1.5": b & bhi & vol,
        "참고 240 아래(반대편)": b & (~above) & c.notna() & ma.notna(),
    }

print("\n" + "=" * 104)
print("B부. 진입신호 환산 — 유니버스 대비 초과(2016~) · 학습/검증 · 월블록 CI 하한")
print("=" * 104)
NTRIAL = 0
for K, mk in ((KP, "코스피"), (KQ, "코스닥")):
    S = sigs(K)
    for h in HS:
        print(f"\n[{mk}] 보유 {h}일")
        for nm, m in S.items():
            NTRIAL += 1
            print(report(K, nm, m, h))

# ══════════════════════════════════════════════════════════════════════
# C부. M7 지수 게이트
# ══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 104)
print("C부. M7 지수 게이트 — 지수 240일선 위/아래에서 유니버스가 어떻게 다른가 (2016~)")
print("=" * 104)
for code, mk, K in (("KS11", "코스피", KP), ("KQ11", "코스닥", KQ)):
    IX = fdr.DataReader(code, "2004-01-01")
    IX = IX[IX.Close > 0].copy()
    IX["date"] = IX.index.strftime("%Y%m%d")
    IX["ma240"] = IX.Close.rolling(240).mean()
    up = dict(zip(IX.date, IX.Close > IX.ma240))
    K["ixup"] = K.date.map(up)
    for h in HS:
        U = K[K.date >= TR0].dropna(subset=[f"n{h}", "ixup"])
        a = U[U.ixup][f"n{h}"]; d = U[~U.ixup][f"n{h}"]
        print(f"  {mk} {h:>2}일  지수240위 {a.mean():>+6.2f}%(중앙{a.median():>+6.2f}, {len(a):>8,}) | "
              f"240아래 {d.mean():>+6.2f}%(중앙{d.median():>+6.2f}, {len(d):>8,}) | 차 {a.mean() - d.mean():>+5.2f}%p")

verdict.log_trials("chart_basic2(강의2편)", NTRIAL)
print(f"\n시험 조합 {NTRIAL}개 기록 · 누적 {verdict.trial_count():,}개")
