# -*- coding: utf-8 -*-
"""로스 카메론(Warrior Trading) 'Growing a $2k Account to $65k in 30 Days'(xGIa8Vg0PWM · 2026-10-15 사용자 링크) 실측 — H0337.

영상 규칙(모멘텀 첫 눌림 · 1분봉):
  종목: 오늘 +10%↑(30%↑ 최고) · 상대 거래량 5배↑(50일 평균 대비) · 주가 $2~20 · 유통주식 2천만 주 미만 · 뉴스(못 씀) · 7~10시(장전 포함)
  진입: 급등(당일 신고가) 뒤 눌림 1~5봉 — 급등폭의 50% 넘게 안 되돌림 · VWAP 위 · 9EMA 위 · 빨간 봉 거래량 < 초록 봉 거래량 →
        처음으로 직전 봉 고가를 넘는 봉에서 매수(역지정가) · 손절 = 눌림 저점
  청산: 목표로 끊지 않음 — 윗꼬리 봉·빨간 봉 등 '청산 신호'에 나옴(호가창·체결창 신호는 못 씀) · 10시 넘으면 매매 그만
우리 자료: 국장 1분봉 전 종목(2022-12~, 정규장만 — 장전 NXT 없음) · 미장 1분봉은 대형·중형 1,040종목뿐(소형 급등주 거의 없음).
국장 옮김: 주가 1천~3만원 · 유통주식 대신 시총(3천억 미만 / 1천억 미만) · 상대 거래량 = 지금까지 누적 ÷ (50일 평균 일 거래량 × 지난 시간 비율).
청산 판: X1 손익비 2:1(못 닿으면 장 끝) · X2 빨간 봉 또는 윗꼬리 봉 마감에 매도 · X3 직전 봉 저가 깨면(첫 새 저가 봉) 매도 · 모두 손절 먼저.
한 종목 하루 최대 3번(앞 거래 끝난 뒤 다음 눌림). 비용: 국장 0.23% + 역지정가 진입·시장가 청산 미끄러짐 각 0.05% · 미장 0.20% + 각 0.02%.
구간: 학습 ~2024 · 검증 2025~.
    python research/yt_ross.py KR|US
"""
import sys, glob
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))
MK = sys.argv[1] if len(sys.argv) > 1 else "KR"
CFG = {"KR": dict(tz="Asia/Seoul", t0="0901", t1="1531", open_min=9 * 60, fee=0.23, slip=0.05, px=(1000, 30000), day_min=390),
       "US": dict(tz="America/New_York", t0="0931", t1="1600", open_min=9 * 60 + 30, fee=0.20, slip=0.02, px=(2, 20), day_min=390)}[MK]


def load(f):
    D = pd.read_parquet(f, columns=["ts", "o", "h", "l", "c", "v"])
    t = pd.to_datetime(D.ts, unit="s", utc=True).dt.tz_convert(CFG["tz"])
    D["date"] = t.dt.strftime("%Y%m%d").values; D["hm"] = t.dt.strftime("%H%M").values
    D = D[(D.hm >= CFG["t0"]) & (D.hm <= CFG["t1"])]
    for k in ("o", "h", "l", "c"): D[k] = D[k].astype("float64")
    return D.sort_values("ts").reset_index(drop=True)


def ema(x, n):
    a = 2 / (n + 1); out = np.empty_like(x); out[0] = x[0]
    for i in range(1, len(x)): out[i] = a * x[i] + (1 - a) * out[i - 1]
    return out


def exit_walk(o, h, l, c, e, px, stop, mode, end):
    """e = 진입 봉. 반환 (비용 전 %, 끝난 봉, 손절 여부)."""
    tgt = px + 2 * (px - stop)
    for j in range(e, end):
        if l[j] <= stop: return (min(stop, o[j] if j > e else stop) / px - 1) * 100, j, 1
        if mode == "X1" and h[j] >= tgt and j > e: return (max(tgt, o[j]) / px - 1) * 100, j, 0
        if mode == "X1" and h[j] >= tgt and j == e and c[j] >= tgt: return (tgt / px - 1) * 100, j, 0
        rg = h[j] - l[j]
        if mode == "X2" and (c[j] < o[j] or (rg > 0 and h[j] - max(o[j], c[j]) >= 0.5 * rg)):
            return (c[j] / px - 1) * 100, j, 0
        if mode == "X3" and j > e and c[j] < l[j - 1]:
            return (c[j] / px - 1) * 100, j, 0
    return (c[end - 1] / px - 1) * 100, end - 1, 0


