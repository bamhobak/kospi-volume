# -*- coding: utf-8 -*-
"""1억 1년 — 기존 규칙 없이 새로 찾기(2026-11-05 사용자 "기존 규칙은 쓰지 말고 너가 새롭게 찾아서 해야지").
규율(결과 보기 전에 고정):
  자료 = 일봉으로 만든 '어제까지' 재료 49개(feats.make · 시가 갭·수급·테마·미장 전이 안 씀) · 유니버스 = 거래대금 상위 40%(1천원↑·우선주 X)
  방식 = 시가→종가(oc) · 시가 매수 → 5·10·20거래일째 종가 매도(sw5·sw10·sw20) · 비용 0.23
  찾기 2016~2022: 재료 하나(아래·위 10·20·30%) → 방식마다 날 바구니 평균 위 15(재료마다 한 칸, 거르지 않음) → 둘씩·위 8 셋씩 묶음
     · 통과 = 날 바구니 t≥2.5 · 플러스 해 5/7↑ · 날 200↑
     (11-05 1차: 재료 하나부터 t≥3·5/7 로 거르니 0칸 — 유니버스 평균이 비용 뒤 -0.4% 라 하나짜리는 전멸. 굴리기 결과 보기 전에 바꿈)
  확인 2023-01~2025-10(끝나는 날이 10-31 안인 매수만): 건당 ≥ +0.5% · 날 바구니 t≥2 · 중앙 > 0 · 플러스 해 2/3↑
  방식마다 확인 통과 중 '확인 구간 날 바구니 평균' 1등 하나 · 기존 규칙과 닮으면(5일↑ 보유인데 깊은 과매도 조건 = 폭락반등·낙폭과대·깊은 이격 계열,
  52주 고가 근처+거래량 적음 = 조용한 신고가) 다음 순위
  돈 = 뽑힌 방식에 똑같이 나눔 · 한 종목 금액(그 칸 자산의 0.5·1·2·4%)은 2016~2025-10 계좌로 해 수익 중앙값 1등 · 체결 손해 모형 = 실행 실측(t1_size_liq_1021)
  굴리기 2025-11-05~2026-11-04 · 고치지 않음 · 끝나는 날을 넘기는 매수는 안 함
    python research/y2_search.py
"""
import io, contextlib, sys, itertools
from pathlib import Path
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "factory"))
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
import FinanceDataReader as fdr
import feats as FT

COST, CAPTURE = 0.23, 1.0
F = ["r1", "r5", "r20", "r60", "clv", "rng", "vm", "vm5", "fh", "fl", "d5", "d20", "d60", "vol20", "dn", "up", "amt20", "liq", "px", "mk_r1", "mk_r5",
     "hi250", "lo250", "hi60", "d120", "d224", "rsi14", "bbp", "bbw", "macd", "ich", "uw", "lw", "body", "lu20", "age", "mcap", "align", "engulf",
     "d50", "d200", "st_up", "lr50", "vbrk", "c40", "bigd", "bodyr", "sweep", "turn"]
MODES = {"oc": 1, "sw5": 5, "sw10": 10, "sw20": 20}
LEARN, VALID, RUN = ("20160101", "20221231"), ("20230101", "20251031"), ("20251105", "20261104")
CACHE = BASE / "data" / "y2_hist.pkl"
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))
DEEP = {"r20", "r60", "d20", "d50", "d60", "rsi14", "bbp", "fl", "d5", "lo250", "fh", "hi60", "ich", "r5"}   # 아래쪽이면 '깊은 과매도'


def hist():
    if CACHE.exists(): return pd.read_pickle(CACHE)
    A = pd.read_pickle(BASE / "data" / "y1_kr.pkl")
    A = A[A.date >= "20140101"].copy()
    X = FT.make(A, mk="KR")
    X = X[X.uni & (X.date >= "20160101")].reset_index(drop=True)
    U = X[["ticker", "date", "oc"] + ["sw5", "sw10", "sw20"] + F].copy()
    for k in ("sw5", "sw10", "sw20"): U[k] = U[k] + 0.6               # make 의 매일 자료 길은 비용 0.6 을 미리 뺐다 → 되돌리고 아래서 0.23
    gd = U.groupby("date")
    for f in F: U["q_" + f] = gd[f].rank(pct=True).astype("float32")
    U = FT.shrink(U); U.to_pickle(CACHE); return U


