# -*- coding: utf-8 -*-
"""장중 진입 규칙 찾기 — 10분봉 연속 상승 × 외국인 매집 (2026-11-16 사용자 "장중에 특정 조건일 때 매수하고 장 마감이나 특정 조건일 때 매도 ·
예: 10분봉 기준 연속 상승인데 외국인 보유량도 같이 오르거나").

자료: 토스 1분봉 data/m1/KR/bf(2022-12~, 보통주) · 외국인·기관 순매수 investor.db flow11(원, 장 마감 뒤 확정 → **어제까지**만 쓴다 —
      장중 외국인 잠정치·보유량은 과거 자료가 없다). 학습 2022-12~2024 · 검증 2025~.
신호: 10분봉 N개 연속 상승(N=3·4·5·6, 그날 처음 나온 것, 신호 봉 끝 ≤ 13:30) · 거울 = N개 연속 하락.
매수: 신호 봉 끝난 다음 첫 체결 분 시가 · 비용 0.23 + 미끄러짐 0.05.
매도 8종: 30분 뒤 x30 · 60분 뒤 x60 · 종가 xc · 첫 하락 10분봉 xdn · 고점(10분봉 종가) 대비 -1.5% xtr · 손절 -2%/익절 +3%(아니면 종가) xst ·
          손절 -2%만(아니면 종가) xsl · 다음 날 시가 xno
거르개(run): 매수가 1천원↑ · 어제 종가 +25% 미만 · 20일 평균 거래대금 3억↑(1분봉 합).
대조: 같은 날·같은 30분 칸에 아무 종목을 사서 같은 매도(x30·x60·xc·xno).
    python research/memguard.py research/m10_1116.py run      (LIM=50 으로 시험)
    python research/m10_1116.py rep
"""
import glob, math, os, pickle, sqlite3, sys, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
if sys.stdout is not None: sys.stdout.reconfigure(encoding="utf-8")
MK = os.environ.get("MK", "kr")                 # 2026-11-16 사용자 "미장도 같은 방식으로" — MK=us 면 미장(외국인 수급 조건 없음)
OUTD = Path("C:/temp/kp/m10" + ("_us" if MK == "us" else "")); OUTD.mkdir(parents=True, exist_ok=True)
NMIN, START, COST = 391, 9 * 60 + 1, 0.28
MINP, MINA, LIMUP, MDIR, TZ = 1000, 3e8, 1.25, "KR", None
if MK == "us": START, COST, MINP, MINA, LIMUP, MDIR, TZ = 9 * 60 + 31, 0.30, 5, 1e6, 1.5, "US", "America/New_York"
NB = 38                                         # 10분봉 38개(09:10~15:20 끝)
NS = (3, 4, 5, 6)
LASTB = 26                                      # 신호 봉 끝 ≤ 13:30
EXN = ("x30", "x60", "xc", "xdn", "xtr", "xst", "xsl", "xno")
BASEX = ("x30", "x60", "xc", "xno")
PER = (("학습 22.12~24", "20221201", "20241231"), ("검증 25~", "20250101", "20991231"))
if MK == "us": PER = (("학습 21.12~24", "20211201", "20241231"), ("검증 25~", "20250101", "20991231"))


def load(f):
    B = pd.read_parquet(f, columns=["ts", "o", "c", "v"])
    k = pd.DatetimeIndex(pd.to_datetime(B.ts.values, unit="s", utc=True)).tz_convert(TZ) if TZ else pd.to_datetime(B.ts.values + 9 * 3600, unit="s")
    mi = (k.hour * 60 + k.minute).values - START
    ok = (mi >= 0) & (mi < NMIN)
    B = B[ok]; day = k.strftime("%Y%m%d")[ok]; mi = mi[ok]
    days, di = np.unique(day, return_inverse=True)
    O = np.full((len(days), NMIN), np.nan); C = np.full((len(days), NMIN), np.nan); V = np.zeros((len(days), NMIN))
    O[di, mi] = B.o.values; C[di, mi] = B.c.values; V[di, mi] = B.v.values
    tr = V > 0; O[~tr] = np.nan
    Cf = pd.DataFrame(np.where(tr, C, np.nan)).ffill(axis=1).values
    return days, O, Cf, V


