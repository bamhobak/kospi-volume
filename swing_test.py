# -*- coding: utf-8 -*-
"""스윙매매 기법 실측 — 2단계: 기법별 테스트
   매수 = 신호 다음날 시가 / 청산 = 보유기간·손절·익절·트레일링 (일중 경로 반영)
   폐지 종목은 보유 중 거래 종료 시 마지막 종가로 청산
"""
import io, sys, time
import numpy as np, pandas as pd
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
T0 = time.time()
def log(m): print(f"[{time.time()-T0:4.0f}s] {m}", flush=True)

D = pd.read_pickle("data/swing.pkl")
D = D[~D.bad].reset_index(drop=True)
log(f"{len(D):,}행 · {D.ticker.nunique()}종목")

# ── 종목별 경로 배열 (청산 시뮬레이션용) ─────────────────────
TK = D.ticker.values
order = np.argsort(TK, kind="stable")
D = D.iloc[order].reset_index(drop=True)
tk = D.ticker.values
starts = {}
u, idx0 = np.unique(tk, return_index=True)
for t, i in zip(u, idx0): starts[t] = i
ends = {}
for t, i in zip(u, np.append(idx0[1:], len(tk))): ends[t] = i
OP, HI, LO, CL = D.open.values.astype(float), D.high.values.astype(float), D.low.values.astype(float), D.close.values.astype(float)
ROW = np.arange(len(D))
LOC = ROW - np.array([starts[t] for t in tk])            # 종목 내 위치
LEN = np.array([ends[t] - starts[t] for t in tk])        # 종목 길이
BASE0 = np.array([starts[t] for t in tk])
COST = D.cost.values; YR = D.y.values; ATR = D.atr.values

def simulate(sig, hold=10, stop=None, target=None, trail=None, stop_atr=None):
    """sig = 불리언 마스크. 다음날 시가 매수, hold 거래일 보유.
       stop/target = % (예 -8, 20) · trail = 고점대비 % 하락 시 청산 · stop_atr = ATR 배수 손절"""
    s = np.flatnonzero(sig)
    s = s[LOC[s] + 1 < LEN[s]]                            # 다음날이 있어야 매수 가능
    if len(s) == 0: return None
    buy = OP[s + 1]
    ok = buy > 0
    s, buy = s[ok], buy[ok]
    n = len(s)
    out = np.empty(n)
    for k in range(n):
        i, b = s[k], buy[k]
        last = BASE0[i] + LEN[i] - 1
        end = min(i + hold, last)
        st = b * (1 + stop / 100) if stop is not None else None
        if stop_atr is not None and np.isfinite(ATR[i]): st = b - stop_atr * ATR[i]
        tg = b * (1 + target / 100) if target is not None else None
        peak = b; res = None
        for j in range(i + 1, end + 1):
            if st is not None and LO[j] <= st: res = (st / b - 1) * 100; break
            if tg is not None and HI[j] >= tg: res = (tg / b - 1) * 100; break
            if trail is not None:
                peak = max(peak, HI[j])
                tl = peak * (1 - trail / 100)
                if LO[j] <= tl and peak > b: res = (tl / b - 1) * 100; break

        if res is None: res = (CL[end] / b - 1) * 100
        out[k] = res
    return dict(r=out - COST[s], y=YR[s], i=s)

def stat(res, mn=30):
    if res is None or len(res["r"]) < mn: return None
    r, y = res["r"], res["y"]
    ism, osm = r[y <= 2022], r[y >= 2023]
    if len(ism) < 5 or len(osm) < 5: return None
    rs = np.sort(r)
    yy = pd.Series(r).groupby(y).agg(["mean", "size"]); yy = yy[yy["size"] >= 3]
    return dict(n=len(r), ret=r.mean(), med=np.median(r), win=(r > 0).mean() * 100,
                pf=(r[r > 0].sum() / abs(r[r <= 0].sum())) if (r <= 0).any() else 99.,
                is_=ism.mean(), os_=osm.mean(), t5=rs[:-5].mean() if len(rs) > 5 else np.nan,
                pos=int((yy["mean"] > 0).sum()), ny=len(yy), worst=r.min(), tot=r.sum() / 100 * 3_000_000)

