# -*- coding: utf-8 -*-
"""유튜브 '전 재산 날리고 깨달았습니다 캔들 하나면 된다는 걸'(Mr. Chard Song, zXhwTvtc5Yc · 2026-10-14 사용자 링크) 실측 — H0335.

영상의 국내 주식 실전 기법 셋:
  M1 망치형: 지수가 -1% 넘게 빠진 날만, 10~11시 10분봉에서 아침부터 빠지던 종목에 긴 아래꼬리 망치형이 완성되면 다음 봉 진입,
     손절 = 망치 저점 - 꼬리 길이(그만큼 여유). 청산은 영상에 없음 → 장 끝 / 손익비 2:1 둘 다.
  M2 갭상승: 일봉으로 며칠 음봉 연속 하락 → 다음날 +2% 넘게 갭상승 → 첫 1시간봉(09~10시)이 양봉이면 10시 매수(음봉이면 안 삼),
     손절 = 전날 저가(또는 전날 종가). 청산은 영상에 없음 → 장 끝 / 5거래일.
  M3 매집 돌파: 코스닥 시총 1천억~5천억 · 거래량 죽어 있다가 전날 대비 5배 이상 · 윗꼬리 없는 장대양봉 · 시가=저가(아래꼬리 없음) 마감 확인 →
     다음날 몸통 1/3 정도 눌림에서 지정가 매수(대안 1/2) · 다음날 갭상승이면 첫 1시간봉 양봉 확인 뒤 10시 매수 ·
     손절 = 장대양봉 저가 · 목표 손익비 2:1(최대 20거래일 보유).
자료: M1·M2·M3b = 토스 1분봉(국장 2022-12~, 전 종목) · M3a = kr_scan 일봉 2005~.
비용: 국장 0.23%(수수료·세금) + 시장가 진입·손절 미끄러짐 각 0.05% · 지정가 진입은 미끄러짐 0. 같은 봉 손절·목표 = 손절로 셈.
1분봉 구간: 학습 ~2024 · 검증 2025~ / 일봉: 옛날 ~15 · 학습 16~22 · 검증 23~.
    python research/yt_candle.py
"""
import sys, glob, pickle
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(ROOT))
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))
FEE, SLIP = 0.23, 0.05
M1DIR = BASE / "data" / "m1" / "KR" / "bf"
CACHE = ROOT / "cache"


def load1m(f):
    D = pd.read_parquet(f, columns=["ts", "o", "h", "l", "c", "v"])
    t = pd.to_datetime(D.ts, unit="s", utc=True).dt.tz_convert("Asia/Seoul")
    D["date"] = t.dt.strftime("%Y%m%d").values; D["hm"] = t.dt.strftime("%H%M").values
    D = D[(D.hm >= "0901") & (D.hm <= "1531")]
    for k in ("o", "h", "l", "c"): D[k] = D[k].astype("float64")
    return D.sort_values("ts").reset_index(drop=True)


def daily(D):
    g = D.groupby("date", sort=True)
    d = pd.DataFrame({"o": g.o.first(), "h": g.h.max(), "l": g.l.min(), "c": g.c.last(), "amt": (D.c * D.v).groupby(D.date).sum(), "n": g.size()})
    return d


# ── 지수 대용: KODEX 200(069500) · KODEX 코스닥150(229200) 1분봉 — 전날 종가 대비 그 시각 등락 ──
IDX = {}


def idx_curve(code):
    if code in IDX: return IDX[code]
    D = load1m(M1DIR / ("%s.parquet" % code)); d = daily(D); pc = d.c.shift(1)
    D["r"] = (D.c / D.date.map(pc) - 1) * 100
    IDX[code] = {k: dict(zip(g.hm, g.r)) for k, g in D.groupby("date")}
    return IDX[code]


