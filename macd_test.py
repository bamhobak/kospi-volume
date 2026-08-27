"""MACD 두 전략 실측
전략1(추세추종): 200일선 위/아래로 추세 판단 → 200일선 지지·저항 + 과거 변곡점 일치 구간 → MACD 크로스 진입 → 손절=직전 변곡점, 목표=손익비 1:2
전략2(추세반전): 가격·MACD 각각 추세선(최근 스윙 2점) → MACD가 먼저 돌파 → 이후 가격이 돌파할 때 진입 → 동일 손절/목표
사용: python macd_test.py [종목수] [시작연도]
"""
import io, sys, pickle, statistics
from pathlib import Path
import numpy as np, pandas as pd
import FinanceDataReader as fdr

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
BASE = Path(__file__).parent
N_UNIV = int(sys.argv[1]) if len(sys.argv) > 1 else 200
Y0 = sys.argv[2] if len(sys.argv) > 2 else "2023-01-01"
PIVOT = 5          # 변곡점 확인 봉수(좌우)
NEAR = 3.0         # 이평선/과거변곡점 근접 허용 %
RR = 2.0           # 손익비
MAXBARS = 40       # 시간 청산
CACHE = BASE / "data" / "macd_ohlc.pkl"

lst = fdr.StockListing("KOSPI")
lst = lst[lst["Code"].str.endswith("0")].sort_values("Amount", ascending=False).head(N_UNIV)
codes = list(zip(lst["Code"], lst["Name"]))
print(f"유니버스 {len(codes)}종목 (거래대금 상위) · 기간 {Y0}~2026-08-28", file=sys.stderr)

cache = pickle.load(open(CACHE, "rb")) if CACHE.exists() else {}
for i, (c, n) in enumerate(codes):
    if c not in cache:
        try: cache[c] = fdr.DataReader(c, "2021-06-01", "2026-08-28")
        except Exception: cache[c] = pd.DataFrame()
        if i % 50 == 0: pickle.dump(cache, open(CACHE, "wb")); print(f"  가격 {i}/{len(codes)}", file=sys.stderr)
pickle.dump(cache, open(CACHE, "wb"))

def prep(d):
    d = d.copy()
    e12 = d["Close"].ewm(span=12, adjust=False).mean(); e26 = d["Close"].ewm(span=26, adjust=False).mean()
    d["macd"] = e12 - e26
    d["sig"] = d["macd"].ewm(span=9, adjust=False).mean()
    d["ma200"] = d["Close"].rolling(200).mean()
    return d

def swings(arr_hi, arr_lo, L=PIVOT):
    """확정 스윙: i는 i+L 시점에 확정 → (확정시점, 인덱스, 값) 리스트"""
    hi, lo = [], []
    n = len(arr_hi)
    for i in range(L, n - L):
        if arr_hi[i] == max(arr_hi[i - L:i + L + 1]): hi.append((i + L, i, arr_hi[i]))
        if arr_lo[i] == min(arr_lo[i - L:i + L + 1]): lo.append((i + L, i, arr_lo[i]))
    return hi, lo

def simulate(d, i_entry, direction, stop, target):
    """i_entry 시가 진입 → 손절/목표/시간청산. 반환 (수익률%, 결과)"""
    if i_entry >= len(d): return None
    o = d["Open"].iloc[i_entry]
    if o <= 0: return None
    for k in range(i_entry, min(i_entry + MAXBARS, len(d))):
        lo, hi = d["Low"].iloc[k], d["High"].iloc[k]
        if direction > 0:
            if lo <= stop: return ((stop / o - 1) * 100, "손절")
            if hi >= target: return ((target / o - 1) * 100, "목표")
        else:
            if hi >= stop: return ((o / stop - 1) * 100, "손절")
            if lo <= target: return ((o / target - 1) * 100, "목표")
    c = d["Close"].iloc[min(i_entry + MAXBARS, len(d)) - 1]
    return (((c / o - 1) if direction > 0 else (o / c - 1)) * 100, "시간")