class Scorer:
    def __init__(s, U):
        s.U = U
        d = U.date.to_numpy(); s.days = np.array(sorted(set(d))); s.code = np.searchsorted(s.days, d)
        s.yr = U.date.str[:4].to_numpy()
        s.Q = {f: U["q_" + f].to_numpy() for f in F}
        s.Y = {m: U[m].to_numpy().astype(float) - COST for m in MODES}
        s.per = {}
        for nm, (lo, hi) in (("L", LEARN), ("V", VALID), ("R", RUN)):
            s.per[nm] = (d >= lo) & (d <= hi)
        for m, h in MODES.items():                                       # 확인 구간은 끝나는 날이 10-31 안인 매수만
            cut = s.days[np.searchsorted(s.days, VALID[1], side="right") - h] if h > 1 else VALID[1]
            s.per["V" + m] = s.per["V"] & (d <= cut)

    def mask(s, conds):
        m = np.ones(len(s.U), bool)
        for f, side, q in conds:
            v = s.Q[f]; m &= (v <= q) if side == "lo" else (v >= 1 - q)
        return m

    def score(s, m, mode, per):
        y = s.Y[mode]; sel = m & s.per[per] & np.isfinite(y)
        if sel.sum() < 30: return None
        c = s.code[sel]; yy = y[sel]
        sm = np.bincount(c, yy, minlength=len(s.days)); n = np.bincount(c, minlength=len(s.days)); k = n > 0
        dm = sm[k] / n[k]
        yrs = pd.Series(yy).groupby(s.yr[sel]).mean()
        return dict(n=int(sel.sum()), nd=int(k.sum()), dmean=dm.mean(), t=dm.mean() / (dm.std() + 1e-9) * np.sqrt(k.sum()),
                    avg=yy.mean(), med=np.median(yy), win=(yy > 0).mean() * 100, ypos=int((yrs > 0).sum()), ny=len(yrs))


def txt(conds):
    return " & ".join("%s %s%d%%" % (f, "아래" if side == "lo" else "위", q * 100) for f, side, q in conds)


def existing_like(conds, mode):
    if MODES[mode] >= 5 and any(side == "lo" and f in DEEP for f, side, q in conds): return "깊은 과매도 스윙(폭락반등·낙폭과대·깊은 이격 계열)"
    fs = {(f, side) for f, side, q in conds}
    if ("hi250", "hi") in fs and (("vm", "lo") in fs or ("vm5", "lo") in fs): return "조용한 신고가 계열"
    return None


def impact():
    import t1_size_liq_1021 as SL
    with contextlib.redirect_stdout(io.StringIO()):
        ab, cf = SL.fit(SL.liq_of_exec())
    return (lambda p: np.maximum(0.0, ab[0] + ab[1] * np.sqrt(p))), (lambda p: 1 / (1 + cf * p))


