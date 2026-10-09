# -*- coding: utf-8 -*-
"""재료 사전 + 재료 만들기 — **과거 패널(kr_scan)과 매일 실시간 일봉(토스)에 같은 함수**를 쓴다.
그래야 과거 시험 성적과 그림자(앞으로 오는 날) 성적이 같은 잣대가 된다.

한 줄 = (종목, 거래일 t). 데이 매매 기준 — t 시가 단일가에 사서 t 종가 단일가에 판다(oc).
재료가 언제 알려지나(at):
  pre   어제(t-1) 종가까지 — 장 전에 확정
  open  t 시가(장전 예상체결가로 미리 보인다 — 실제 체결가와 조금 다르다)
  close t 종가 무렵(종가 단일가 15:20 가격으로 근사) — 밤샘(on: t 종가 매수 → t+1 시가 매도)만 쓴다
  live  과거가 없는 실시간 녹화 재료(장전 동시호가 등) — 정답지·그림자에만 쓴다
매매 방식(mode): oc 시가→종가 · on 종가→다음날 시가 · sw5/sw20 시가 매수 → 5/20거래일 뒤 종가(과거 패널 n5/n20, 비용 포함)
유니버스 = 그날 20일 평균 거래대금(어제까지) 상위 40% · 1,000원 이상 · 보통주. q_<재료> = 그날 유니버스 안 백분위(0~1).
"""
import numpy as np, pandas as pd

COST = 0.23            # 국장 왕복(수수료 0.015×2 + 거래세 0.20) — 단일가 체결 가정
SWH = (5, 10, 20, 40, 60)                  # 스윙 보유 거래일(2026-10-10 사용자: 스윙 기법도 같이)
MODES = {"oc": ("시가 매수 → 같은 날 종가 매도", {"pre", "open"}),
         "on": ("종가 매수 → 다음날 시가 매도", {"pre", "open", "close"})}
MODES.update({"sw%d" % h: ("시가 매수 → %d거래일 들고 종가 매도(스윙)" % h, {"pre", "open"}) for h in SWH})
MODES.update({"m10c": ("10:00 매수 → 같은 날 종가 매도(1분봉 2022-12~)", {"pre", "open", "i10"}),          # 2026-10-10 장중 방식
              "m14c": ("14:00 매수 → 같은 날 종가 매도(1분봉 2022-12~)", {"pre", "open", "i10", "i14"})})
TARGET = {m: m for m in MODES}
INTRA_SLIP = 0.05                          # 장중 시장가 매수 미끄러짐(단일가가 아니라서) — 비용에 더한다

