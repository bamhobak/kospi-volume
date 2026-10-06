# -*- coding: utf-8 -*-
"""유튜브 단타 5편 실측 (2026-10-07, 사용자 링크 5개) — 국장·미장 1분봉.
  V1 dzF9cCAW1OE '10번 중 9번 이기는 단타' — 1분봉 22이평 아래로 크게 벌어진 급락 → 첫 양봉에 사서 낙폭의 25%(또는 50%) 되돌림에서 익절, 저점 깨면 손절
  V2 -Tp2fhvVVGM '오더블록' — 5분봉: 음봉 몸통을 감싸는 양봉(장악형) → 그 음봉 몸통(오더블록)까지 되돌리면 매수 · 오더블록 캔들 저점 손절 ·
     직전 고점에서 절반 익절 + 나머지는 본절 스탑, 장 끝에 정리
  V3 pGg_JBGLbdI '9시 유동성 사냥' — 5분봉 09:00~10:00: 첫 15분 박스 → 박스 아래로 찍고 다시 박스 안 마감(사냥) → 3봉 상승 갭(FVG) →
     FVG 로 되돌린 첫 양봉에 매수 · 사냥 저점 손절 · 목표 = 직전 고점 / 피보 -2.5 확장 / 장 끝 · 추세(전날 종가 > 5일선) 있음/없음
     V3b 수요존 — 사냥 뒤 첫 장대 양봉 범위로 되돌린 아래꼬리 양봉에 매수 · 존 아래 손절 · 직전 고점 익절
  V4 1BcJBE-m59s 'RSI 단타' — 5분봉: 100이평 상승 중 RSI(14) 50 상향 돌파 매수 → RSI 50 하향 이탈 매도(직전 저점 손절·장 끝 정리) ·
     클로디 RSI(상승·하락 힘 분리 교차)는 수식상 RSI 50 교차와 같아 이평 조건 없는 판으로 잰다 · 눌림 RSI 고점 돌파 판
  (V5 a6LRWJZIhDI 는 받아쓰기 뒤 따로)
비용: 국장 수수료·세금 0.23% + 장중 시장가 진입·손절 미끄러짐 각 0.05% (지정가 익절은 0) · 미장 수수료 0.10%×2 + 미끄러짐 각 0.02%.
같은 1분/5분 봉에서 익절·손절 둘 다 닿으면 손절로 센다(보수적) · 손절선을 뚫고 연 봉은 그 봉 시가에 체결.
표본: 국장 = 1분봉 전 기간 종목 중 무작위 300 · 미장 = 지금까지 받은 대형주 전부(수집 중) · 2022-12~2026-10 · 학습 ~2024 / 검증 2025~.
    python research/yt_scalp.py
"""
import json, sys, time, random
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(BASE))
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))
COST = {"KR": (0.23, 0.05), "US": (0.20, 0.02)}          # (왕복 수수료·세금, 시장가 한 번 미끄러짐)
OPEN_HM = {"KR": ("0900", "1000", "0915"), "US": ("0930", "1030", "0945")}


def load(mk, f):
    D = pd.read_parquet(f, columns=["ts", "o", "h", "l", "c", "v"])
    tz = "Asia/Seoul" if mk == "KR" else "America/New_York"
    t = pd.to_datetime(D.ts, unit="s", utc=True).dt.tz_convert(tz)
    D["date"] = t.dt.strftime("%Y%m%d").values; D["hm"] = t.dt.strftime("%H%M").values
    for k in ("o", "h", "l", "c"): D[k] = D[k].astype("float64")
    return D.sort_values("ts").reset_index(drop=True)