def acct(S, m, mode, lo, hi, base, imp, fill, eq0, isc=1.0):
    """한 칸 계좌 — 시가 매수, h 거래일째 종가 매도. 자산 = 현금 + 들고 있는 원금(장부). 날짜별 자산(실현 기준)."""
    h = MODES[mode]; U = S.U
    days = S.days[(S.days >= lo) & (S.days <= hi)]
    di = {d: i for i, d in enumerate(days)}
    sel = m & (U.date.to_numpy() >= lo) & (U.date.to_numpy() <= hi) & np.isfinite(S.Y[mode])
    Z = pd.DataFrame({"date": U.date.to_numpy()[sel], "y": S.Y[mode][sel], "a20": U.amt20.to_numpy()[sel] * 1e8}).sort_values(["date", "a20"], ascending=[True, False])
    G = {d: g for d, g in Z.groupby("date")}
    cash, held, out = eq0, {}, {}
    for i, d in enumerate(days):
        for back in held.pop(i, []): cash += back                       # 오늘 종가에 끝나는 몫
        g = G.get(d)
        if g is not None and i + h - 1 < len(days):
            eq = cash + sum(sum(v) for v in held.values())
            unit = eq * base
            for y, a20 in zip(g.y.to_numpy(), g.a20.to_numpy()):
                if cash < unit: break
                p = unit / a20 * 100
                fl = 1 / (1 + isc * (1 / fill(p) - 1)); inv = unit * fl
                back = inv * (1 + (y - isc * imp(p)) / 100 * CAPTURE)
                cash -= inv
                if h == 1: cash += back
                else: held.setdefault(i + h - 1, []).append(back)
        out[d] = cash + sum(sum(v) for v in held.values())
    return pd.Series(out)


def yearly(path, eq0):
    s = path.copy(); s.index = s.index.str[:4]; out, prev = {}, eq0
    for y, v in s.groupby(level=0):
        out[y] = (v.iloc[-1] / prev - 1) * 100; prev = v.iloc[-1]
    return out


