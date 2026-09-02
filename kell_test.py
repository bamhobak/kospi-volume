# -*- coding: utf-8 -*-
"""올리버 켈(2020 US Investing Championship 941%) 전략 실측 — 한국 시장.

원 전략(영상은 나스닥 15분봉):
  진입 — 하락하던 가격이 반등해 10EMA·20EMA 위에서 종가 마감 · 두 EMA 가 좁게 수렴 ·
         종가가 VWAP 위
  유지 — 20EMA 위에 있는 한 보유
  청산 — 종가가 20EMA 아래로 마감하면 전량 매도
  손절 — 반등 직전 저점 이탈

일봉으로 옮기며 불가피한 근사 두 가지(결과 해석에 반드시 감안할 것):
  · VWAP 은 장중 개념이라 일봉엔 없다 → 20일 거래량가중평균가로 대체
    (sum(종가×거래량,20)/sum(거래량,20)). 원 지표와 같지 않다.
  · 15분봉 → 일봉이라 신호 빈도·보유기간의 성격이 달라진다.

청산이 동적이라(20EMA 이탈까지 보유) 고정보유 틀을 못 쓴다. 종목별로 경로를 걸어
청산일을 찾는다. 매수는 우리 규율대로 신호 다음날 시가, 비용 차감.
게이트 ✅ = 학습CI>0 & 붐제외CI>0 & 전체중앙>0 & 붐제외중앙>0 & 상위5%제거평균>0
"""
import io, sys, gc
from pathlib import Path
import numpy as np, pandas as pd
import FinanceDataReader as fdr

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
BASE = Path(__file__).parent
MAXHOLD = 120          # 20EMA 를 계속 안 깨면 무한정 들고 갈 수 없으므로 상한

IX = fdr.DataReader("KS11", "2017-01-01"); IX = IX[IX.Close > 0].copy()
IX["date"] = IX.index.strftime("%Y%m%d")
IX["dev60"] = (IX.Close / IX.Close.rolling(60).mean() - 1) * 100
DEV = dict(zip(IX.date, IX.dev60)); del IX; gc.collect()

COLS = ["ticker", "date", "open", "high", "low", "close", "volume",
        "buy", "cost", "dil", "amt20", "marcap"]

def prep(f, mk):
    K = pd.read_pickle(BASE / "data" / f)[COLS].copy()
    K = K.sort_values(["ticker", "date"]).reset_index(drop=True)
    K["mk"] = mk
    K["pref"] = ~K.ticker.str.endswith("0")
    g = K.groupby("ticker", sort=False)
    K["e10"] = g.close.transform(lambda s: s.ewm(span=10, adjust=False).mean())
    K["e20"] = g.close.transform(lambda s: s.ewm(span=20, adjust=False).mean())
    pv = K.close * K.volume
    K["vwap20"] = (pv.groupby(K.ticker).transform(lambda s: s.rolling(20).sum())
                   / g.volume.transform(lambda s: s.rolling(20).sum()))
    K["gap"] = (K.e10 - K.e20).abs() / K.close * 100          # 두 EMA 수렴도(%)
    K["pc"] = g.close.shift(1); K["pe20"] = g.e20.shift(1)
    K["lo10"] = g.low.transform(lambda s: s.rolling(10).min())  # 반등 직전 저점 근사
    K["ixdev"] = K.date.map(DEV)
    K["yr"] = K.date.str[:4]
    K["di"] = K.groupby("ticker").cumcount()
    return K

def boot(v, k, seed=127, n=2000):
    if len(v) < 25: return None
    rng = np.random.default_rng(seed)
    d = pd.DataFrame({"r": np.asarray(v), "ym": np.asarray(k)})
    by = {m: gg.r.to_numpy() for m, gg in d.groupby("ym")}; ms = list(by)
    if len(ms) < 3: return None
    return np.percentile([np.concatenate([by[x] for x in rng.choice(ms, len(ms), replace=True)]).mean()
                          for _ in range(n)], [2.5, 97.5])

def walk(K, sig, stop_pct=None, use_stop_low=True):
    """신호일 다음날 시가 매수 → 종가가 20EMA 아래로 마감하면 그날 종가 청산.
       손절: 반등 직전 저점(10일 최저) 이탈 시 그 가격에 청산."""
    out = []
    sigv = sig.fillna(False).values
    for tk, idx in K.groupby("ticker", sort=False).indices.items():
        c = K.close.values[idx]; e20 = K.e20.values[idx]; lo = K.low.values[idx]
        buy = K.buy.values[idx]; cost = K.cost.values[idx]
        lo10 = K.lo10.values[idx]; dt = K.date.values[idx]
        s = np.where(sigv[idx])[0]
        n = len(idx)
        for i in s:
            b = buy[i]
            if not (b == b) or b <= 0 or i + 1 >= n: continue
            floor = lo10[i] if use_stop_low else None
            hard = b * (1 - stop_pct / 100) if stop_pct else None
            ret = None
            for j in range(i + 1, min(i + 1 + MAXHOLD, n)):
                if floor == floor and floor and lo[j] <= floor:      # 직전 저점 이탈
                    ret = (floor / b - 1) * 100 - cost[i]; break
                if hard and lo[j] <= hard:
                    ret = -stop_pct - cost[i]; break
                if c[j] == c[j] and e20[j] == e20[j] and c[j] < e20[j]:  # 20EMA 종가 이탈
                    ret = (c[j] / b - 1) * 100 - cost[i]; break
            else:
                j = min(i + MAXHOLD, n - 1)
                ret = (c[j] / b - 1) * 100 - cost[i]
            out.append((dt[i], tk, ret, j - i))
    return pd.DataFrame(out, columns=["date", "ticker", "r", "hold"])