def one(arg):
    f, caps = arg
    try: D = load(f)
    except Exception: return []
    g = D.groupby("date", sort=True)
    dd = pd.DataFrame({"c": g.c.last(), "h": g.h.max(), "v": g.v.sum(), "n": g.size()})
    dd = dd[dd.n >= 200]
    if len(dd) < 25: return []
    dd["pc"] = dd.c.shift(1); dd["av50"] = dd.v.rolling(50, min_periods=20).mean().shift(1)
    mv = dd[(dd.h >= dd.pc * 1.10) & dd.av50.gt(0)]
    T = []
    for d, r in mv.iterrows():
        x = D[D.date == d].reset_index(drop=True)
        o, h, l, c, v, hm = x.o.values, x.h.values, x.l.values, x.c.values, x.v.values.astype(float), x.hm.values
        n = len(c)
        mins = np.array([int(s[:2]) * 60 + int(s[2:]) for s in hm]) - CFG["open_min"]
        cumv = np.cumsum(v); tp = (h + l + c) / 3; vwap = np.cumsum(tp * v) / np.maximum(cumv, 1)
        e9 = ema(c, 9); pc = r.pc
        cap = np.nan
        if caps is not None:
            k = np.searchsorted(caps[0], d, side="right") - 1
            if k >= 0: cap = caps[1][k]
        trades = 0; j = 2; hod_i = 0
        while j < n - 1 and trades < 3:
            if mins[j] > 120: break                                         # 2시간 지나면 안 봄(영상 10시 = 국장 9시 시작 기준 1시간 · 판으로 둘 다 기록)
            # 직전 봉까지의 당일 고가 위치
            hod_i = int(np.argmax(h[:j])); hod = h[hod_i]
            pb = j - 1 - hod_i                                              # 눌림 봉 수(고가 봉 다음부터 j-1 까지)
            if 1 <= pb <= 5 and h[j] > h[j - 1]:
                seg = slice(hod_i + 1, j)
                plo = l[seg].min()
                b0 = max(0, hod_i - 10); base = l[b0:hod_i + 1].min()
                sq = hod - base
                red = c[seg] < o[seg]
                gr = c[b0:hod_i + 1] > o[b0:hod_i + 1]
                gain = (c[j - 1] / pc - 1) * 100
                rvol = cumv[j - 1] / (r.av50 * max(mins[j - 1], 1) / CFG["day_min"])
                ok = (sq > 0 and (hod - plo) <= 0.5 * sq and red.any() and plo >= vwap[j - 1] and c[j - 1] >= e9[j - 1]
                      and (v[seg][red].mean() if red.any() else 0) < (v[b0:hod_i + 1][gr].mean() if gr.any() else np.inf)
                      and gain >= 10 and rvol >= 5)
                if ok:
                    trig = h[j - 1]
                    px = max(o[j], trig) * (1 + CFG["slip"] / 100); stop = plo
                    if px > stop:
                        win = "~1시간" if mins[j] <= 60 else "1~2시간"
                        pr = CFG["px"][0] <= c[j - 1] <= CFG["px"][1]
                        info = dict(date=d, win=win, gain=gain, rvol=rvol, price_ok=pr, cap=cap, risk=(px - stop) / px * 100)
                        endj = None
                        for mode in ("X1", "X2", "X3"):
                            ret, ej, st = exit_walk(o, h, l, c, j, px, stop, mode, n)
                            T.append(dict(info, mode=mode, r=ret - CFG["fee"] - CFG["slip"] * (1 + st), R=ret / ((px - stop) / px * 100)))
                            if mode == "X2": endj = ej
                        trades += 1; j = endj + 2; continue
            j += 1
    return T


def main():
    files = sorted(glob.glob(str(BASE / "data" / "m1" / MK / "bf" / "*.parquet")))
    capmap = {}
    if MK == "KR":
        A = pd.read_pickle(BASE / "data" / "kr_scan.pkl")[["ticker", "date", "marcap"]]
        A = A[A.date >= "20220601"]
        A["cap"] = np.where(A.marcap > 1e9, A.marcap / 1e8, A.marcap)
        for tk, q in A.groupby("ticker"): capmap[tk] = (q.date.values, q.cap.values)
    args = [(f, capmap.get(Path(f).stem)) for f in files]
    T = []
    with ProcessPoolExecutor(8) as ex:
        for i, r in enumerate(ex.map(one, args, chunksize=8)):
            T += r
            if i % 300 == 0: print("  ..%d/%d" % (i, len(args)), flush=True)
    E = pd.DataFrame(T)
    E["per"] = np.where(E.date <= "20241231", "학습 ~24", "검증 25~")
    E.to_pickle(ROOT / "cache" / ("yt_ross_%s.pkl" % MK))
    P("## %s 로스 카메론 첫 눌림(1분봉) — 비용 뒤 평균 · 중앙 · 승률 · 평균 R · 건수" % MK)
    P("| 판 | 청산 | 학습 ~24 | 검증 25~ |"); P("|---|---|---|---|")
    def row(nm, m):
        for mode, mn in (("X1", "2:1"), ("X2", "빨간·윗꼬리 봉"), ("X3", "직전 저가 깸")):
            cs = []
            for p in ("학습 ~24", "검증 25~"):
                x = E[m & (E["mode"] == mode) & (E.per == p)]
                cs.append("%d건 %+.2f · 중앙 %+.2f · %.0f%% · %+.2fR" % (len(x), x.r.mean(), x.r.median(), (x.r > 0).mean() * 100, x.R.mean()) if len(x) >= 10 else "%d건" % len(x))
            P("| %s | %s | %s |" % (nm, mn, " | ".join(cs)))
    al = E.r.notna()
    row("전체(+10%·상대 거래량 5배·VWAP·9EMA·50% 안)", al)
    row("영상 시간대(장 시작 1시간 안)", E.win == "~1시간")
    row("주가 범위 안(%s~%s)" % CFG["px"], E.price_ok)
    row("+30%↑ 종목", E.gain >= 30)
    row("상대 거래량 20배↑", E.rvol >= 20)
    if MK == "KR":
        row("시총 3천억 미만", E.cap < 3000)
        row("5원칙 다(1시간 안·주가·시총 1천억 미만·+10%·5배)", (E.win == "~1시간") & E.price_ok & (E.cap < 1000))
    else:
        row("5원칙(1시간 안·주가 $2~20)", (E.win == "~1시간") & E.price_ok)
    P("\n손절 폭(진입가 대비) 중앙 %.2f%% · 하루 평균 신호 %.1f건" % (E[E["mode"] == "X1"].risk.median(), (E["mode"] == "X1").sum() / max(E.date.nunique(), 1)))
    (ROOT / "cache" / ("yt_ross_%s.out" % MK)).write_text("\n".join(OUT), encoding="utf-8")


if __name__ == "__main__":
    main()