trades1, trades2 = [], []
for code, name in codes:
    d = cache.get(code)
    if d is None or len(d) < 300: continue
    d = prep(d)
    H, L, C = d["High"].values, d["Low"].values, d["Close"].values
    M, S, MA = d["macd"].values, d["sig"].values, d["ma200"].values
    sw_hi, sw_lo = swings(H, L)
    mh, ml = swings(M, M)          # MACD 스윙(고점/저점)
    dates = d.index
    start = np.searchsorted(dates, pd.Timestamp(Y0))
    last_exit1 = last_exit2 = -99

    for i in range(max(start, 210), len(d) - 1):
        conf_lo = [(j, v) for (t, j, v) in sw_lo if t <= i]
        conf_hi = [(j, v) for (t, j, v) in sw_hi if t <= i]
        if len(conf_lo) < 2 or len(conf_hi) < 2 or np.isnan(MA[i]): continue

        # ---------- 전략1: 추세추종 ----------
        if i - last_exit1 >= 5:
            cross_up = M[i] > S[i] and M[i - 1] <= S[i - 1]
            cross_dn = M[i] < S[i] and M[i - 1] >= S[i - 1]
            near_ma = abs(min(L[i - 2:i + 1]) / MA[i] - 1) * 100 <= NEAR
            near_ma_r = abs(max(H[i - 2:i + 1]) / MA[i] - 1) * 100 <= NEAR
            if C[i] > MA[i] and cross_up and near_ma:
                # 과거 변곡점(저점) 일치 확인
                past = [v for (j, v) in conf_lo if i - 120 <= j <= i - PIVOT and abs(v / C[i] - 1) * 100 <= NEAR]
                stop = max([v for (j, v) in conf_lo if j <= i - PIVOT and v < C[i]] or [0])
                if past and stop > 0:
                    o_next = d["Open"].iloc[i + 1]
                    if o_next > stop:
                        tgt = o_next + RR * (o_next - stop)
                        r = simulate(d, i + 1, +1, stop, tgt)
                        if r: trades1.append(dict(code=code, n=name, d=dates[i].strftime("%Y%m%d"), dir="L", ret=r[0], how=r[1],
                                                  risk=(o_next - stop) / o_next * 100)); last_exit1 = i
            elif C[i] < MA[i] and cross_dn and near_ma_r:
                past = [v for (j, v) in conf_hi if i - 120 <= j <= i - PIVOT and abs(v / C[i] - 1) * 100 <= NEAR]
                stop = min([v for (j, v) in conf_hi if j <= i - PIVOT and v > C[i]] or [1e18])
                if past and stop < 1e17:
                    o_next = d["Open"].iloc[i + 1]
                    if o_next < stop and o_next > 0:
                        tgt = o_next - RR * (stop - o_next)
                        r = simulate(d, i + 1, -1, stop, tgt)
                        if r: trades2 if False else trades1.append(dict(code=code, n=name, d=dates[i].strftime("%Y%m%d"), dir="S", ret=r[0], how=r[1],
                                                                       risk=(stop - o_next) / o_next * 100)); last_exit1 = i

        # ---------- 전략2: 추세반전 ----------
        if i - last_exit2 >= 5:
            ph = [(j, v) for (t, j, v) in sw_hi if t <= i][-2:]
            mhi = [(j, v) for (t, j, v) in mh if t <= i][-2:]
            if len(ph) == 2 and len(mhi) == 2 and ph[1][1] < ph[0][1] and mhi[1][1] < mhi[0][1]:
                # 하락 추세선(고점 2개) — 반등 롱
                def line(p, x):
                    (x1, y1), (x2, y2) = p
                    return y1 + (y2 - y1) * (x - x1) / max(1, (x2 - x1))
                mbreak = None
                for k in range(max(mhi[1][0] + 1, i - 15), i + 1):
                    if M[k] > line(mhi, k): mbreak = k; break
                if mbreak is not None and mbreak < i:
                    if C[i] > line(ph, i) and C[i - 1] <= line(ph, i - 1):
                        stop = min(L[mbreak:i + 1])
                        o_next = d["Open"].iloc[i + 1]
                        if o_next > stop > 0:
                            tgt = o_next + RR * (o_next - stop)
                            r = simulate(d, i + 1, +1, stop, tgt)
                            if r: trades2.append(dict(code=code, n=name, d=dates[i].strftime("%Y%m%d"), dir="L", ret=r[0], how=r[1],
                                                      risk=(o_next - stop) / o_next * 100)); last_exit2 = i
            pl = [(j, v) for (t, j, v) in sw_lo if t <= i][-2:]
            mlo = [(j, v) for (t, j, v) in ml if t <= i][-2:]
            if len(pl) == 2 and len(mlo) == 2 and pl[1][1] > pl[0][1] and mlo[1][1] > mlo[0][1]:
                def line(p, x):
                    (x1, y1), (x2, y2) = p
                    return y1 + (y2 - y1) * (x - x1) / max(1, (x2 - x1))
                mbreak = None
                for k in range(max(mlo[1][0] + 1, i - 15), i + 1):
                    if M[k] < line(mlo, k): mbreak = k; break
                if mbreak is not None and mbreak < i:
                    if C[i] < line(pl, i) and C[i - 1] >= line(pl, i - 1):
                        stop = max(H[mbreak:i + 1])
                        o_next = d["Open"].iloc[i + 1]
                        if 0 < o_next < stop:
                            tgt = o_next - RR * (stop - o_next)
                            r = simulate(d, i + 1, -1, stop, tgt)
                            if r: trades2.append(dict(code=code, n=name, d=dates[i].strftime("%Y%m%d"), dir="S", ret=r[0], how=r[1],
                                                      risk=(stop - o_next) / o_next * 100)); last_exit2 = i

