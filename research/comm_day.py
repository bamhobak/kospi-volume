# -*- coding: utf-8 -*-
"""온라인 커뮤니티 단타 기법 실측 (2026-10-07, 사용자 "커뮤니티에 올라간 단타 매매법 수집해서 실측") — 국장·미장 1분봉, 매수 쪽만.
수집 출처(조사 에이전트): QuantConnect/SSRN(Stocks-in-Play ORB) · Crabel · Larry Williams Oops · Raschke 80-20 · SMB Fashionably Late ·
Red-to-Green · Ross Cameron 마이크로 풀백 · Gap and Go · Aziz ABCD · TradeThatSwing(Breakout and Run · 첫 1시간 추세) · HOD 돌파 ·
갭 메우기 · VWAP 2σ 회귀 · 2nd Day Play · Sykes Morning Panic · 다음카페·디시·주달(시초가 갭 3~5% · 갭상 첫 눌림 · 투매 받기 · 오후 2시 반등 ·
영웅전 신고가+거래대금). 공매도 기법(First Red Day 등)은 국장에서 못 써서 뺐다. 상따·상한가 눌림은 소형주 이벤트라 따로(comm_limitup).
규칙 해석은 조사 보고서의 '가장 흔한 구체적 해석'을 따랐다(각 함수 주석). 같은 봉 손절 우선 · 손절선을 뚫고 연 봉은 그 봉 시가.
비용: 국장 수수료·세금 0.23% + 장중 시장가 진입·손절 각 0.05% · 미장 0.20% + 0.02%. 표본: 국장 1분봉 전 기간 종목 무작위 300 · 미장 대형주(수집된 만큼).
    python research/comm_day.py
"""
import json, sys, time, random
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(BASE))
import yt_scalp as Y
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))
# 시각(국장 / 미장 뉴욕) — 개장 후 같은 경과 시간으로 맞춘다
HM = {"KR": dict(o5="0905", o15="0915", t10="1000", t1015="0945", t1030="1030", t11="1100", t1130="1130", t1200="1200",
                 t1300="1300", t1330="1330", t1400="1400", t1430="1430", t1500="1500", t0910="0910", end="1530"),
      "US": dict(o5="0935", o15="0945", t10="1030", t1015="1015", t1030="1100", t11="1130", t1130="1200", t1200="1230",
                 t1300="1330", t1330="1400", t1400="1430", t1430="1500", t1500="1530", t0910="0940", end="1600")}


def ema(x, n):
    return pd.Series(x).ewm(span=n, adjust=False).mean().values


def first(cond, start=0):
    w = np.where(cond[start:])[0]
    return start + w[0] if len(w) else None