def tenmin(g):
    """1분봉(봉 끝 시각) 하루 → 10분봉. 09:01~09:10 = 10:10 아님, 첫 봉 끝 0910."""
    mins = (g.hm.str[:2].astype(int) - 9) * 60 + g.hm.str[2:].astype(int)
    k = ((mins - 1) // 10).clip(lower=0).values
    a = g.groupby(k).agg(o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last"), i_end=("o", lambda s: s.index[-1]))
    a["end"] = [(9 * 60 + 10 * (j + 1)) for j in a.index]
    return a.reset_index(drop=True)


def walk(o, h, l, c, i, px, stop, tgt):
    """1분봉 i+1 부터 장 끝까지. 반환 (비용 전 %, 손절 여부)."""
    for j in range(i + 1, len(c)):
        if l[j] <= stop: return (min(stop, o[j]) / px - 1) * 100, 1
        if tgt is not None and h[j] >= tgt: return (max(tgt, o[j]) / px - 1) * 100, 0
    return (c[-1] / px - 1) * 100, 0


def hold_days(dd, k, px, stop, tgt, nd):
    """일봉 dd(o,h,l,c 배열) k+1 일부터 nd 일. 반환 (비용 전 %, 손절 여부)."""
    o, h, l, c = dd
    end = min(len(c) - 1, k + nd)
    for j in range(k + 1, end + 1):
        if stop is not None and l[j] <= stop: return (min(stop, o[j]) / px - 1) * 100, 1
        if tgt is not None and h[j] >= tgt: return (max(tgt, o[j]) / px - 1) * 100, 0
    return (c[end] / px - 1) * 100, 0


def one(arg):
    f, mk, m3, only_m3 = arg
    tk = Path(f).stem
    try: D = load1m(f)
    except Exception: return []
    dd = daily(D)
    dd = dd[dd.n >= 200]
    if len(dd) < 30: return []
    dates = list(dd.index); di = {d: i for i, d in enumerate(dates)}
    DO, DH, DL, DC = dd.o.values, dd.h.values, dd.l.values, dd.c.values
    amt20 = pd.Series(dd.amt.values).rolling(20, min_periods=10).mean().shift(1).values
    bear = (DC < DO).astype(int)
    run = np.zeros(len(DC), int)
    for i in range(len(DC)): run[i] = run[i - 1] + 1 if (bear[i] and i) else (1 if bear[i] else 0)
    IC = idx_curve("069500" if mk == "KOSPI" else "229200")
    T = []
    byday = dict(tuple(D.groupby("date")))
    for i in range(21, len(dates)):
        d = dates[i]; g = byday[d].reset_index(drop=True)
        if amt20[i] != amt20[i] or amt20[i] < 1e9: continue
        liq = "100억↑" if amt20[i] >= 1e10 else "10~100억"
        o, h, l, c, hm = g.o.values, g.h.values, g.l.values, g.c.values, g.hm.values
        op, pc = o[0], DC[i - 1]
        ic = IC.get(d, {})
        if only_m3: ic = {}
        # ── M1 망치형 ──
        if not any(v <= -1.0 for hk, v in ic.items() if "1010" <= hk <= "1100"): b = None
        else: b = tenmin(g)
        lo_sofar = None if b is None else np.minimum.accumulate(b.l.values)
        for j in range(0 if b is None else len(b) - 1):
            e = b.end.values[j]
            if e < 10 * 60 + 10: continue
            if e > 11 * 60: break
            hmk = "%02d%02d" % (e // 60, e % 60)
            ir = ic.get(hmk)
            if ir is None or ir > -1.0: continue
            bo, bh, bl, bc = b.o.values[j], b.h.values[j], b.l.values[j], b.c.values[j]
            rg = bh - bl
            if rg <= 0: continue
            body = abs(bc - bo); lw = min(bo, bc) - bl; uw = bh - max(bo, bc)
            if not (lw >= 2 * body and lw >= 0.6 * rg and uw <= 0.2 * rg): continue
            if not (bl <= lo_sofar[j] and bc < op): continue                    # 아침부터 빠지던(오늘 저점 갱신 · 시가 아래)
            k = int(b.i_end.values[j]) + 1
            if k >= len(c): break
            px = o[k] * (1 + SLIP / 100); stop = bl - lw
            r, s = walk(o, h, l, c, k - 1, px, stop, None)              # walk 는 i+1 부터 → 진입 봉 k 부터 보게 k-1
            T.append(("M1 망치형 · 장 끝", liq, d, r - FEE - SLIP * s))
            tg = px + 2 * (px - stop)
            r, s = walk(o, h, l, c, k - 1, px, stop, tg)
            T.append(("M1 망치형 · 손익비 2:1(장 끝까지)", liq, d, r - FEE - SLIP * s))
            pcr = (bc / pc - 1) * 100
            T.append(("M1 망치형 · 장 끝 · 종목 전날 대비 -3%↓" if pcr <= -3 else "M1 망치형 · 장 끝 · 종목 전날 대비 -3% 위", liq, d, T[-2][3]))
            break
        # ── M2 갭상승 (며칠 음봉 → +2% 갭 → 첫 1시간봉) ──
        gap = (op / pc - 1) * 100
        if run[i - 1] >= 3 and gap >= 2 and not only_m3:
            k = np.where(hm <= "1000")[0]
            if len(k):
                k = k[-1]; px = c[k] * (1 + SLIP / 100); up = c[k] > op
                tag = "양봉" if up else "음봉(영상: 안 삼)"
                for snm, stop in (("전날 저가", DL[i - 1]), ("전날 종가", pc)):
                    if c[k] <= stop: continue
                    r, s = walk(o, h, l, c, k, px, stop, None)
                    T.append(("M2 음봉 %d일↑ 뒤 갭 +2%%↑ · 첫 1시간 %s · 손절 %s · 장 끝" % (3, tag, snm), liq, d, r - FEE - SLIP * s))
                    if s == 0:
                        r2, s2 = hold_days((DO, DH, DL, DC), i, px, stop, None, 5)
                    else: r2, s2 = r, 1
                    T.append(("M2 음봉 %d일↑ 뒤 갭 +2%%↑ · 첫 1시간 %s · 손절 %s · 5거래일" % (3, tag, snm), liq, d, r2 - FEE - SLIP * max(s, s2)))
        # ── M3b 매집 돌파 다음날 갭상승 → 첫 1시간 양봉 → 10시 매수 ──
        if i >= 1 and (tk, dates[i - 1]) in m3:
            sl, sc = m3[(tk, dates[i - 1])]
            if op > sc:
                k = np.where(hm <= "1000")[0]
                if len(k) and c[k[-1]] > op:
                    k = k[-1]; px = c[k] * (1 + SLIP / 100); stop = sl; tg = px + 2 * (px - stop)
                    r, s = walk(o, h, l, c, k, px, stop, tg)
                    if s == 0 and not (h[k + 1:].max() >= tg if k + 1 < len(h) else False):
                        r, s = hold_days((DO, DH, DL, DC), i, px, stop, tg, 20)
                    T.append(("M3b 매집 돌파 다음날 갭상승 · 첫 1시간 양봉 10시 · 손절 저가 · 2:1 · 20일", "-", d, r - FEE - SLIP * (1 + s)))
    return T


def m3_daily():
    """M3a 일봉(2005~): 신호 표 + 눌림 지정가 매매."""
    A = pd.read_pickle(BASE / "data" / "kr_scan.pkl")
    A = A[(A.close >= 1000) & (~A.pref.fillna(False))].sort_values(["ticker", "date"]).reset_index(drop=True)
    A["cap억"] = np.where(A.marcap > 1e9, A.marcap / 1e8, A.marcap)          # 2022 까지 원 · 2023~ 억(kr_scan 단위 섞임)
    g = A.groupby("ticker", sort=False)
    # 액면분할·병합 이음새(가격제한 밖 하루 변동) 앞뒤 60일 신호 제외 — run_spec.load_market 과 같은 처리
    pc0 = g.close.shift(1); lim = np.where(A.date < "20150615", 0.16, 0.31)
    seam = (((A.close / pc0 - 1).abs() > lim) | ((A.open / pc0 - 1).abs() > lim)).to_numpy()
    tk0 = A.ticker.to_numpy(); bad = np.zeros(len(A), bool)
    for i in np.flatnonzero(seam):
        lo_, hi_ = max(i - 60, 0), min(i + 60, len(A) - 1); bad[lo_:hi_ + 1] |= (tk0[lo_:hi_ + 1] == tk0[i])
    pv = g.volume.shift(1)
    v20 = g.volume.transform(lambda s: s.shift(2).rolling(20, min_periods=10).mean())
    rg = (A.high - A.low).replace(0, np.nan)
    body = (A.close - A.open) / A.open * 100
    base = (A.mk == "KOSDAQ") & A["cap억"].between(1000, 5000) & (A.volume >= 5 * pv) & (pv > 0) & (A.close > A.open) \
        & ((A.high - A.close) / rg <= 0.1) & ((A.open - A.low) / rg <= 0.1)
    A["quiet"] = pv <= v20                                              # 거래량 죽어 있다가(전날이 그 전 20일 평균 이하)
    A["body"] = body
    sig = A[base.fillna(False) & (body >= 5) & ~bad].copy()
    P("M3 신호(코스닥 1천~5천억 · 거래량 전날 5배 · 꼬리 없는 장대양봉 몸통 5%%↑): %d건 · 몸통 10%%↑ %d · 조용하다 터짐 %d" % (len(sig), (sig.body >= 10).sum(), sig.quiet.sum()))
    O, H, L, Cc, TK, DT = A.open.values, A.high.values, A.low.values, A.close.values, A.ticker.values, A.date.values
    # 같은 날 비교군: 코스닥 1천~5천억 아무 종목 다음날 시가 → 20일 뒤 종가
    A["f20"] = (g.close.shift(-20) / g.open.shift(-1) - 1) * 100
    A.loc[A.f20.abs() > 300, "f20"] = np.nan
    grp = (A.mk == "KOSDAQ") & A["cap억"].between(1000, 5000)
    bm = A.loc[grp].groupby("date").f20.mean()
    rows = []
    for ix, s in sig.iterrows():
        n = ix + 1
        if n >= len(A) or TK[n] != s.ticker: continue
        lo, cl, op = s.low, s.close, s.open
        bd = cl - op
        rec = dict(date=s.date, ticker=s.ticker, body=s.body, quiet=bool(s.quiet), gapup=O[n] > cl, x20=np.nan)
        if n + 20 < len(A) and TK[n + 20] == s.ticker:
            rec["x20"] = (Cc[n + 19] / O[n] - 1) * 100 - bm.get(s.date, np.nan)
        for nm, lvl in (("시가", None), ("1/3", cl - bd / 3), ("1/2", cl - bd / 2)):
            if lvl is None: px = O[n]; slip = SLIP
            else:
                if L[n] > lvl: rec[nm] = np.nan; continue
                px = min(O[n], lvl); slip = 0
            stop = lo; tgt = px + 2 * (px - stop)
            if px <= stop: rec[nm] = np.nan; continue
            ret = None; st = 0
            # 진입일: 지정가 체결 뒤 같은 날 손절 닿았으면(저가 ≤ 손절) 손절로 셈
            if L[n] <= stop: ret = (min(stop, O[n]) / px - 1) * 100 if lvl is None else (stop / px - 1) * 100; st = 1
            else:
                end = n
                for j in range(n + 1, min(n + 21, len(A))):
                    if TK[j] != s.ticker: break
                    end = j
                    if L[j] <= stop: ret = (min(stop, O[j]) / px - 1) * 100; st = 1; break
                    if H[j] >= tgt: ret = (max(tgt, O[j]) / px - 1) * 100; break
                if ret is None: ret = (Cc[end] / px - 1) * 100
            rec[nm] = ret - FEE - slip - SLIP * st
        rows.append(rec)
    E = pd.DataFrame(rows)
    E["per"] = np.where(E.date <= "20151231", "옛날", np.where(E.date <= "20221231", "학습", "검증"))
    P("\n## M3a 매집 돌파(일봉 2005~) — 다음날 진입 · 손절 장대양봉 저가 · 목표 2:1 · 최대 20일 (비용 뒤 평균 · 승률 · 건수)")
    P("| 판 | 옛날 ~15 | 학습 16~22 | 검증 23~ |"); P("|---|---|---|---|")
    def row(nm, m, col):
        cs = []
        for p in ("옛날", "학습", "검증"):
            x = E.loc[m & (E.per == p), col].dropna()
            cs.append("%d건 평균 %+.2f · 중앙 %+.2f · %.0f%%" % (len(x), x.clip(-50, 50).mean(), x.median(), (x > 0).mean() * 100) if len(x) >= 5 else "%d건" % len(x))
        P("| %s | %s |" % (nm, " | ".join(cs)))
    P("(평균 = ±50%% 자름)")
    al = E.body > 0
    for nm, col in (("다음날 시가 매수(비교)", "시가"), ("몸통 1/3 눌림 지정가(영상)", "1/3"), ("몸통 1/2 눌림 지정가", "1/2")):
        row(nm, al, col)
        row("  └ 거래량 죽어 있다가(전날 ≤ 20일 평균)", E.quiet, col)
        row("  └ 몸통 10%↑", E.body >= 10, col)
    row("20일 보유 − 같은 날 코스닥 1천~5천억 아무 종목(초과)", al, "x20")
    E.to_pickle(CACHE / "yt_candle_m3.pkl")
    m3 = {(r.ticker, r.date): (sig.loc[(sig.ticker == r.ticker) & (sig.date == r.date), "low"].iloc[0], sig.loc[(sig.ticker == r.ticker) & (sig.date == r.date), "close"].iloc[0])
          for r in E[E.date >= "20221101"].itertuples()}
    mkmap = A.groupby("ticker").mk.last().to_dict()
    return m3, mkmap


def main():
    only_m3 = len(sys.argv) > 1 and sys.argv[1] == "m3"
    m3, mkmap = m3_daily()
    files = sorted(glob.glob(str(M1DIR / "*.parquet")))
    tks3 = {t for t, _ in m3}
    args = [(f, mkmap.get(Path(f).stem), m3, only_m3) for f in files if mkmap.get(Path(f).stem) in ("KOSPI", "KOSDAQ") and (not only_m3 or Path(f).stem in tks3)]
    P("\n1분봉 종목 %d" % len(args))
    T = []
    with ProcessPoolExecutor(8) as ex:
        for i, r in enumerate(ex.map(one, args, chunksize=8)):
            T += r
            if i % 300 == 0: print("  ..%d" % i, flush=True)
    E = pd.DataFrame(T, columns=["k", "liq", "date", "r"])
    E["per"] = np.where(E.date <= "20241231", "학습 ~24", "검증 25~")
    E.to_pickle(CACHE / ("yt_candle_m1%s.pkl" % ("_m3" if only_m3 else "")))
    P("\n## 1분봉(2022-12~) — 비용 뒤 평균 · 승률 · 건수")
    P("| 판 | 거래대금 | 학습 ~24 | 검증 25~ |"); P("|---|---|---|---|")
    for k in sorted(E.k.unique()):
        for lq in ("전체",) + tuple(sorted(E[E.k == k].liq.unique()) if E[E.k == k].liq.nunique() > 1 else ()):
            Z = E[(E.k == k) & ((E.liq == lq) if lq != "전체" else True)]
            cs = []
            for p in ("학습 ~24", "검증 25~"):
                x = Z.loc[Z.per == p, "r"]
                cs.append("%d건 평균 %+.2f · 중앙 %+.2f · %.0f%%" % (len(x), x.mean(), x.median(), (x > 0).mean() * 100) if len(x) >= 5 else "%d건" % len(x))
            P("| %s | %s | %s |" % (k, lq, " | ".join(cs)))
    (CACHE / "yt_candle.out").write_text("\n".join(OUT), encoding="utf-8")


if __name__ == "__main__":
    main()