def report(title, tr):
    print(f"\n## {title}\n")
    if len(tr) < 5: print(f"거래 {len(tr)}건 — 표본부족\n"); return
    df = pd.DataFrame(tr)
    def st(g):
        if len(g) == 0: return "-"
        return f"{g['ret'].mean():+.2f}% / {(g['ret'] > 0).mean() * 100:.0f}% ({len(g)}건)"
    print(f"**전체 {len(df)}건 · 평균 {df['ret'].mean():+.2f}% · 승률 {(df['ret'] > 0).mean() * 100:.0f}% · 중앙값 {df['ret'].median():+.2f}% · 평균손실폭 {df['risk'].mean():.1f}%**\n")
    print("| 구분 | 전체 | 롱 | 숏 |\n|---|---|---|---|")
    print(f"| 성과 | {st(df)} | {st(df[df['dir'] == 'L'])} | {st(df[df['dir'] == 'S'])} |")
    print("\n| 청산 사유 | 건수 | 비중 | 평균 |\n|---|---|---|---|")
    for how, g in df.groupby("how"): print(f"| {how} | {len(g)} | {len(g) / len(df) * 100:.0f}% | {g['ret'].mean():+.2f}% |")
    df["y"] = df["d"].str[:4]
    print("\n| 연도 | 건수 | 평균 | 승률 |\n|---|---|---|---|")
    for y, g in df.groupby("y"): print(f"| {y} | {len(g)} | {g['ret'].mean():+.2f}% | {(g['ret'] > 0).mean() * 100:.0f}% |")
    print(f"\n기대값(손익비 반영): 승률 {(df['ret'] > 0).mean() * 100:.0f}% × 평균이익 {df[df['ret'] > 0]['ret'].mean():+.1f}% / 패율 {(df['ret'] <= 0).mean() * 100:.0f}% × 평균손실 {df[df['ret'] <= 0]['ret'].mean():+.1f}%")

print(f"# MACD 전략 실측 — KOSPI 거래대금 상위 {N_UNIV}종목, {Y0}~2026-08\n")
print(f"공통 규칙: 신호 다음날 시가 진입 · 손절=직전 변곡점 · 목표=손익비 1:{RR:.0f} · {MAXBARS}봉 초과 시 시간청산 · 변곡점 확인 {PIVOT}봉")
report("전략1 · 추세추종 (200일선 + 변곡점 일치 + MACD 크로스)", trades1)
report("전략2 · 추세반전 (MACD 추세선 선행 돌파 → 가격 추세선 돌파)", trades2)