HDR = ("| 기법 | 신호 | 절대수익 | 중앙값 | 승률 | PF | 상위5제외 | 학습(~22) | 검증(23~) | +연도 | 최악 | 300만씩 |\n"
       "|---|---|---|---|---|---|---|---|---|---|---|---|")
def row(lab, res):
    s = stat(res)
    if not s: return print(f"| {lab} | {0 if res is None else len(res['r'])} | 부족 |" + " - |" * 9)
    print(f"| {lab} | {s['n']} | **{s['ret']:+.2f}%** | {s['med']:+.2f}% | {s['win']:.0f}% | {s['pf']:.2f} | "
          f"{s['t5']:+.2f}% | {s['is_']:+.2f}% | **{s['os_']:+.2f}%** | {s['pos']}/{s['ny']} | {s['worst']:+.0f}% | "
          f"{s['tot']/10000:+,.0f}만 |")

LIQ = (D.amt20 >= 10) & (D.srd.notna())     # 최소 유동성 (하루 10억)
print(f"\n유동성 통과 {int(LIQ.sum()):,}행\n")

# ═══ ① 저점 반등 ═══════════════════════════════════════════
print("## ① 저점 찍고 반등 (10일 보유)\n"); print(HDR)
for lab, m in [
    ("120일 신저가 당일", LIQ & D.newlo120),
    ("120일 신저가 후 양봉 전환", LIQ & (D.newlo120.groupby(D.ticker).shift(1) == True) & (D.body > 0)),
    ("240일 신저가 + 아랫꼬리(50%↑)", LIQ & D.newlo240 & (D.lwick >= 0.5)),
    ("120일 저점 +5% 이내 + 양봉", LIQ & (D.fromlo120 <= 0.05) & (D.body > 1)),
    ("120일 저점권 + 거래량 3배", LIQ & (D.fromlo120 <= 0.05) & (D.vr20 >= 3)),
    ("120일 저점권 + 거래량 3배 + 종가 상단(0.7↑)", LIQ & (D.fromlo120 <= 0.05) & (D.vr20 >= 3) & (D.clpos >= 0.7)),
    ("쌍바닥(60일저점 재확인 ±3%) + 반등", LIQ & (D.fromlo60.abs() <= 0.03) & (D.fromlo120 > 0.02) & (D.body > 1) & (D.vr20 >= 2)),
]: row(lab, simulate(m.values, hold=10))

# ═══ ② 거래량 폭발 ═════════════════════════════════════════
print("\n## ② 거래량 폭발 (10일 보유)\n"); print(HDR)
for lab, m in [
    ("거래량 3배 + 양봉", LIQ & (D.vr20 >= 3) & (D.body > 0)),
    ("거래량 5배 + 양봉", LIQ & (D.vr20 >= 5) & (D.body > 0)),
    ("거래량 5배 + 장대양봉(5%↑)", LIQ & (D.vr20 >= 5) & (D.body >= 5)),
    ("60일 신고 거래량 + 양봉", LIQ & (D.vmax60 >= 1) & (D.body > 0)),
    ("거래량 말랐다가(5/60<0.6) 5배 폭발", LIQ & (D.vdry < 0.6) & (D.vr20 >= 5) & (D.body > 0)),
    ("거래량 5배 + 양봉 + 하락구간(60일 -20%↓)", LIQ & (D.vr20 >= 5) & (D.body > 0) & (D.run60 <= -20)),
    ("거래량 5배 + 양봉 + 상승구간(60일 +20%↑)", LIQ & (D.vr20 >= 5) & (D.body > 0) & (D.run60 >= 20)),
]: row(lab, simulate(m.values, hold=10))