HDR = (f"  {'조건':<30} {'n':>5} {'평균':>7} {'승률':>5} {'중앙':>7} {'상5뺀':>7} "
       f"{'IS':>7} {'OS':>7} {'붐제외':>7} {'보유':>5} {'양수년':>5} {'학습CI':>13} {'붐제외CI':>13}")
def rep(Z, tag, dedup_days=None):
    if len(Z) == 0: print(f"  {tag:<30}    0 (없음)"); return None
    Z = Z.sort_values("date").copy()
    if dedup_days:                       # 같은 종목 중복 진입 제거
        keep, last = [], {}
        for t, d, ix in zip(Z.ticker.values, Z.date.values, Z.index):
            if last.get(t) and d <= last[t]: continue
            last[t] = d; keep.append(ix)
        Z = Z.loc[keep]
    if len(Z) < 30: print(f"  {tag:<30} {len(Z):>5} (부족)"); return None
    Z["yr"] = Z.date.str[:4]; Z["ym"] = Z.date.str[:6]
    zi, zo, nb = Z[Z.date < "20230101"], Z[Z.date >= "20230101"], Z[Z.yr < "2025"]
    ci, cn = boot(zi.r.values, zi.ym.values), boot(nb.r.values, nb.ym.values)
    cut = np.percentile(Z.r.values, 95); t5 = Z.r.values[Z.r.values <= cut].mean()
    med = float(np.median(Z.r)); mnb = float(np.median(nb.r)) if len(nb) else np.nan
    lo_ = ci[0] if ci is not None else np.nan; ln = cn[0] if cn is not None else np.nan
    ok = bool(lo_ > 0 and ln > 0 and med > 0 and mnb > 0 and t5 > 0)
    f = lambda x: f"[{x[0]:+.1f},{x[1]:+.1f}]" if x is not None else "-"
    yrs = Z.groupby("yr").r.mean()
    print(f"  {tag:<30} {len(Z):>5} {Z.r.mean():>+7.2f} {(Z.r>0).mean()*100:>4.0f}% {med:>+7.2f} "
          f"{t5:>+7.2f} {zi.r.mean():>+7.2f} {zo.r.mean() if len(zo) else np.nan:>+7.2f} "
          f"{nb.r.mean() if len(nb) else np.nan:>+7.2f} {Z.hold.mean():>5.1f} "
          f"{int((yrs>0).sum())}/{len(yrs):<2} {f(ci):>13} {f(cn):>13}{'  ✅' if ok else ''}")
    return dict(n=len(Z), r=Z.r.mean(), win=(Z.r > 0).mean()*100, Z=Z)

for f, mk in (("kp_ow.pkl", "KOSPI"), ("kq_ow.pkl", "KOSDAQ")):
    K = prep(f, mk)
    U = ((~K.pref) & (K.close >= 1000) & (~K.dil.fillna(False)) & (K.amt20.fillna(0) >= 30))
    # 진입: 어제는 20EMA 아래(하락/눌림) → 오늘 두 EMA 위에서 마감
    RECLAIM = (K.pc < K.pe20) & (K.close > K.e10) & (K.close > K.e20)
    VWAPOK = K.close > K.vwap20
    print(f"\n{'='*150}\n#### 켈 전략 {mk} — 20EMA 이탈 시 청산 (최대 {MAXHOLD}일)\n{'='*150}")
    print(f"## 0) 원안 그대로 (수렴 2% · VWAP 위 · 직전저점 손절)\n{HDR}")
    for reg, lab in ((K.ixdev > 5, "상승장"), (K.ixdev.abs() <= 5, "횡보장"),
                     (K.ixdev < -5, "하락장"), (K.ixdev == K.ixdev, "전국면")):
        sig = U & RECLAIM & VWAPOK & (K.gap <= 2) & reg
        Z = walk(K, sig)
        rep(Z, f"원안 · {lab}", dedup_days=True)

    print(f"\n## 1) 조건 하나씩 빼보기 (전국면)\n{HDR}")
    base = U & RECLAIM & (K.ixdev == K.ixdev)
    for tag, sig in (("원안(수렴2%+VWAP)", base & VWAPOK & (K.gap <= 2)),
                     ("VWAP 조건 제거", base & (K.gap <= 2)),
                     ("수렴 조건 제거", base & VWAPOK),
                     ("둘 다 제거(단순 20EMA 회복)", base)):
        rep(walk(K, sig), tag, dedup_days=True)

    print(f"\n## 2) 수렴 문턱·손절 방식\n{HDR}")
    for g_ in (1, 2, 3, 5):
        rep(walk(K, U & RECLAIM & VWAPOK & (K.gap <= g_)), f"수렴 ≤{g_}% (직전저점 손절)", dedup_days=True)
    rep(walk(K, U & RECLAIM & VWAPOK & (K.gap <= 2), use_stop_low=False),
        "손절 없음(20EMA만)", dedup_days=True)
    rep(walk(K, U & RECLAIM & VWAPOK & (K.gap <= 2), stop_pct=8, use_stop_low=False),
        "고정 -8% 손절", dedup_days=True)
    del K; gc.collect()

print("\n※ VWAP 은 일봉 근사(20일 거래량가중평균가)라 원 지표와 다르다.")
print("  15분봉 전략을 일봉으로 옮긴 것이므로 '원 전략의 검증'이 아니라 '같은 논리의 일봉판' 이다.")