def one(arg):
    mk, f = arg
    try: D = Y.load(mk, f)
    except Exception: return []
    days = [(d, g.reset_index(drop=True)) for d, g in D.groupby("date", sort=True) if len(g) >= 300]
    if len(days) < 30: return []
    H = HM[mk]; T = []
    dd = pd.DataFrame({"date": [d for d, _ in days], "o": [g.o.iloc[0] for _, g in days], "h": [g.h.max() for _, g in days],
                       "l": [g.l.min() for _, g in days], "c": [g.c.iloc[-1] for _, g in days],
                       "v": [g.v.sum() for _, g in days], "v5": [g.v.iloc[:5].sum() for _, g in days],
                       "amt": [(g.c * g.v).sum() for _, g in days]})
    rng = dd.h - dd.l
    tr = pd.concat([rng, (dd.h - dd.c.shift(1)).abs(), (dd.l - dd.c.shift(1)).abs()], axis=1).max(axis=1)
    dd["atr"] = tr.rolling(14).mean(); dd["atr20"] = tr.rolling(20).mean(); dd["rng20"] = rng.rolling(20).mean()
    dd["v5avg"] = dd.v5.rolling(14).mean(); dd["vavg"] = dd.v.rolling(20).mean(); dd["amt20"] = dd.amt.rolling(20).mean()
    dd["stretch"] = pd.concat([dd.h - dd.o, dd.o - dd.l], axis=1).min(axis=1).rolling(10).mean()
    dd["hi15"] = dd.h.rolling(15).max(); dd["hi20"] = dd.h.rolling(20).max()
    dd["up4"] = (dd.c > dd.c.shift(1)).rolling(4).sum(); dd["r4"] = dd.c / dd.c.shift(4) - 1
    pv = {k: dd[k].shift(1).values for k in dd.columns if k != "date"}          # 전날까지 값
    nxt_o = dd.o.shift(-1).values
    for idx, (d, g) in enumerate(days):
        if idx < 21: continue
        o, h, l, c, v, hm = g.o.values, g.h.values, g.l.values, g.c.values, g.v.values.astype(float), g.hm.values
        n = len(c); op = o[0]
        pc, ph, pl, po = pv["c"][idx], pv["h"][idx], pv["l"][idx], pv["o"][idx]
        if not (pc > 0): continue
        gap = (op / pc - 1) * 100
        if abs(gap) > 29: continue
        atr = pv["atr"][idx]; rv5 = dd.v5.values[idx] / pv["v5avg"][idx] if pv["v5avg"][idx] else np.nan
        cpv = np.cumsum(c * v); cv = np.cumsum(v); vw = cpv / np.where(cv == 0, np.nan, cv)
        var = np.cumsum(v * c * c) / np.where(cv == 0, np.nan, cv) - vw ** 2; sd = np.sqrt(np.maximum(var, 0))
        lo_sofar = np.minimum.accumulate(l); hi_sofar = np.maximum.accumulate(h)
        at = lambda t: (np.where(hm <= t)[0][-1] if (hm <= t).any() else 0)
        add = lambda name, r, s, extra=None: T.append((name, d, r, s, extra))
        # 1 Stocks-in-Play 5분 ORB — 첫 5분 양봉 → 그 고가 돌파 매수 · 손절 ATR 10% · 장 끝 (RVOL 은 따로 적어 두고 날마다 상위 20 을 나중에 고른다)
        if n > 10 and c[4] > op and atr == atr:
            h5 = h[:5].max(); j = first(h > h5, 5)
            if j is not None:
                px = max(h5, o[j]); r, s = Y.run_trade(o, h, l, c, j, px, px - 0.1 * atr, None)
                if l[j] <= px - 0.1 * atr: r, s = ((px - 0.1 * atr) / px - 1) * 100, 1
                add("01 SIP 5분 ORB(첫봉 양봉 고가 돌파·ATR10% 손절)", r, 1 + s, rv5)
        # 2 Crabel 스트레치 — 시가 + 10일 평균 스트레치에 매수 스톱 → 다음날 시가
        st_ = pv["stretch"][idx]
        if st_ == st_ and st_ > 0 and nxt_o[idx] == nxt_o[idx]:
            j = first(h >= op + st_, 1)
            if j is not None:
                px = max(op + st_, o[j]); add("02 Crabel 스트레치 매수 → 다음날 시가", (nxt_o[idx] / px - 1) * 100, 1)
        # 3 Oops — 전날 음봉 & 오늘 전날 저가 아래 시작 → 전날 저가+0.1% 회복 매수 · 그때까지 저가 손절 · 장 끝
        if pc < po and op < pl:
            j = first(h >= pl * 1.001, 1)
            if j is not None:
                px = max(pl * 1.001, o[j]); r, s = Y.run_trade(o, h, l, c, j, px, lo_sofar[j - 1] * 0.999, None)
                add("03 Oops(갭하락 뒤 전날 저가 회복)", r, 1 + s)
        # 4 Raschke 80-20 — 전날 레인지 > 20일 평균 · 시가 상위 20% · 종가 하위 20% → 오늘 전날 저가 0.5%↓ 뒤 전날 저가 재돌파 매수
        pr = ph - pl
        if pr > 0 and pr > pv["rng20"][idx] and (po - pl) >= 0.8 * pr and (pc - pl) <= 0.2 * pr:
            k = first(l <= pl * 0.995, 0)
            if k is not None:
                j = first(h >= pl, k + 1)
                if j is not None:
                    px = max(pl, o[j]); r, s = Y.run_trade(o, h, l, c, j, px, lo_sofar[j - 1] * 0.999, None)
                    add("04 Raschke 80-20", r, 1 + s)
        # 5 Fashionably Late — 9EMA 가 VWAP 를 아래에서 위로(VWAP 10봉 기울기 ≤ 0) → 손절 1/3 · 목표 측정 이동
        e9 = ema(c, 9)
        cr = np.where((e9[1:] > vw[1:]) & (e9[:-1] <= vw[:-1]))[0] + 1
        for j in cr:
            if j < 30 or hm[j] > H["t1500"] or not (vw[j] <= vw[j - 10]) or not (e9[j] > e9[j - 3]): continue
            dl = lo_sofar[j]; px = c[j]; dist = px - dl
            if dist <= px * 0.003: continue
            r, s = Y.run_trade(o, h, l, c, j, px, px - dist / 3, px + dist)
            add("05 Fashionably Late(9EMA↗VWAP)" + (" · RVOL≥2" if rv5 >= 2 else ""), r, 1 + s); break
        # 6 Red-to-Green — 전날 종가 아래(전날 저가 위) 시작 → 전날 종가 위 1분봉 마감 매수 · 1분봉이 전날 종가 아래 마감하면 정리 · 장 끝
        if pl < op < pc:
            j = first(c > pc, 1)
            if j is not None and j < n - 1:
                px = c[j]; ex = None
                for q in range(j + 1, n):
                    if l[q] <= lo_sofar[j] * 0.999: ex = (min(lo_sofar[j] * 0.999, o[q]) / px - 1) * 100; break
                    if c[q] < pc: ex = (c[q] / px - 1) * 100; break
                add("06 Red-to-Green(전날 종가 회복)", ex if ex is not None else (c[-1] / px - 1) * 100, 2 if ex is not None else 1)
        # 8 마이크로 풀백 — 갭 ≥ 10% & RVOL ≥ 5 · 개장 90분: 2%↑ 급등 → 0.3~5% 눌림(음봉 4개 미만) → 직전 봉 고가 돌파 매수 · 눌림 저점 손절 · 직전 봉 저가 깨면 정리
        if gap >= 10 and rv5 >= 5:
            for j in range(6, n - 1):
                if hm[j] > H["t11"]: break
                hi6 = h[j - 6:j - 1].max(); lo_pb = l[j - 4:j].min()
                if hi6 >= c[j - 6] * 1.02 and 0.003 <= (hi6 - lo_pb) / hi6 <= 0.05 and (c[j - 4:j] < o[j - 4:j]).sum() < 4 and h[j] > h[j - 1]:
                    px = max(h[j - 1], o[j]); stp = min(lo_pb, px * 0.98); ex = None
                    for q in range(j + 1, n):
                        if l[q] <= stp: ex = (min(stp, o[q]) / px - 1) * 100; break
                        if c[q] < l[q - 1]: ex = (c[q] / px - 1) * 100; break
                    add("08 마이크로 풀백(갭10%·RVOL5)", ex if ex is not None else (c[-1] / px - 1) * 100, 2); break
        # 9 Gap and Go — 갭 3~7% & RVOL ≥ 3 → 첫 5분 고가 돌파 · 첫 5분 저가 손절 · 2R 절반 익절+본절 · 개장 1시간 뒤 정리
        if 3 <= gap <= 7 and rv5 >= 3:
            h5, l5 = h[:5].max(), l[:5].min(); j = first(h > h5, 5)
            if j is not None and hm[j] < H["t1030"]:
                px = max(h5, o[j]); end = at(H["t1030"]) + 1
                r, s = Y.run_trade(o[:end], h[:end], l[:end], c[:end], j, px, l5 * 0.999, None, half=px + 2 * (px - l5))
                add("09 Gap and Go(갭3~7%·RVOL3)", r, 1 + s)
        # 10 ABCD — 개장 2시간: 3봉 피벗 A(저) → B(고, A 대비 +2%↑) → C(저, A 위·되돌림 38~78%) → B 돌파 매수 · C 손절 · D=B+(B−A)
        piv_l = [i for i in range(3, n - 3) if l[i] == l[i - 3:i + 4].min()]
        piv_h = [i for i in range(3, n - 3) if h[i] == h[i - 3:i + 4].max()]
        lim = at(H["t11"])
        done = False
        for a in piv_l:
            if a > lim or done: break
            for b in piv_h:
                if b <= a or b > lim: continue
                if h[b] < l[a] * 1.02: continue
                for cc in piv_l:
                    if cc <= b + 1 or cc > lim: continue
                    ret = (h[b] - l[cc]) / (h[b] - l[a])
                    if l[cc] > l[a] and 0.38 <= ret <= 0.78:
                        j = first(h > h[b], cc + 4)
                        if j is not None and hm[j] <= H["t1200"]:
                            px = max(h[b], o[j]); r, s = Y.run_trade(o, h, l, c, j, px, l[cc] * 0.999, h[b] + (h[b] - l[a]))
                            add("10 ABCD(B 돌파)", r, 1 + s)
                        done = True
                    break
                break
        # 12 첫 1시간 박스 돌파 — 개장 90분, 직전 15봉 범위 ≤ 0.6%(국장 1%) & VWAP·시가 위 → 박스 고가 돌파 · 박스 저가 손절 · 2R 또는 직전 봉 저가 아래 마감 정리
        bx = 0.01 if mk == "KR" else 0.006
        for j in range(20, n - 1):
            if hm[j] > H["t11"]: break
            hh, ll = h[j - 15:j].max(), l[j - 15:j].min()
            if (hh - ll) / ll <= bx and c[j - 1] > vw[j - 1] and c[j - 1] > op and h[j] > hh:
                px = max(hh, o[j]); stp = ll * 0.999; tg = px + 2 * (px - stp); ex = None
                for q in range(j + 1, n):
                    if l[q] <= stp: ex = (min(stp, o[q]) / px - 1) * 100; break
                    if h[q] >= tg: ex = (tg / px - 1) * 100; break
                    if c[q] < l[q - 1]: ex = (c[q] / px - 1) * 100; break
                add("12 첫 1시간 박스 돌파", ex if ex is not None else (c[-1] / px - 1) * 100, 2); break
        # 13 HOD 돌파 — 개장 1시간 뒤~15시: 누적 거래량이 평소 같은 시각의 2배↑ & VWAP 위 & 당일 고가가 15봉 전 것 → 그 고가 돌파 · −1% 손절 · 장 끝
        vfrac = cv / max(pv["vavg"][idx], 1)
        for j in range(max(at(H["t10"]), 20), n - 1):
            if hm[j] > H["t1500"]: break
            hod = hi_sofar[j - 1]
            if h[j] > hod and c[j - 1] > vw[j - 1] and h[j - 15:j - 1].max() < hod and vfrac[j - 1] >= 2 * (j / n):
                px = max(hod, o[j]); r, s = Y.run_trade(o, h, l, c, j, px, px * 0.99, None)
                add("13 HOD 돌파(RVOL2·VWAP 위)", r, 1 + s); break
        # 14 작은 갭하락 메우기 — 갭 < 0.4×ATR20 & 시가가 전날 범위 안 → 시가 매수 · 전날 종가 목표 · 같은 거리 손절
        a20 = pv["atr20"][idx]
        if op < pc and a20 == a20 and (pc - op) < 0.4 * a20 and op >= pl:
            dist = pc - op
            if dist > op * 0.001:
                r, s = Y.run_trade(o, h, l, c, 0, op, op - dist, pc)
                if l[0] <= op - dist: r, s = (-dist / op) * 100, 1
                add("14 작은 갭하락 메우기(시가 매수)", r, 0 + s)
        # 15 VWAP −2σ 회귀 — 10:00~11:30 · 13:30~14:30(미장 같은 경과) 에 저가가 VWAP−2σ 아래 & 반전봉(장악형·망치형) → 다음 봉 시가 매수 · 목표 VWAP · 손절 신호 저가 −1×(1분 ATR14)
        a1 = pd.Series(h - l).rolling(14).mean().values
        for j in range(30, n - 2):
            win = (H["t10"] <= hm[j] <= H["t1130"]) or (H["t1330"] <= hm[j] <= H["t1430"])
            if not win: continue
            if l[j] <= vw[j] - 2 * sd[j] and sd[j] > 0:
                body = abs(c[j] - o[j]); lw = min(o[j], c[j]) - l[j]
                eng = c[j - 1] < o[j - 1] and c[j] > o[j] and o[j] <= c[j - 1] and c[j] >= o[j - 1]
                ham = lw >= 2 * body and (c[j] - l[j]) >= (h[j] - l[j]) * 2 / 3 and h[j] > l[j]
                if eng or ham:
                    px = o[j + 1]
                    if vw[j] > px:
                        r, s = Y.run_trade(o, h, l, c, j + 1, px, l[j] - a1[j], vw[j])
                        if l[j + 1] <= l[j] - a1[j]: r, s = ((l[j] - a1[j]) / px - 1) * 100, 1
                        add("15 VWAP −2σ 반전봉 회귀", r, 1 + s)
                    break
        # 16 2nd Day Play — 전날 +10%↑(미장 +8%↑) & 거래량 3배↑ → 오늘 전날 고가 돌파 매수 · 전날 종가 손절 · 장 끝
        pret = (pc / pv["c"][idx - 1] - 1) * 100 if idx >= 2 else np.nan
        vmul = pv["v"][idx] / dd.v.values[max(0, idx - 21):idx - 1].mean() if idx >= 22 else np.nan
        if pret >= (10 if mk == "KR" else 8) and vmul >= 3 and op < ph:
            j = first(h > ph, 1)
            if j is not None:
                px = max(ph, o[j]); r, s = Y.run_trade(o, h, l, c, j, px, pc * 0.999, None)
                add("16 2nd Day Play(전날 급등주 전날 고가 돌파)", r, 1 + s)
        # 17 Morning Panic — 4일 연속 상승 & 4일 +20%↑ → 첫 15분 저가가 시가 −5%↓ 뒤 1분봉 직전 고가 돌파 매수 · 저점 손절 · +10% 또는 1시간
        if pv["up4"][idx] == 4 and pv["r4"][idx] >= 0.2:
            k = first((l <= op * 0.95) & (hm <= H["o15"]), 0)
            if k is not None:
                j = first(h > np.r_[np.inf, h[:-1]], k + 1)
                if j is not None:
                    px = max(h[j - 1], o[j]); end = min(n, j + 60)
                    r, s = Y.run_trade(o[:end], h[:end], l[:end], c[:end], j, px, lo_sofar[j] * 0.999, px * 1.1)
                    add("17 Morning Panic(연속 급등주 장초 급락 반등)", r, 1 + s)
        # 20 시초가 갭 3~5% — 시가 매수 · 첫 1분봉이 시가 아래 마감이면 그 종가에 손절 · 아니면 9:15(미장 9:45) 정리
        if 3 <= gap <= 5 and op >= pv["hi20"][idx] * 0.9:
            if c[0] < op: add("20 시초가 갭3~5%(신고가 근처) · 9:15 정리", (c[0] / op - 1) * 100, 1)
            else:
                k = at(H["o15"]); add("20 시초가 갭3~5%(신고가 근처) · 9:15 정리", (c[k] / op - 1) * 100, 1)
        # 21 갭상 첫 눌림 — 갭 ≥ 2% · 9:10~10:00: 시가 +1% 고점 뒤 1분 20이평까지 눌림 → 20이평 위 양봉·거래량 늘며 마감 매수 · +3% 익절 · 눌림 저점 손절
        if gap >= 2:
            m20 = pd.Series(c).rolling(20).mean().values
            for j in range(20, n - 1):
                if hm[j] < H["t0910"]: continue
                if hm[j] > H["t10"]: break
                if hi_sofar[j - 1] >= op * 1.01 and l[j] <= m20[j] and c[j] > m20[j] and c[j] > o[j] and v[j] > v[j - 1]:
                    px = c[j]; r, s = Y.run_trade(o, h, l, c, j, px, min(l[j - 5:j + 1]) * 0.999, px * 1.03)
                    add("21 갭상 첫 눌림(1분 20이평)", r, 1 + s); break
        # 23 투매 받기 — 3분봉, 10:00~11:30·13:00~14:30: −2%↓ 장대음봉 & 그때까지 그날 최대 거래량 → 종가 매수 · 1/3 되돌림 익절 · 그 봉 저가 손절
        k3 = np.arange(n) // 3
        G3 = pd.DataFrame({"o": o, "h": h, "l": l, "c": c, "v": v, "hm": hm}).groupby(k3).agg(o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last"), v=("v", "sum"), hm=("hm", "last"))
        to, th, tl, tc, tv, thm = G3.o.values, G3.h.values, G3.l.values, G3.c.values, G3.v.values, G3.hm.values
        for j in range(10, len(tc) - 1):
            win = (H["t10"] <= thm[j] <= H["t1130"]) or (H["t1300"] <= thm[j] <= H["t1430"])
            if win and tc[j] <= to[j] * 0.98 and tv[j] >= tv[:j].max():
                top = th[j - 10:j + 1].max(); px = tc[j]; tg = tl[j] + (top - tl[j]) / 3
                if tg > px:
                    r, s = Y.run_trade(to, th, tl, tc, j, px, tl[j] * 0.999, tg); add("23 투매 받기(3분 장대음봉+최대 거래량)", r, 1 + s)
                break
        # 24 오후 2시 반등 — 12시 가격이 시가 −2%↓ · 14시 뒤 처음 VWAP 위 마감 & 그 봉 거래량 ≥ 그날 평균 2배 → 매수 · 장 끝 / 다음날 시가
        k12 = at(H["t1200"])
        if c[k12] <= op * 0.98:
            avgv = cv[-1] / n
            for j in range(at(H["t1400"]), n - 1):
                if c[j] > vw[j] and c[j - 1] <= vw[j - 1] and v[j] >= 2 * avgv:
                    px = c[j]; r, s = Y.run_trade(o, h, l, c, j, px, -1.0, None); add("24 오후 2시 반등(VWAP 회복·거래량 2배) · 장 끝", r, 1)
                    if nxt_o[idx] == nxt_o[idx]: add("24 오후 2시 반등 · 다음날 시가", (nxt_o[idx] / px - 1) * 100, 1)
                    break
        # 25 신고가+거래대금(영웅전) — 20일 거래대금 상위(국장 500억↑ · 미장 $200M↑) & 시가가 15일 고가 5% 안 → 15일 고가 돌파 매수 · −2% 손절 · 장 끝
        h15 = pv["hi15"][idx]; amt_ok = pv["amt20"][idx] >= (5e10 if mk == "KR" else 2e8)
        if amt_ok and h15 == h15 and op < h15 and op >= h15 * 0.95:
            j = first(h > h15, 1)
            if j is not None:
                px = max(h15, o[j]); r, s = Y.run_trade(o, h, l, c, j, px, px * 0.98, None); add("25 15일 신고가 돌파(거래대금 큰 종목)", r, 1 + s)
        # 11 Breakout and Run — 전날 20일 고가 돌파 마감 & 종가가 범위 위 25% → 오늘 개장 45분 뒤~2시간: 5분 스윙 고가(직전 6봉) 돌파 · 스윙 저가 손절(≤2%) · 장 끝
        if pc >= pv["hi20"][idx - 1] if idx >= 2 else False:
            if pr > 0 and (pc - pl) >= 0.75 * pr:
                b = Y.bars5(g); bo, bh, bl, bc, bhm = b.o.values, b.h.values, b.l.values, b.c.values, b.hm.values
                for j in range(6, len(bc) - 1):
                    if bhm[j] <= H["t1015"]: continue
                    if bhm[j] > H["t1130"]: break
                    sh, sl_ = bh[j - 6:j].max(), bl[j - 6:j].min()
                    if bh[j] > sh:
                        px = max(sh, bo[j]); stp = max(sl_, px * 0.98)
                        r, s = Y.run_trade(bo, bh, bl, bc, j, px, stp * 0.999, None); add("11 Breakout and Run", r, 1 + s); break
    return [(mk,) + x for x in T]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    t0 = time.time()
    done = json.loads((BASE / "data" / "m1" / "backfill_state.json").read_text(encoding="utf-8"))["done"]
    kr = sorted(k.split(":")[1] for k in done if k.startswith("KR:")); random.seed(7); kr = random.sample(kr, 300)
    us = sorted(k.split(":")[1] for k in done if k.startswith("US:"))
    jobs = [("KR", BASE / "data/m1/KR/bf" / (s + ".parquet")) for s in kr] + [("US", BASE / "data/m1/US/bf" / (s + ".parquet")) for s in us]
    jobs = [j for j in jobs if j[1].exists()]
    rows = []
    with ProcessPoolExecutor(6) as ex:
        for i, r in enumerate(ex.map(one, jobs, chunksize=2)):
            rows += r
            if (i + 1) % 100 == 0: print("  %d/%d · %.1f분" % (i + 1, len(jobs), (time.time() - t0) / 60), flush=True)
    R = pd.DataFrame(rows, columns=["mk", "s", "date", "raw", "nslip", "rv"])
    # 1번 Stocks-in-Play: 날마다 RVOL>1 중 상위 20
    S1 = R[R.s.str.startswith("01")].copy()
    S1 = S1[S1.rv > 1].sort_values("rv", ascending=False).groupby(["mk", "date"]).head(20); S1["s"] = "01 SIP 5분 ORB · RVOL>1 날마다 상위 20(논문 방식)"
    R = pd.concat([R, S1], ignore_index=True)
    R.to_pickle(ROOT / "cache" / "comm_day.pkl")
    P("# 온라인 커뮤니티 단타 기법 실측(1분봉) · %s" % time.strftime("%Y-%m-%d")); P("")
    P("- 국장 무작위 %d · 미장 대형주 %d · 2022-12~2026-10 · 비용 뒤(국장 0.23%%+미끄러짐 0.05%% · 미장 0.20%%+0.02%%) · 같은 봉 손절 우선" % (
        len([j for j in jobs if j[0] == "KR"]), len([j for j in jobs if j[0] == "US"]))); P("")
    for mk in ("KR", "US"):
        Z = R[R.mk == mk].copy()
        if Z.empty: continue
        fee, sl = Y.COST[mk]; Z["ret"] = Z.raw - fee - sl * Z.nslip
        P("## %s" % ("국장" if mk == "KR" else "미장")); P("")
        P("| 기법 | 건수 | 비용 전 평균 | 학습 ~24: 평균·승률 | 검증 25~: 평균·승률 | 해마다(23·24·25·26) | 판정 |"); P("|---|---|---|---|---|---|---|")
        for s, z in Z.groupby("s", sort=True):
            cell, mm = [], []
            for a, b in (("20221201", "20241231"), ("20250101", "20991231")):
                y = z[(z.date >= a) & (z.date <= b)]
                cell.append("%d건 %+.3f%% · %.0f%%" % (len(y), y.ret.mean(), (y.ret > 0).mean() * 100) if len(y) else "-"); mm.append(y.ret.mean() if len(y) >= 30 else np.nan)
            yr = z.groupby(z.date.str[:4]).ret.mean(); yr = yr[yr.index >= "2023"]
            ok = all(m > 0 for m in mm if m == m) and all(m == m for m in mm) and (yr > 0).sum() >= len(yr) - 1
            P("| %s | %d | %+.3f%% | %s | %s | %s | %s |" % (s, len(z), z.raw.mean(), cell[0], cell[1], " ".join("%+.2f" % v for v in yr.values), "✅ 후보" if ok else "—"))
        P("")
    P("(%.1f분)" % ((time.time() - t0) / 60))
    from verdict import log_trials
    log_trials("comm_day_%s" % time.strftime("%Y%m%d"), int(R.groupby(["mk", "s"]).ngroups))
    (ROOT / "reports" / ("comm_day_%s.md" % time.strftime("%Y%m%d"))).write_text("\n".join(OUT) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