def bars5(g):
    """1분봉 하루치 → 5분봉(봉 끝 시각 기준 묶음)."""
    k = (np.arange(len(g)) // 5)
    a = g.groupby(k).agg(o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last"), hm=("hm", "last"))
    return a.reset_index(drop=True)


def run_trade(o, h, l, c, i, px, stop, tgt, half=None, slip=0.0):
    """i+1 봉부터 본다. 반환: (수익률% 비용 전, 미끄러짐 횟수). tgt=None 이면 장 끝. half=(1차 목표) 면 절반 익절 뒤 본절."""
    n = len(c); pos = 1.0; got = 0.0; be = None; sl_n = 0
    for j in range(i + 1, n):
        st = be if be is not None else stop
        if l[j] <= st:                                           # 손절(같은 봉 목표보다 먼저)
            f = min(st, o[j]); got += pos * (f / px - 1); return got * 100, sl_n + 1
        if half is not None and be is None and h[j] >= half:
            got += 0.5 * (half / px - 1); pos = 0.5; be = px
        if tgt is not None and h[j] >= tgt:
            got += pos * (max(tgt, o[j]) / px - 1); return got * 100, sl_n
    got += pos * (c[-1] / px - 1)
    return got * 100, sl_n


def rsi(c, n=14):
    d = np.diff(c, prepend=c[0]); up = np.where(d > 0, d, 0.0); dn = np.where(d < 0, -d, 0.0)
    au = pd.Series(up).ewm(alpha=1 / n, adjust=False).mean().values; ad = pd.Series(dn).ewm(alpha=1 / n, adjust=False).mean().values
    return 100 - 100 / (1 + au / np.where(ad == 0, 1e-12, ad))


def one(arg):
    mk, f = arg
    try:
        D = load(mk, f)
    except Exception:
        return []
    t0h, t1h, boxend = OPEN_HM[mk]
    T = []
    days = D.groupby("date", sort=True)
    closes = days.c.last(); ma5 = closes.rolling(5).mean().shift(1); pclose = closes.shift(1)
    # 5분봉 연속 시계열(이평100·RSI 는 날을 넘겨 이어 계산)
    B5 = []
    for d, g in days:
        if len(g) < 300: continue
        b = bars5(g); b["date"] = d; B5.append(b)
    if not B5: return []
    B5 = pd.concat(B5, ignore_index=True)
    B5["ma100"] = B5.c.rolling(100).mean(); B5["ma100s"] = B5.ma100 - B5.ma100.shift(10); B5["rsi"] = rsi(B5.c.values)
    trend_ok = (pclose > ma5)
    for d, g in days:
        if len(g) < 300: continue
        o, h, l, c, hm = g.o.values, g.h.values, g.l.values, g.c.values, g.hm.values
        # ── V1: 1분봉 22이평 괴리 급락 → 첫 양봉 → 25%/50% 되돌림 ──
        ma = pd.Series(c).rolling(22).mean().values
        lo30 = pd.Series(l).rolling(30).min().values; hi30 = pd.Series(h).rolling(30).max().values
        for dv in (0.01, 0.02):
            busy = -1
            for t in np.where((c < ma * (1 - dv)) & (l <= lo30))[0]:
                if t <= busy or t < 30: continue
                H = hi30[t]; L = l[t]
                for k in range(t + 1, min(t + 6, len(c) - 1)):
                    L = min(L, l[k])
                    if c[k] > o[k]:
                        drop = H - L
                        if drop <= 0: break
                        for fr in (0.25, 0.5):
                            tg = L + fr * drop
                            if c[k] >= tg: continue
                            r, s = run_trade(o, h, l, c, k, c[k], L, tg)
                            T.append(("V1 괴리 %d%% · 되돌림 %d%%" % (dv * 100, fr * 100), d, r, 1 + s))
                        busy = k + 30; break
        # ── 5분봉 하루치 ──
        b = B5[B5.date == d]
        bo, bh, bl, bc, bhm = b.o.values, b.h.values, b.l.values, b.c.values, b.hm.values
        brsi, bma, bms = b.rsi.values, b.ma100.values, b.ma100s.values
        n5 = len(bc)
        # ── V2 오더블록(장악형 양봉 → 음봉 몸통 되돌림) ──
        busy = -1
        for j in range(1, n5 - 2):
            if j <= busy: continue
            if not (bc[j - 1] < bo[j - 1] and bc[j] > bo[j] and bo[j] <= bc[j - 1] and bc[j] >= bo[j - 1]): continue
            top, stop = bo[j - 1], min(bl[j - 1], bl[j]); Hh = bh[j]
            for k in range(j + 1, min(j + 13, n5 - 1)):
                if bl[k] <= top:                                   # 손절선(아래)에 닿는 봉은 반드시 먼저 오더블록 상단을 지난다 → 진입 뒤 손절로 센다
                    px = min(top, bo[k])
                    if Hh <= px * 1.001: break
                    # 들어간 봉 안에서 손절까지 닿았으면 손절
                    if bl[k] <= stop:
                        T.append(("V2 오더블록(절반 직전고점·본절)", d, (stop / px - 1) * 100, 1)); busy = k; break
                    r, s = run_trade(bo, bh, bl, bc, k, px, stop, None, half=Hh)
                    T.append(("V2 오더블록(절반 직전고점·본절)", d, r, s))
                    r, s = run_trade(bo, bh, bl, bc, k, px, stop, Hh)
                    T.append(("V2 오더블록(전량 직전고점)", d, r, s))
                    busy = k; break
                Hh = max(Hh, bh[k])
        # ── V3 9시 유동성 사냥 + FVG / 수요존 ──
        bxi = np.where(bhm <= boxend)[0]
        if len(bxi) >= 2:
            bxl, bxh = bl[bxi].min(), bh[bxi].max()
            win = np.where((bhm > boxend) & (bhm <= t1h))[0]
            sw = [k for k in win if bl[k] < bxl and bc[k] > bxl]
            if sw:
                s0 = sw[0]; slo = bl[s0]
                tr = bool(trend_ok.get(d, False))
                # FVG: s0 뒤 3봉 b1,b2,b3 에서 b3 저가 > b1 고가
                done = False
                for q in range(s0 + 1, n5 - 3):
                    if bhm[q + 2] > t1h or done: break
                    if bl[q + 2] > bh[q] and bc[q + 1] > bo[q + 1]:
                        ftop, fbot = bl[q + 2], bh[q]; hi_ = bh[: q + 3].max()
                        for k in range(q + 3, n5 - 1):
                            if bhm[k] > t1h: break
                            if bl[k] <= slo: break
                            if bl[k] <= ftop and bc[k] > bo[k]:
                                px = bc[k]
                                for nm, tg in (("직전 고점", hi_), ("피보 -2.5", hi_ + 2.5 * (hi_ - slo)), ("장 끝", None)):
                                    if tg is not None and tg <= px: continue
                                    r, s = run_trade(bo, bh, bl, bc, k, px, slo, tg)
                                    T.append(("V3 사냥+FVG → %s%s" % (nm, " · 추세 위" if tr else " · 추세 아래"), d, r, 1 + s))
                                done = True; break
                        done = True
                # 수요존: 사냥 뒤 첫 장대 양봉(몸통 ≥ 그날 그때까지 평균 몸통 2배)
                body = np.abs(bc - bo); avgb = np.cumsum(body) / np.arange(1, n5 + 1)
                for z in range(s0, n5 - 1):
                    if bhm[z] > t1h: break
                    if bc[z] > bo[z] and body[z] >= 2 * avgb[max(z - 1, 0)]:
                        zl, zh = bl[z], bh[z]; hi_ = bh[: z + 1].max()
                        for k in range(z + 1, n5 - 1):
                            if bl[k] < zl: break
                            if bl[k] <= zh and bc[k] > bo[k] and (min(bo[k], bc[k]) - bl[k]) >= (bc[k] - bo[k]):
                                hi2 = max(hi_, bh[z + 1:k].max() if k > z + 1 else hi_)
                                if hi2 > bc[k]:
                                    r, s = run_trade(bo, bh, bl, bc, k, bc[k], zl, hi2)
                                    T.append(("V3b 수요존 되돌림 → 직전 고점%s" % (" · 추세 위" if tr else " · 추세 아래"), d, r, 1 + s))
                                break
                        break
        # ── V4 RSI ──
        busy = -1
        for j in range(1, n5 - 1):
            if j <= busy or np.isnan(brsi[j - 1]) or np.isnan(bma[j]): continue
            if brsi[j - 1] < 50 <= brsi[j]:
                swl = bl[max(0, j - 10): j + 1].min()
                for lab, ok in (("V4 RSI 50 상향(100이평 상승 중)", bms[j] > 0 and bc[j] > bma[j]), ("V4 RSI 50 상향(이평 조건 없음 = 클로디 교차)", True)):
                    if not ok: continue
                    # RSI 50 하향 이탈 봉 종가 · 직전 저점 손절 · 장 끝
                    ex = None
                    for k in range(j + 1, n5):
                        if bl[k] <= swl: ex = (min(swl, bo[k]) / bc[j] - 1) * 100; sl = 2; break
                        if brsi[k] < 50: ex = (bc[k] / bc[j] - 1) * 100; sl = 2; break
                    if ex is None: ex = (bc[-1] / bc[j] - 1) * 100; sl = 1
                    T.append((lab, d, ex, sl))
                busy = j
        # 눌림 RSI 고점 돌파: 100이평 상승 · RSI 가 50 아래로 눌렸다가 그 눌림 구간 RSI 최고점을 넘음
        busy = -1
        for j in range(12, n5 - 1):
            if j <= busy or np.isnan(bms[j]) or not (bms[j] > 0): continue
            seg = brsi[j - 12: j]
            if seg.min() < 50 and brsi[j] > seg.max() and brsi[j - 1] <= seg.max():
                swl = bl[j - 12: j + 1].min(); ex = None
                for k in range(j + 1, n5):
                    if bl[k] <= swl: ex = (min(swl, bo[k]) / bc[j] - 1) * 100; sl = 2; break
                    if brsi[k] < 50: ex = (bc[k] / bc[j] - 1) * 100; sl = 2; break
                if ex is None: ex = (bc[-1] / bc[j] - 1) * 100; sl = 1
                T.append(("V4 눌림 RSI 고점 돌파(100이평 상승 중)", d, ex, sl)); busy = j
    return [(mk,) + x for x in T]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    t0 = time.time()
    done = json.loads((BASE / "data" / "m1" / "backfill_state.json").read_text(encoding="utf-8"))["done"]
    kr = sorted(k.split(":")[1] for k in done if k.startswith("KR:"))
    random.seed(7); kr = random.sample(kr, 300)
    us = sorted(k.split(":")[1] for k in done if k.startswith("US:"))
    jobs = [("KR", BASE / "data/m1/KR/bf" / (s + ".parquet")) for s in kr] + [("US", BASE / "data/m1/US/bf" / (s + ".parquet")) for s in us]
    jobs = [j for j in jobs if j[1].exists()]
    rows = []
    with ProcessPoolExecutor(6) as ex:
        for i, r in enumerate(ex.map(one, jobs, chunksize=2)):
            rows += r
            if (i + 1) % 50 == 0: print("  %d/%d · %.1f분 · 거래 %d" % (i + 1, len(jobs), (time.time() - t0) / 60, len(rows)), flush=True)
    R = pd.DataFrame(rows, columns=["mk", "s", "date", "raw", "nslip"])
    R.to_pickle(ROOT / "cache" / "yt_scalp.pkl")
    nk = {"KR": len([j for j in jobs if j[0] == "KR"]), "US": len([j for j in jobs if j[0] == "US"])}
    P("# 유튜브 단타 5편 실측(1분봉) · %s" % time.strftime("%Y-%m-%d")); P("")
    P("- 국장 무작위 %d종목 · 미장 대형주 %d종목(수집된 만큼) · 2022-12~2026-10 · 학습 ~2024 / 검증 2025~" % (nk["KR"], nk["US"]))
    P("- 비용 뒤 = 수수료·세금(국장 0.23% · 미장 0.20%) + 시장가 미끄러짐(국장 0.05% · 미장 0.02%) × 진입·손절 횟수"); P("")
    for mk in ("KR", "US"):
        Z = R[R.mk == mk].copy()
        if Z.empty: continue
        fee, sl = COST[mk]; Z["ret"] = Z.raw - fee - sl * Z.nslip
        P("## %s" % ("국장" if mk == "KR" else "미장")); P("")
        P("| 기법 | 건수(종목당 하루) | 비용 전 평균 | 학습: 평균·승률 | 검증: 평균·승률 | 해마다(23·24·25·26) |"); P("|---|---|---|---|---|---|")
        for s, z in Z.groupby("s", sort=True):
            nd = z.date.nunique()
            cell = []
            for a, b in (("20221201", "20241231"), ("20250101", "20991231")):
                y = z[(z.date >= a) & (z.date <= b)]
                cell.append("%d건 %+.3f%% · %.0f%%" % (len(y), y.ret.mean(), (y.ret > 0).mean() * 100) if len(y) else "-")
            yr = z.groupby(z.date.str[:4]).ret.mean(); yr = yr[yr.index >= "2023"]
            P("| %s | %d (%.2f) | %+.3f%% | %s | %s | %s |" % (s, len(z), len(z) / max(nk[mk], 1) / max(R[R.mk == mk].date.nunique(), 1), z.raw.mean(), cell[0], cell[1], " ".join("%+.2f" % v for v in yr.values)))
        P("")
    P("(%.1f분)" % ((time.time() - t0) / 60))
    from verdict import log_trials
    log_trials("yt_scalp_%s" % time.strftime("%Y%m%d"), int(R.groupby(["mk", "s"]).ngroups))
    (ROOT / "reports" / ("yt_scalp_%s.md" % time.strftime("%Y%m%d"))).write_text("\n".join(OUT) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