# 이름: (설명, 언제, 뒤집을 때 성질, 언제부터)
#   성질: s = 0 기준 부호(값 → -값) · r = 1 기준 배수(값 → 1/값) · u = 0~1(값 → 1-값) · h = 0~100(값 → 100-값) · c = 그대로(부등호만 뒤집음)
FEATS = {
    "r1": ("어제 등락률 %", "pre", "s"), "r5": ("최근 5일 등락률 %", "pre", "s"), "r20": ("최근 20일 등락률 %", "pre", "s"),
    "r60": ("최근 60일 등락률 %", "pre", "s"),
    "clv": ("어제 종가 위치(고가=1·저가=0)", "pre", "u"), "rng": ("어제 고저폭 %", "pre", "c"),
    "vm": ("어제 거래량 ÷ 그 전 20일 평균(배)", "pre", "r"), "vm5": ("최근 5일 평균 거래량 ÷ 20일 평균(배)", "pre", "r"),
    "fh": ("어제 종가의 20일 고가 대비 %(0 이하)", "pre", "c"), "fl": ("어제 종가의 20일 저가 대비 %(0 이상)", "pre", "c"),
    "d5": ("어제 종가의 5일선 대비 %", "pre", "s"), "d20": ("어제 종가의 20일선 대비 %", "pre", "s"),
    "d60": ("어제 종가의 60일선 대비 %", "pre", "s"),
    "vol20": ("최근 20일 하루 등락 표준편차 %", "pre", "c"), "dn": ("어제까지 연속 하락 일수", "pre", "c"),
    "up": ("어제까지 연속 상승 일수", "pre", "c"),
    "amt20": ("20일 평균 거래대금(억원)", "pre", "c"), "liq": ("유니버스 안 거래대금 순위(0=가장 작음)", "pre", "u"),
    "px": ("어제 종가(원)", "pre", "c"),
    "mk_r1": ("시장(유니버스 중앙) 어제 등락 %", "pre", "s"), "mk_r5": ("시장 5일 등락 %", "pre", "s"),
    "fr": ("어제 외국인 순매수 ÷ 20일 평균 거래대금 %", "pre", "s"), "ir": ("어제 개인 순매수 ÷ 20일 평균 거래대금 %", "pre", "s"),
    "fr5": ("최근 5일 외국인 순매수 합 ÷ 20일 평균 거래대금 %", "pre", "s"),
    "th": ("속한 테마 중 가장 뜨거운 테마의 20일 수익 순위(0~1, 1=가장 뜨거움)", "pre", "u"),
    "us_ewy": ("밤사이 미장 EWY(한국 ETF) 등락 %", "pre", "s"), "tr_us": ("밤사이 그 종목 짝 미장 종목/ETF 등락 %", "pre", "s"),
    "tr_pred": ("밤사이 미장으로 본 예상 갭 %", "pre", "s"),
    "gap": ("오늘 시가 갭 %(시가 ÷ 어제 종가)", "open", "s"), "mgap": ("오늘 시장 갭(유니버스 중앙) %", "open", "s"),
    "rgap": ("오늘 갭 - 시장 갭 %p", "open", "s"), "tr_res": ("실제 갭 - 미장으로 본 예상 갭 %p", "open", "s"),
    "r1t": ("오늘 등락률 %(종가 무렵)", "close", "s"), "clvt": ("오늘 종가 위치", "close", "u"),
    "vmt": ("오늘 거래량 ÷ 20일 평균(배)", "close", "r"), "rngt": ("오늘 고저폭 %", "close", "c"),
    "oct": ("오늘 시가→종가 %", "close", "s"),
    # 2026-10-10 추가(사용자: 못 옮긴 조건 중 지금 자료로 만들 수 있는 건 재료로) — 전부 일봉으로 계산
    "hi250": ("어제 종가의 52주(250일) 고가 대비 %(0 이하, 0=신고가)", "pre", "c"),
    "lo250": ("어제 종가의 52주 저가 대비 %(0 이상)", "pre", "c"),
    "hi60": ("어제 종가의 60일 고가(전고점) 대비 %", "pre", "c"),
    "d120": ("어제 종가의 120일선 대비 %", "pre", "s"), "d224": ("어제 종가의 224일선 대비 %", "pre", "s"),
    "rsi14": ("RSI(14) 어제 값(0~100)", "pre", "h"), "bbp": ("볼린저(20,2) %b 어제 값(0=하단·1=상단)", "pre", "u"),
    "bbw": ("볼린저(20,2) 폭 %", "pre", "c"), "macd": ("MACD(12,26) 히스토그램 ÷ 종가 %", "pre", "s"),
    "ich": ("어제 종가의 일목 기준선(26일 고저 중간) 대비 %", "pre", "s"),
    "uw": ("어제 윗꼬리 비율(0~1)", "pre", "u"), "lw": ("어제 아랫꼬리 비율(0~1)", "pre", "u"),
    "body": ("어제 몸통 %(종가÷시가-1, 양봉 +)", "pre", "s"),
    "lu20": ("최근 20일 상한가(+29%↑ 마감) 횟수", "pre", "c"), "age": ("상장 후 거래일 수(250 이상은 250)", "pre", "c"),
    "mcap": ("시가총액(억원, 어제 종가)", "pre", "c"),
    "uwt": ("오늘 윗꼬리 비율(종가 무렵)", "close", "u"),
    "hi20t": ("오늘 종가의 20일 고가(오늘 포함) 대비 %(0=20일 신고가로 마감)", "close", "c"),
    "align": ("이평 정배열 단계 0~3(어제 종가 기준 5>20·20>60·60>120 일 선 만족 수)", "pre", "c"),
    "engulf": ("어제 상승 장악형 캔들(1=양봉 몸통이 그제 음봉 몸통을 감쌈)", "pre", "c"),
    # 2026-10-10 2차(사용자: "여기서 할 수 있는 거 다 수집해" — 못 옮긴 조건 표)
    "d50": ("어제 종가의 50일선 대비 %", "pre", "s"), "d200": ("어제 종가의 200일선 대비 %", "pre", "s"),
    "st_up": ("어제 Supertrend(ATR10·배수3) 상승 추세면 1", "pre", "c"),
    "lr50": ("최근 50일 종가 선형회귀 기울기(하루당 %)", "pre", "s"),
    "vbrk": ("어제 거래량 ÷ 그 전 60일 최대 거래량(1↑=60일 신고 거래량)", "pre", "r"),
    "c40": ("어제 종가의 그 전 40일 종가 최고 대비 %(0↑=40일 종가 신고)", "pre", "c"),
    "bigd": ("최근 장대양봉(+7%↑·거래량 2배↑) 뒤 지난 거래일 수(30 이상은 30)", "pre", "c"),
    "bodyr": ("어제 몸통 ÷ 고저폭(0=도지·1=꼬리 없는 마루보주)", "pre", "u"),
    "sweep": ("어제 20일 저가를 깼다가 그 위로 마감(스윕 후 복귀)=1", "pre", "c"),
    "turn": ("어제 회전율 %(거래량 ÷ 발행 주식)", "pre", "c"),
    "inst": ("어제 기관 순매수 ÷ 20일 평균 거래대금 %", "pre", "s"), "inst5": ("최근 5일 기관 순매수 합 ÷ 20일 평균 거래대금 %", "pre", "s"),
    "amtt": ("오늘 거래대금(억원, 종가 무렵)", "close", "c"),
    # 장중(1분봉 2022-12~ · m10c/m14c 방식만)
    "i_r10": ("오늘 시가→10:00 %", "i10", "s"), "i_vw10": ("10:00 가격의 VWAP 대비 %", "i10", "s"),
    "i_a10": ("10:00까지 거래대금 ÷ 20일 평균 하루 거래대금", "i10", "r"),
    "i_r14": ("오늘 시가→14:00 %", "i14", "s"), "i_vw14": ("14:00 가격의 VWAP 대비 %", "i14", "s"),
    "i_pos14": ("14:00 가격의 오늘 고저 위치(0~1)", "i14", "u"), "i_a14": ("14:00까지 거래대금 ÷ 20일 평균 하루 거래대금", "i14", "r"),
    # 실시간 녹화(과거 없음) — 정답지·그림자 전용
    "a_eq": ("08:59 장전 호가로 본 예상 갭 %", "live", "s"), "a_drift": ("장전 예상 갭 변화(08:59 - 08:31) %p", "live", "s"),
    "a_imb": ("08:59 장전 호가 매수잔량 쏠림(-1~1)", "live", "s"), "a_nxt": ("NXT 장전 마지막 체결가 갭 %", "live", "s"),
    "a_err": ("장전 예상 갭 - 실제 갭 %p(예상이 얼마나 빗나갔나)", "live", "s"),
    "c_imb": ("15:27 마감 동시호가 매수잔량 쏠림", "live", "s"), "c_drift": ("마감 동시호가 예상가 - 15:20 가격 %", "live", "s"),
}
FLOW = {"fr", "ir", "fr5", "inst", "inst5"}            # 2018~ 만 있다
INTRA = {k for k, v in FEATS.items() if v[1] in ("i10", "i14")}
HIST = [k for k, v in FEATS.items() if v[1] != "live"]