# ═══ ③ 선 돌파 ═════════════════════════════════════════════
print("\n## ③ 선 돌파 (10일 보유)\n"); print(HDR)
for lab, m in [
    ("60일 전고점 돌파", LIQ & D.brk60),
    ("60일 전고점 돌파 + 거래량 2배", LIQ & D.brk60 & (D.vr20 >= 2)),
    ("120일 전고점 돌파 + 거래량 2배", LIQ & D.brk120 & (D.vr20 >= 2)),
    ("240일 전고점 돌파 + 거래량 2배", LIQ & D.brk240 & (D.vr20 >= 2)),
    ("좁은 박스(60일폭<25%) 돌파 + 거래량 2배", LIQ & D.brk60 & (D.boxw60 < 0.25) & (D.vr20 >= 2)),
    ("60일선 상향돌파 + 거래량 2배", LIQ & (D.dev60 > 0) & (D.close.groupby(D.ticker).shift(1) <= D.ma60.groupby(D.ticker).shift(1)) & (D.vr20 >= 2)),
    ("120일선 상향돌파 + 거래량 2배", LIQ & (D.dev120 > 0) & (D.close.groupby(D.ticker).shift(1) <= D.ma120.groupby(D.ticker).shift(1)) & (D.vr20 >= 2)),
]: row(lab, simulate(m.values, hold=10))

# ═══ ④ 눌림목 ══════════════════════════════════════════════
print("\n## ④ 눌림목 (10일 보유)\n"); print(HDR)
for lab, m in [
    ("20일 +20%↑ 급등 후 20일선 눌림(±3%)", LIQ & (D.run20 >= 20) & (D.near20 <= 0.03)),
    ("20일 +20%↑ 후 고점대비 -10~-20% 눌림", LIQ & (D.run20 >= 20) & D.pull.between(-0.20, -0.10)),
    ("60일 +30%↑ 후 20일선 눌림 + 거래량 감소", LIQ & (D.run60 >= 30) & (D.near20 <= 0.03) & (D.vdry < 0.8)),
    ("정배열 + 5일선 눌림(±2%) + 양봉", LIQ & D.ma5_20 & D.ma20_60 & (D.near20 <= 0.05) & (D.body > 0)),
    ("피보 38.2% 되돌림 부근(0.55~0.68)", LIQ & D.fib.between(0.55, 0.68) & (D.run60 >= 20) & (D.body > 0)),
    ("피보 50% 되돌림 부근(0.45~0.55)", LIQ & D.fib.between(0.45, 0.55) & (D.run60 >= 20) & (D.body > 0)),
    ("눌림 + 거래량 급감(5/60<0.5) 후 양봉", LIQ & (D.run60 >= 20) & (D.vdry < 0.5) & (D.body > 1)),
]: row(lab, simulate(m.values, hold=10))

# ═══ ⑤ 주봉·월봉 ═══════════════════════════════════════════
print("\n## ⑤ 주봉·월봉 결합 (10일 보유)\n"); print(HDR)
BOT = LIQ & (D.fromlo120 <= 0.05) & (D.vr20 >= 3) & (D.body > 1)      # ①의 저점반등 기본형
for lab, m in [
    ("저점반등 기본형", BOT),
    ("+ 주봉 5주선 위", BOT & (D.w_above5 == True)),
    ("+ 주봉 5주선 아래", BOT & (D.w_above5 == False)),
    ("+ 주봉 양봉", BOT & (D.wup == True)),
    ("+ 주봉 거래량 1.5배", BOT & (D.wvr >= 1.5)),
    ("+ 월봉 6개월선 위", BOT & (D.m_above6 == True)),
    ("+ 월봉 6개월선 아래", BOT & (D.m_above6 == False)),
    ("+ 월봉 12개월선 아래", BOT & (D.m_above12 == False)),
]: row(lab, simulate(m.values, hold=10))

log("완료")