def main():
    U = hist(); S = Scorer(U)
    P("자료 %s줄 · %s~%s · 재료 %d개" % (f"{len(U):,}", U.date.min(), U.date.max(), len(F)))
    picks = {}
    for mode in MODES:
        P("\n## 방식 %s\n" % mode)
        singles = []
        for f in F:
            for side in ("lo", "hi"):
                for q in (0.1, 0.2, 0.3):
                    r = S.score(S.mask([(f, side, q)]), mode, "L")
                    if r and r["nd"] >= 200: singles.append(((f, side, q), r))
        best = {}
        for c, r in sorted(singles, key=lambda x: -x[1]["dmean"]):     # 재료마다 가장 좋은 칸 하나
            best.setdefault(c[0], (c, r))
        top = sorted(best.values(), key=lambda x: -x[1]["dmean"])[:15]
        P("재료 하나 위 15: %s" % ", ".join("%s(%+.2f)" % (txt([c]), r["dmean"]) for c, r in top))
        cands = [[c] for c, _ in top] + [[a[0], b[0]] for a, b in itertools.combinations(top, 2)]               + [[a[0], b[0], c[0]] for a, b, c in itertools.combinations(top[:8], 3)]
        rows = []
        for cs in cands:
            m = S.mask(cs); rl = S.score(m, mode, "L")
            if not (rl and rl["t"] >= 2.5 and rl["ypos"] >= 5 and rl["nd"] >= 200): continue
            rv = S.score(m, mode, "V" + mode)
            ok = bool(rv and rv["avg"] >= 0.5 and rv["t"] >= 2 and rv["med"] > 0 and rv["ypos"] >= 2)
            rows.append((cs, rl, rv, ok))
        P("찾기 통과 %d칸 · 확인 통과 %d칸" % (len(rows), sum(r[3] for r in rows)))
        P("| 조건 | 찾기(2016~22) 건·건당·날 t | 확인(2023~25-10) 건·건당·승률·중앙·날 평균·t | 통과 |"); P("|---|---|---|---|")
        for cs, rl, rv, ok in sorted(rows, key=lambda x: -(x[2]["dmean"] if x[2] else -9))[:10]:
            P("| %s | %d · %+.2f%% · %.1f | %s | %s |" % (txt(cs), rl["n"], rl["avg"], rl["t"],
              ("%d · %+.2f%% · %.0f%% · %+.2f · %+.2f · %.1f" % (rv["n"], rv["avg"], rv["win"], rv["med"], rv["dmean"], rv["t"])) if rv else "-", "O" if ok else ""))
        for cs, rl, rv, ok in sorted([r for r in rows if r[3]], key=lambda x: -x[2]["dmean"]):
            why = existing_like(cs, mode)
            if why: P("· %s — 기존 규칙과 닮음(%s) → 다음" % (txt(cs), why)); continue
            picks[mode] = (cs, rl, rv); P("**뽑힘: %s**" % txt(cs)); break
        if mode not in picks: P("뽑힌 것 없음")
    if not picks:
        P("\n어느 방식도 확인을 통과 못 함 — 현금"); (ROOT / "y2_search.out").write_text("\n".join(OUT), encoding="utf-8"); return
    imp, fill = impact()
    share = 1e8 / len(picks)
    P("\n## 한 종목 금액 고르기(2016~2025-10 계좌, 칸마다 %s원 시작)\n" % f"{share:,.0f}")
    cfg = {}
    for mode, (cs, _, _) in picks.items():
        m = S.mask(cs); best = None
        for base in (0.005, 0.01, 0.02, 0.04):
            y = yearly(acct(S, m, mode, LEARN[0], VALID[1], base, imp, fill, share), share)
            md = np.median(list(y.values()))
            P("· %s 기본 %.1f%%: 해 중앙 %+.1f%% · 최악 %+.1f%% · %s" % (mode, base * 100, md, min(y.values()), " ".join("%s %+.0f" % kv for kv in y.items())))
            if best is None or md > best[0]: best = (md, base)
        cfg[mode] = best[1]
    P("\n## 굴리기 %s~%s (1억 · 고친 것 없음)\n" % RUN)
    days = S.days[(S.days >= RUN[0]) & (S.days <= RUN[1])]
    res = {}
    for isc, lb in ((1.0, "새로 찾은 방법"), (0.5, "— 체결 손해 절반이면"), (0.0, "— 체결 손해 없으면")):
        tot = 0
        for mode, (cs, _, _) in picks.items():
            path = acct(S, S.mask(cs), mode, *RUN, cfg[mode], imp, fill, share, isc).reindex(days).ffill().fillna(share)
            tot = tot + path
            if isc == 1.0: res["  └ " + mode] = path * len(picks)               # 그 칸만 1억이었다면
        res[lb] = tot
    for sym, k in (("KS11", "코스피 그냥 들고 있기"), ("KQ11", "코스닥 그냥 들고 있기")):
        X = fdr.DataReader(sym, "2025-10-01"); X.index = X.index.strftime("%Y%m%d")
        res["참고: " + k] = (1e8 * X.Close / X.Close[X.index < RUN[0]].iloc[-1]).reindex(days).ffill()
    P("| 판 | 1년 뒤 | 수익 | 가장 크게 빠진 폭(실현 기준) |"); P("|---|---|---|---|")
    for k, s in res.items():
        s = s.dropna(); P("| %s | %s원 | %+.1f%% | %.1f%% |" % (k, f"{s.iloc[-1]:,.0f}", (s.iloc[-1] / 1e8 - 1) * 100, (s / s.cummax() - 1).min() * 100))
    M = pd.DataFrame(res); M.index = pd.to_datetime(M.index)
    P("\n월말 자산(만원):"); P("| 월 | " + " | ".join(res) + " |"); P("|---" * (len(res) + 1) + "|")
    for d, r in M.resample("ME").last().iterrows():
        P("| %s | %s |" % (d.strftime("%Y-%m"), " | ".join(f"{v / 1e4:,.0f}" for v in r)))
    for mode, (cs, _, _) in picks.items():
        r = S.score(S.mask(cs), mode, "R")
        if r: P("굴리기 구간 %s 신호: %d건 · 건당 %+.2f%%(비용 뒤·체결 손해 전) · 승률 %.0f%% · 중앙 %+.2f" % (mode, r["n"], r["avg"], r["win"], r["med"]))
    M.to_pickle(BASE / "data" / "y2_paths.pkl")
    (ROOT / "y2_search.out").write_text("\n".join(OUT), encoding="utf-8")


if __name__ == "__main__":
    main()