def _supertrend(tk, h, l, c, atr, mult):
    """Supertrend 방향(1 상승·0 하락) — 종목이 바뀌면 처음부터. 종가가 위 밴드를 넘으면 상승, 아래 밴드를 깨면 하락."""
    n = len(c); out = np.full(n, np.nan)
    fu = fl = np.nan; up = True
    for i in range(n):
        if i == 0 or tk[i] != tk[i - 1]:
            fu = fl = np.nan; up = True
        a = atr[i]
        if not (a == a): continue
        mid = (h[i] + l[i]) / 2; ub = mid + mult * a; lb = mid - mult * a
        pc_ = c[i - 1] if i and tk[i] == tk[i - 1] else c[i]
        fu = ub if not (fu == fu) or ub < fu or pc_ > fu else fu
        fl = lb if not (fl == fl) or lb > fl or pc_ < fl else fl
        if up and c[i] < fl: up = False
        elif not up and c[i] > fu: up = True
        out[i] = 1.0 if up else 0.0
    return out


def _streak(b, tk):
    b = b.fillna(False).astype(bool)
    return b.astype(int).groupby([tk, (~b).groupby(tk).cumsum()]).cumsum()


def make(D, flows=None, themes=None, us=None, seam=True, amt_mp=15):
    """D: ticker,date,open,high,low,close,volume(+pref,n5,n20) — 종목·날짜순 정렬. 반환: 같은 줄 + 재료·목표·uni.
    flows: ticker,date,frgn,indiv(원) · themes: gname,ticker · us: transfer.attach 가 붙인다(따로)."""
    D = D.sort_values(["ticker", "date"]).reset_index(drop=True)
    tk = D.ticker
    g = D.groupby("ticker", sort=False)
    o, h, l, c, v = (D[k].astype("float64") for k in ("open", "high", "low", "close", "volume"))
    pc = g.close.shift(1)
    sh = lambda k, n: g[k].shift(n)
    roll = lambda s, n, f, mp=None: getattr(s.groupby(tk, sort=False).rolling(n, min_periods=mp or n), f)().reset_index(level=0, drop=True)
    ret = (c / pc - 1) * 100                                          # t 의 하루 등락
    F = pd.DataFrame(index=D.index)
    F["r1"] = ret.groupby(tk).shift(1)
    F["r5"] = (pc / sh("close", 6) - 1) * 100
    F["r20"] = (pc / sh("close", 21) - 1) * 100
    F["r60"] = (pc / sh("close", 61) - 1) * 100
    ph, pl = sh("high", 1), sh("low", 1)
    F["clv"] = (pc - pl) / (ph - pl).replace(0, np.nan)
    F["rng"] = (ph - pl) / pc * 100
    pv = sh("volume", 1).astype(float)
    v20p = roll(v, 20, "mean", 15).groupby(tk).shift(1)              # t-1 까지 20일 평균
    F["vm"] = pv / v20p.groupby(tk).shift(1).replace(0, np.nan)      # 어제 거래량 ÷ 그 전 20일
    F["vm5"] = roll(v, 5, "mean").groupby(tk).shift(1) / v20p.replace(0, np.nan)
    F["fh"] = (pc / roll(h, 20, "max", 15).groupby(tk).shift(1) - 1) * 100
    F["fl"] = (pc / roll(l, 20, "min", 15).groupby(tk).shift(1) - 1) * 100
    for n in (5, 20, 60):
        F["d%d" % n] = (pc / roll(c, n, "mean").groupby(tk).shift(1) - 1) * 100
    F["vol20"] = roll(ret, 20, "std", 15).groupby(tk).shift(1)
    F["dn"] = _streak(ret < 0, tk).groupby(tk).shift(1)
    F["up"] = _streak(ret > 0, tk).groupby(tk).shift(1)
    amt = c * v
    F["amt20"] = roll(amt, 20, "mean", amt_mp).groupby(tk).shift(1) / 1e8      # 매일 자료는 3일만 있어도(새로 들어온 종목이 순위판에서 빠지지 않게)
    F["px"] = pc
    F["gap"] = (o / pc - 1) * 100
    F["r1t"] = ret
    F["clvt"] = (c - l) / (h - l).replace(0, np.nan)
    F["vmt"] = v / v20p.replace(0, np.nan)
    F["rngt"] = (h - l) / c * 100
    F["oct"] = (c / o - 1) * 100
    # ── 2026-10-10 추가 재료(전부 어제 종가까지 → shift 1) ──
    s1 = lambda x: x.groupby(tk).shift(1)
    F["hi250"] = (pc / s1(roll(h, 250, "max", 120)) - 1) * 100
    F["lo250"] = (pc / s1(roll(l, 250, "min", 120)) - 1) * 100
    F["hi60"] = (pc / s1(roll(h, 60, "max", 40)) - 1) * 100
    for n in (120, 224):
        F["d%d" % n] = (pc / s1(roll(c, n, "mean", int(n * 0.8))) - 1) * 100
    dc = c.groupby(tk).diff()
    up_ = dc.clip(lower=0).groupby(tk).transform(lambda s: s.ewm(alpha=1 / 14, adjust=False).mean())
    dn_ = (-dc.clip(upper=0)).groupby(tk).transform(lambda s: s.ewm(alpha=1 / 14, adjust=False).mean())
    F["rsi14"] = s1(100 - 100 / (1 + up_ / dn_.replace(0, np.nan)))
    m20, sd20 = roll(c, 20, "mean"), roll(c, 20, "std")
    F["bbp"] = s1((c - (m20 - 2 * sd20)) / (4 * sd20).replace(0, np.nan))
    F["bbw"] = s1(4 * sd20 / m20 * 100)
    e12 = c.groupby(tk).transform(lambda s: s.ewm(span=12, adjust=False).mean())
    e26 = c.groupby(tk).transform(lambda s: s.ewm(span=26, adjust=False).mean())
    mac = e12 - e26
    sig = mac.groupby(tk).transform(lambda s: s.ewm(span=9, adjust=False).mean())
    F["macd"] = s1((mac - sig) / c * 100)
    F["ich"] = (pc / s1((roll(h, 26, "max") + roll(l, 26, "min")) / 2) - 1) * 100
    rg = (h - l).replace(0, np.nan)
    uw_t = (h - np.maximum(o, c)) / rg
    F["uw"] = s1(uw_t); F["lw"] = s1((np.minimum(o, c) - l) / rg)
    F["body"] = s1((c / o - 1) * 100)
    lim_up = np.where(D.date < "20150615", 14.5, 29.0)
    F["lu20"] = s1(roll((ret >= lim_up).astype(float), 20, "sum", 1))
    F["age"] = g.cumcount().clip(upper=250).astype(float)
    if "marcap" in D.columns:
        mc = D.marcap.astype(float); mc = mc.where(mc < 1e9, mc / 1e8)           # 일부 날짜가 원 단위로 섞여 있다(억 단위 최대 ~2천만 → 1e9 넘으면 원)
        F["mcap"] = s1(mc)
    elif "shares" in D.columns:
        F["mcap"] = D.shares.astype(float) * pc / 1e8
    else:
        F["mcap"] = np.nan
    F["uwt"] = uw_t
    F["hi20t"] = (c / roll(h, 20, "max", 15) - 1) * 100
    ma = {n: roll(c, n, "mean", int(n * 0.8)) for n in (5, 20, 60, 120)}
    F["align"] = s1(((ma[5] > ma[20]).astype(float) + (ma[20] > ma[60]).astype(float) + (ma[60] > ma[120]).astype(float)).where(ma[120].notna()))
    po, pcl = g.open.shift(1), g.close.shift(1)
    eng = (c > o) & (pcl < po) & (c >= po) & (o <= pcl)                      # 오늘 양봉 몸통이 어제 음봉 몸통을 감쌈
    F["engulf"] = s1(eng.astype(float))
    # ── 2026-10-10 2차 ──
    for n in (50, 200):
        F["d%d" % n] = (pc / s1(roll(c, n, "mean", int(n * 0.8))) - 1) * 100
    tr_ = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    atr = tr_.groupby(tk).transform(lambda s: s.ewm(alpha=1 / 10, adjust=False).mean())
    F["st_up"] = s1(pd.Series(_supertrend(D.ticker.to_numpy(), h.to_numpy(), l.to_numpy(), c.to_numpy(), atr.to_numpy(), 3.0), index=D.index))
    lc = np.log(c.where(c > 0))                                       # 50일 회귀 기울기 — 누적합 공식(빠르게): slope = (nΣty − ΣtΣy)/(nΣt² − (Σt)²)
    n_ = 50.0; t_ = g.cumcount().astype(float)
    Sy = roll(lc, 50, "sum"); Sty = roll(t_ * lc, 50, "sum")
    St = n_ * t_ - n_ * (n_ - 1) / 2; Stt = roll(t_ * t_, 50, "sum")
    F["lr50"] = s1((n_ * Sty - St * Sy) / (n_ * Stt - St * St)) * 100
    F["vbrk"] = pv / s1(roll(v, 60, "max", 40)).groupby(tk).shift(1).replace(0, np.nan)
    F["c40"] = (pc / s1(roll(c, 40, "max", 30)).groupby(tk).shift(1) - 1) * 100
    big = ((ret >= 7) & (v >= 2 * v20p)).astype(float)
    idx = pd.Series(np.where(big > 0, g.cumcount(), np.nan), index=D.index).groupby(tk).ffill()
    F["bigd"] = s1((g.cumcount() - idx).clip(upper=30)).fillna(30)
    F["bodyr"] = s1((c - o).abs() / rg)
    lo20 = s1(roll(l, 20, "min", 15))
    F["sweep"] = s1(((l < lo20) & (c > lo20)).astype(float))
    if "marcap" in D.columns:
        shares = (mc * 1e8 / c).where(c > 0)
        F["turn"] = s1(v / shares * 100)
    elif "shares" in D.columns:
        F["turn"] = s1(v / D.shares.astype(float) * 100)
    else:
        F["turn"] = np.nan
    F["amtt"] = c * v / 1e8
    # 목표
    F["oc"] = F["oct"]
    F["on"] = (g.open.shift(-1) / c - 1) * 100
    F.loc[F.on.abs() > 30.5, "on"] = np.nan                           # 거래정지 뒤 첫 시가 같은 이음새
    for hd in SWH:
        if "n%d" % hd in D.columns: F["sw%d" % hd] = D["n%d" % hd].groupby(tk).shift(1)   # 패널 n{h} = 신호 다음날 시가 매수 → 비용 포함
        else: F["sw%d" % hd] = (g.close.shift(-(hd - 1)) / o - 1) * 100 - 0.6               # 매일 자료: t 시가 → t+h-1 종가, 비용 0.6%(패널 하단)
    # 쓸 수 없는 줄: 가격제한으로 불가능한 변동(이음새) · 거래 없음 · 시가 상한가 근처(못 산다)
    lim = np.where(D.date < "20150615", 16.0, 30.5)
    bad = (F.gap.abs() > lim) | (F.r1t.abs() > lim) | (o > h * 1.001) | (o < l * 0.999) | (c > h * 1.001) | (c < l * 0.999) | (v <= 0)
    okrow = ~bad.fillna(True)
    if seam:                                                          # 이음새 앞뒤 60거래일 — 앞뒤 재료·목표가 다 틀린다(run_spec 과 같은 규율)
        di = g.cumcount().to_numpy(); tkv = tk.to_numpy(); badm = np.zeros(len(D), bool)
        for i in np.flatnonzero(bad.fillna(False).to_numpy() & (v > 0).to_numpy()):
            lo_, hi_ = max(i - 60, 0), min(i + 60, len(D) - 1)
            badm[lo_:hi_ + 1] |= (tkv[lo_:hi_ + 1] == tkv[i])
        okrow &= ~pd.Series(badm, index=D.index)
    pref = D["pref"].fillna(False).astype(bool) if "pref" in D.columns else False
    elig = okrow & (F.px >= 1000) & F.amt20.notna() & ~pref & (F.gap < 29)
    F["uni"] = (F.amt20.where(elig).groupby(D.date).rank(pct=True) >= 0.60) & elig
    F["liq"] = F.amt20.where(F.uni).groupby(D.date).rank(pct=True)
    um = lambda s: s.where(F.uni).groupby(D.date).transform("median")
    F["mk_r1"] = um(F.r1); F["mk_r5"] = um(F.r5); F["mgap"] = um(F.gap)
    F["rgap"] = F.gap - F.mgap
    if flows is not None and len(flows):
        m = D[["ticker", "date"]].merge(flows[["ticker", "date", "frgn", "indiv"]], on=["ticker", "date"], how="left")
        fr_, ir_ = m.frgn.astype(float), m.indiv.astype(float)
        a8 = F.amt20 * 1e8
        F["fr"] = fr_.groupby(tk).shift(1).values / a8 * 100
        F["ir"] = ir_.groupby(tk).shift(1).values / a8 * 100
        F["fr5"] = fr_.groupby(tk).rolling(5, min_periods=3).sum().reset_index(level=0, drop=True).groupby(tk).shift(1).values / a8 * 100
        if "inst" in flows.columns:
            in_ = D[["ticker", "date"]].merge(flows[["ticker", "date", "inst"]], on=["ticker", "date"], how="left").inst.astype(float)
            F["inst"] = in_.groupby(tk).shift(1).values / a8 * 100
            F["inst5"] = in_.groupby(tk).rolling(5, min_periods=3).sum().reset_index(level=0, drop=True).groupby(tk).shift(1).values / a8 * 100
        else:
            F["inst"] = F["inst5"] = np.nan
    else:
        F["fr"] = F["ir"] = F["fr5"] = F["inst"] = F["inst5"] = np.nan
    if themes is not None and len(themes):
        R = D[["ticker", "date"]].assign(ret=ret.clip(-30, 30))
        M = themes[["gname", "ticker"]].drop_duplicates().merge(R, on="ticker")
        TI = M.groupby(["gname", "date"]).ret.mean().reset_index().sort_values(["gname", "date"])
        TI["r20"] = TI.groupby("gname").ret.transform(lambda s: (np.log1p(s / 100)).rolling(20, min_periods=15).sum())
        TI["pct"] = TI.groupby("date").r20.rank(pct=True)
        T = themes[["gname", "ticker"]].drop_duplicates().merge(TI[["gname", "date", "pct"]], on="gname").groupby(["ticker", "date"]).pct.max()
        th = D[["ticker", "date"]].merge(T.rename("th").reset_index(), on=["ticker", "date"], how="left").th
        F["th"] = th.groupby(tk).shift(1).values
    else:
        F["th"] = np.nan
    for k in ("us_ewy", "tr_us", "tr_pred", "tr_res"):
        F[k] = np.nan
    out = pd.concat([D[["ticker", "date"]], F], axis=1)
    return out