def run():
    files = sorted(glob.glob(str(BASE / "data" / "m1" / MDIR / "bf" / "*.parquet")))
    if os.environ.get("LIM"): files = files[::max(1, len(files) // int(os.environ["LIM"]))]
    ev, base = [], {}
    for fi, f in enumerate(files):
        t = Path(f).stem
        if MK == "kr" and not t.endswith("0"): continue
        try: days, O, Cf, V = load(f)
        except Exception: continue
        nD = len(days)
        if nD < 40: continue
        j = np.argmax(~np.isnan(O), axis=1); op = O[np.arange(nD), j]; op[np.isnan(O).all(axis=1)] = np.nan
        cl = Cf[:, -1]; pc = np.r_[np.nan, cl[:-1]]; nop = np.r_[op[1:], np.nan]
        hi = np.nanmax(Cf, axis=1); phi = np.r_[np.nan, hi[:-1]]
        valc = np.nancumsum(np.where(V > 0, Cf * V, 0), axis=1)
        dval = valc[:, -1]
        a20 = pd.Series(dval).rolling(20, min_periods=10).mean().shift(1).values
        tr = V > 0
        nxt = np.full((nD, NMIN + 1), -1, dtype=np.int32)
        for m in range(NMIN - 1, -1, -1): nxt[:, m] = np.where(tr[:, m], m, nxt[:, m + 1])
        dint = days.astype(np.int32)
        okday = (a20 >= MINA) & ~np.isnan(pc)

        def px_at(rows, m):
            """m 분 이후 첫 체결 분 시가(없으면 종가)."""
            e = nxt[rows, np.minimum(m, NMIN)]
            return np.where(e >= 0, O[rows, np.maximum(e, 0)], cl[rows])
        # 대조: 30분 칸 경계마다 아무 종목
        for kb in range(1, 10):
            s = 30 * kb; e = nxt[:, s]; rows = np.flatnonzero((e >= 0) & okday)
            if not len(rows): continue
            p = O[rows, e[rows]]; ok = (p >= MINP) & (p < pc[rows] * LIMUP)
            X = {"x30": Cf[rows, np.minimum(e[rows] + 30, NMIN - 1)] / p, "x60": Cf[rows, np.minimum(e[rows] + 60, NMIN - 1)] / p,
                 "xc": cl[rows] / p, "xno": nop[rows] / p}
            for q, nm in enumerate(BASEX):
                x = (X[nm][ok] - 1) * 100 - COST; dd = dint[rows][ok]; good = ~np.isnan(x) & (np.abs(x) < 40)
                sm = pd.Series(x[good]).groupby(dd[good]).agg(["sum", "count"])
                for d_, (a_, c_) in zip(sm.index, sm.values):
                    b = base.setdefault((str(d_), kb), np.zeros(2 * len(BASEX))); b[2 * q] += a_; b[2 * q + 1] += c_
        cb = Cf[:, 9::10][:, :NB]
        prv = np.column_stack([op, cb[:, :-1]])
        lo10 = np.nanmin(np.where(np.isnan(Cf[:, :NB * 10]), np.inf, Cf[:, :NB * 10]).reshape(nD, NB, 10), axis=2)
        for side, M in ((1, cb > prv), (-1, cb < prv)):
            runl = np.zeros(nD, int)
            first = {N: np.full(nD, -1) for N in NS}
            for b in range(LASTB + 1):
                runl = np.where(M[:, b], runl + 1, 0)
                for N in NS:
                    hit = (runl == N) & (first[N] < 0)
                    first[N][hit] = b
            for N in NS:
                rows = np.flatnonzero((first[N] >= 0) & okday)
                if not len(rows): continue
                b = first[N][rows]; s = 10 * (b + 1); e = nxt[rows, s]
                good = e >= 0; rows, b, s, e = rows[good], b[good], s[good], e[good]
                p = O[rows, e]
                ok = (p >= MINP) & (p < pc[rows] * LIMUP)
                rows, b, s, e, p = rows[ok], b[ok], s[ok], e[ok], p[ok]
                if not len(rows): continue
                n = len(rows); ar = np.arange(n)
                X = {"x30": Cf[rows, np.minimum(e + 30, NMIN - 1)] / p, "x60": Cf[rows, np.minimum(e + 60, NMIN - 1)] / p,
                     "xc": cl[rows] / p, "xno": nop[rows] / p}
                # 첫 하락 10분봉 · 고점 대비 -1.5% (신호 다음 봉부터, 10분봉 종가로 판단 → 다음 분 시가에 판다)
                CB = cb[rows]; kk = np.arange(NB)[None, :]
                after = kk > b[:, None]
                dn = (CB < np.column_stack([CB[:, :1], CB[:, :-1]])) & after
                kdn = np.where(dn.any(axis=1), dn.argmax(axis=1), -1)
                X["xdn"] = np.where(kdn >= 0, px_at(rows, 10 * (kdn + 1)), cl[rows]) / p
                pk = np.maximum.accumulate(np.where(kk >= b[:, None], np.nan_to_num(CB, nan=0), 0), axis=1)
                trl = (CB <= pk * 0.985) & after
                ktr = np.where(trl.any(axis=1), trl.argmax(axis=1), -1)
                X["xtr"] = np.where(ktr >= 0, px_at(rows, 10 * (ktr + 1)), cl[rows]) / p
                # 손절·익절: 1분 종가 경로
                path = Cf[rows] / p[:, None]; mm = np.arange(NMIN)[None, :] > e[:, None]
                st = (path <= 0.98) & mm; tk = (path >= 1.03) & mm
                ks = np.where(st.any(axis=1), st.argmax(axis=1), NMIN + 5); kt = np.where(tk.any(axis=1), tk.argmax(axis=1), NMIN + 5)
                kf = np.minimum(ks, kt)
                X["xst"] = np.where(kf < NMIN, path[ar, np.minimum(kf, NMIN - 1)], cl[rows] / p)
                X["xsl"] = np.where(ks < NMIN, path[ar, np.minimum(ks, NMIN - 1)], cl[rows] / p)
                start = prv[rows, b - N + 1]
                E = pd.DataFrame({"t": t, "d": days[rows], "side": side, "N": N, "b": b, "p": p,
                                  "rise": (cb[rows, b] / start - 1) * 100, "day": (p / pc[rows] - 1) * 100, "gap": (op[rows] / pc[rows] - 1) * 100,
                                  "vr": valc[rows, s - 1] / a20[rows], "a20": a20[rows], "phi": (p / phi[rows] - 1) * 100})
                for nm in EXN:
                    x = (X[nm] - 1) * 100 - COST
                    E[nm] = np.where(np.abs(x) < 40, x, np.nan).astype("float32")
                ev.append(E)
        if fi % 200 == 0: print(fi, len(files), sum(len(x) for x in ev), flush=True)
    E = pd.concat(ev, ignore_index=True)
    E.to_pickle(OUTD / "ev.pkl"); pickle.dump(base, open(OUTD / "base.pkl", "wb"))
    print("사건", len(E), "대조 칸", len(base))


def flows():
    c = sqlite3.connect("file:" + str(BASE / "data" / "investor.db") + "?mode=ro", uri=True)
    F = pd.read_sql("SELECT ticker t, date d, frgn, fin+ins+tru+pef+bank+ofin+pens AS inst, indiv FROM flow11 WHERE date >= '20221001'", c)
    F = F.sort_values(["t", "d"]).reset_index(drop=True); g = F.groupby("t", sort=False)
    out = F[["t", "d"]].copy()
    for k in ("frgn", "inst", "indiv"):
        for w in (1, 5, 20):
            out["%s%d" % (k[0], w)] = g[k].transform(lambda s: s.rolling(w, min_periods=1).sum())
    pos = (F.frgn > 0).astype(int)
    out["fstreak"] = pos.groupby((pos != pos.groupby(F.t).shift()).cumsum()).cumsum() * pos       # 외국인 연속 순매수 일수
    # 어제까지만: 다음 거래일 행에 붙인다
    out["d"] = g.d.shift(-1)
    return out.dropna(subset=["d"])


def st(Z, col, B):
    Z = Z.dropna(subset=[col])
    if len(Z) < 30: return None
    d = Z.groupby("d")[col].mean()
    ctl = (Z[col] - Z["c_" + col]).dropna() if "c_" + col in Z else None
    dc = (Z.assign(e=Z[col] - Z["c_" + col]).groupby("d").e.mean()) if ctl is not None else None
    t = lambda s: s.mean() / s.std(ddof=1) * math.sqrt(len(s)) if len(s) > 2 and s.std(ddof=1) > 0 else 0
    return dict(n=len(Z), days=len(d), mean=Z[col].mean(), win=(Z[col] > 0).mean() * 100, dm=d.mean(), t=t(d),
                ex=dc.mean() if dc is not None else np.nan, ext=t(dc) if dc is not None else np.nan)


def rep():
    OUT = []; P = lambda s="": (OUT.append(s), print(s, flush=True))
    E = pd.read_pickle(OUTD / "ev.pkl"); base = pickle.load(open(OUTD / "base.pkl", "rb"))
    E["kb"] = np.clip((E.b + 1) // 3 + ((E.b + 1) % 3 > 0), 1, 9)                     # 신호 봉 끝이 속한 30분 칸 경계(올림)
    Bd = pd.DataFrame([(d, kb, *[v[2 * q] / v[2 * q + 1] if v[2 * q + 1] else np.nan for q in range(len(BASEX))]) for (d, kb), v in base.items()],
                      columns=["d", "kb"] + ["c_" + x for x in BASEX])
    E = E.merge(Bd, on=["d", "kb"], how="left")
    if MK == "us":
        for k_ in ("f1", "f5", "f20", "i1", "i5", "i20", "fstreak"): E[k_] = np.nan
    else:
        E = E.merge(flows(), on=["t", "d"], how="left")
    for k in ("f", "i"):
        for w in (1, 5, 20): E["%s%dr" % (k, w)] = E["%s%d" % (k, w)] / E.a20 * 100
    P("사건 %d · 종목 %d · %s~%s · 외국인 자료 붙은 비율 %.0f%%\n" % (len(E), E.t.nunique(), E.d.min(), E.d.max(), E.f5.notna().mean() * 100))

    def table(title, sets, exits=("x30", "x60", "xc", "xdn", "xtr", "xst", "xsl", "xno")):
        P("\n### %s\n" % title)
        P("| 판 | 매도 | 학습 건·날 | 학습 건당 | 학습 날 바구니(t) | 학습 대조 대비 | 검증 건·날 | 검증 건당 | 검증 날 바구니(t) | 검증 대조 대비 |"); P("|---|---|---|---|---|---|---|---|---|---|")
        for nm, Z in sets:
            for x in exits:
                r = [st(Z[(Z.d >= a) & (Z.d <= b)], x, None) for _, a, b in PER]
                if not r[0] or not r[1]: continue
                c = lambda s: "%d·%d | %+.2f%% | %+.2f%% (%.1f) | %s" % (s["n"], s["days"], s["mean"], s["dm"], s["t"], ("%+.2f" % s["ex"]) if s["ex"] == s["ex"] else "-")
                flag = " ★" if r[0]["dm"] > 0 and r[1]["dm"] > 0 and r[0]["t"] >= 2 and r[1]["t"] >= 2 else ""
                P("| %s%s | %s | %s | %s |" % (nm, flag, x, c(r[0]), c(r[1])))
    U = E[E.side == 1]; Dn = E[E.side == -1]
    table("1. 말한 그대로 — 10분봉 N연속 상승(조건 없음)", [("N=%d" % N, U[U.N == N]) for N in NS])
    table("2. 외국인 조건(어제까지) × N연속 상승", [(nm, U[(U.N == N) & m(U)]) for N in (3, 4, 5) for nm, m in (
        ("N=%d · 외국인 5일 순매수 +" % N, lambda z: z.f5r > 0), ("N=%d · 외국인 5일 ÷ 거래대금 5%%↑" % N, lambda z: z.f5r >= 5),
        ("N=%d · 외국인 3일↑ 연속 순매수" % N, lambda z: z.fstreak >= 3), ("N=%d · 외국인 5일·20일 둘 다 +" % N, lambda z: (z.f5r > 0) & (z.f20r > 0)),
        ("N=%d · 외국인 20일 ÷ 거래대금 20%%↑" % N, lambda z: z.f20r >= 20), ("N=%d · 외국인+기관 5일 둘 다 +" % N, lambda z: (z.f5r > 0) & (z.i5r > 0)),
        ("N=%d · 외국인 5일 순매도(반대)" % N, lambda z: z.f5r < 0))], exits=("x60", "xc", "xdn", "xtr", "xst", "xno"))
    table("3. 변형 — 시각·상승 폭·거래대금·전고점·갭 (N=3·4)", [(nm, U[U.N.isin([3, 4]) & m(U)]) for nm, m in (
        ("신호 ≤ 10:00", lambda z: z.b <= 5), ("신호 10:00~11:30", lambda z: (z.b > 5) & (z.b <= 14)), ("신호 11:30~13:30", lambda z: z.b > 14),
        ("연속 상승 폭 < 1.5%", lambda z: z.rise < 1.5), ("상승 폭 1.5~4%", lambda z: (z.rise >= 1.5) & (z.rise < 4)), ("상승 폭 4%↑", lambda z: z.rise >= 4),
        ("거래대금 그 시각까지 20일 평균의 50%↑", lambda z: z.vr >= 0.5), ("거래대금 100%↑", lambda z: z.vr >= 1.0), ("거래대금 20%↓(조용)", lambda z: z.vr < 0.2),
        ("어제 고가 위", lambda z: z.phi > 0), ("어제 고가 아래", lambda z: z.phi <= 0), ("갭 하락 출발(-1%↓)", lambda z: z.gap <= -1), ("갭 상승 출발(+1%↑)", lambda z: z.gap >= 1),
        ("어제 종가 아래에서 연속 상승", lambda z: z.day < 0), ("큰 종목(거래대금 100억↑·미장 1억달러↑)", lambda z: z.a20 >= (1e10 if MK == "kr" else 1e8)), ("작은 종목(20억↓·미장 1천만달러↓)", lambda z: z.a20 < (2e9 if MK == "kr" else 1e7)))],
          exits=("x60", "xc", "xdn", "xtr", "xst", "xno"))
    table("4. 외국인 × 변형 겹치기 (N=3·4 · 외국인 5일 +)", [(nm, U[U.N.isin([3, 4]) & (U.f5r > 0) & m(U)]) for nm, m in (
        ("어제 고가 위", lambda z: z.phi > 0), ("거래대금 50%↑", lambda z: z.vr >= 0.5), ("신호 ≤ 10:00", lambda z: z.b <= 5), ("상승 폭 1.5~4%", lambda z: (z.rise >= 1.5) & (z.rise < 4)),
        ("어제 종가 아래", lambda z: z.day < 0), ("큰 종목", lambda z: z.a20 >= 1e10), ("외국인 3일↑ 연속 + 어제 고가 위", lambda z: (z.fstreak >= 3) & (z.phi > 0)))],
          exits=("x60", "xc", "xdn", "xtr", "xst", "xno"))
    table("5. 거울 — 10분봉 N연속 하락 뒤 매수(되돌림)", [("N=%d 하락" % N, Dn[Dn.N == N]) for N in NS] + [
        ("N=3·4 하락 · 외국인 5일 +", Dn[Dn.N.isin([3, 4]) & (Dn.f5r > 0)]), ("N=3·4 하락 · 외국인 5일 5%↑", Dn[Dn.N.isin([3, 4]) & (Dn.f5r >= 5)]),
        ("N=3·4 하락 · 낙폭 4%↑", Dn[Dn.N.isin([3, 4]) & (Dn.rise <= -4)]), ("N=3·4 하락 · 갭 하락 출발", Dn[Dn.N.isin([3, 4]) & (Dn.gap <= -1)])],
          exits=("x60", "xc", "xst", "xno"))
    (ROOT / ("m10_1116%s.out" % ("_us" if MK == "us" else ""))).write_text("\n".join(OUT), encoding="utf-8")


if __name__ == "__main__":
    {"run": run, "rep": rep}[sys.argv[1]]()