def intra(U, M):
    """장중 재료·목표(m10c·m14c) — M: ticker,date + 1분봉 단면 o_m,c_m,p1000,vw1000,v1000,p1400,vw1400,hi1400,lo1400,v1400,amt20_m
    (가격은 1분봉끼리만 — 일봉 수정주가와 섞지 않는다 · H0295 함정). U 에 붙여 돌려준다(1분봉 없는 줄은 빈칸)."""
    Z = U[["ticker", "date"]].merge(M, on=["ticker", "date"], how="left")
    U["i_r10"] = ((Z.p1000 / Z.o_m - 1) * 100).values
    U["i_vw10"] = ((Z.p1000 / Z.vw1000 - 1) * 100).values
    U["i_a10"] = (Z.v1000 * Z.vw1000 / Z.amt20_m.replace(0, np.nan)).values
    U["i_r14"] = ((Z.p1400 / Z.o_m - 1) * 100).values
    U["i_vw14"] = ((Z.p1400 / Z.vw1400 - 1) * 100).values
    U["i_pos14"] = ((Z.p1400 - Z.lo1400) / (Z.hi1400 - Z.lo1400).replace(0, np.nan)).values
    U["i_a14"] = (Z.v1400 * Z.vw1400 / Z.amt20_m.replace(0, np.nan)).values
    U["m10c"] = ((Z.c_m / Z.p1000 - 1) * 100).values
    U["m14c"] = ((Z.c_m / Z.p1400 - 1) * 100).values
    return U


def qcols(U, feats=None):
    """유니버스 줄(U)만 받아 q_<재료> = 그날 백분위를 붙인다."""
    feats = feats or [f for f in FEATS if f in U.columns]
    gd = U.groupby("date")
    for f in feats:
        if f == "liq":
            U["q_liq"] = U.liq
        else:
            U["q_" + f] = gd[f].rank(pct=True).astype("float32")
    return U


def shrink(U):
    for k in U.columns:
        if U[k].dtype == "float64": U[k] = U[k].astype("float32")
    return U
