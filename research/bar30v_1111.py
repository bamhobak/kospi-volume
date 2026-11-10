# -*- coding: utf-8 -*-
"""H0404~H0407 변형 판 — 장중 연속 상승·하락 × 지수 반대 방향 (2026-11-11 사용자 "말한 그대로 + 다양한 조건·변형도").

말한 그대로 판(bar30_1111.py · bar30_us_1111.py)에서 넓힌 것:
 · 봉 크기: 30분 N=2·3 · 60분 N=2(신호 11:00) · 15분 N=4
 · 시작: 개장부터(말한 그대로) · 장중 아무 때나 처음 나온 연속(신호가 장 끝 2시간 전까지)
 · 지수 조건 세기: 보합(±0.3%) · 확실(지수 반대로 0.5%↑) · 강하게(1%↑) · 없음
 · 매도: 30분 뒤 · 60분 뒤 · 종가 · 다음 날 시가 · 다음 날 종가(밤을 넘겨 들기)
 · 대상: 개장~신호 거래대금 위·아래 절반
대조 = 같은 날·같은 매수 30분 칸(신호 시각을 30분 칸으로 묶음)·같은 매도에서 같은 거르개를 통과한 아무 종목. '대조 대비' 를 같이 낸다.
    python research/bar30v_1111.py kr run|rep     python research/bar30v_1111.py us run|rep
"""
import os, sys, glob, pickle, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
os.chdir(BASE); sys.path[:0] = [str(ROOT), str(BASE)]
if sys.stdout is not None: sys.stdout.reconfigure(encoding="utf-8")
MK, CMD = sys.argv[1], sys.argv[2]
OUTD = Path("C:/temp/kp/bar30v_%s" % MK); OUTD.mkdir(parents=True, exist_ok=True)
NMIN = 391
if MK == "kr":
    TZ, START, COST, MINV, MINP, IDX = None, 9 * 60 + 1, 0.23 + 0.05, 3e8, 1000, ("069500", "229200")
    PER = (("학습 22.12~24", "20221201", "20241231"), ("검증 25~", "20250101", "20991231"))
else:
    TZ, START, COST, MINV, MINP, IDX = "America/New_York", 9 * 60 + 31, 0.25 + 0.05, 1e6, 5, ("QQQ", "SPY")
    PER = (("학습 21.12~24", "20211201", "20241231"), ("검증 25~", "20250101", "20991231"))
SPECS = (("30분×2", 30, 2), ("30분×3", 30, 3), ("60분×2", 60, 2), ("15분×4", 15, 4))
LASTSIG = 270                                   # '아무 때나' 는 신호 분 인덱스 ≤ 270(장 끝 2시간 전 — 국장 13:30·미장 14:00)
EXN = ("x30", "x60", "xc", "xno", "xnc")


def load(f):
    B = pd.read_parquet(f, columns=["ts", "o", "c", "v"])
    if TZ: k = pd.DatetimeIndex(pd.to_datetime(B.ts.values, unit="s", utc=True)).tz_convert(TZ)
    else: k = pd.to_datetime(B.ts.values + 9 * 3600, unit="s")
    mi = (k.hour * 60 + k.minute).values - START
    ok = (mi >= 0) & (mi < NMIN)
    B = B[ok]; day = k.strftime("%Y%m%d")[ok]; mi = mi[ok]
    days, di = np.unique(day, return_inverse=True)
    O = np.full((len(days), NMIN), np.nan); C = np.full((len(days), NMIN), np.nan); V = np.zeros((len(days), NMIN))
    O[di, mi] = B.o.values; C[di, mi] = B.c.values; V[di, mi] = B.v.values
    tr = V > 0; O[~tr] = np.nan
    Cf = pd.DataFrame(np.where(tr, C, np.nan)).ffill(axis=1).values
    return days, O, Cf, V


def first_open(O):
    j = np.argmax(~np.isnan(O), axis=1); v = O[np.arange(len(O)), j]; v[np.isnan(O).all(axis=1)] = np.nan
    return v


def idx_paths():
    P = {}
    for t in IDX:
        days, O, Cf, V = load(BASE / "data" / "m1" / ("KR" if MK == "kr" else "US") / "bf" / (t + ".parquet"))
        op = first_open(O)
        P[t] = {d: (Cf[i] / op[i] - 1) * 100 for i, d in enumerate(days)}
    return P


def run():
    IP = idx_paths()
    nas = {}
    if MK == "kr":
        import FinanceDataReader as fdr
        X = fdr.DataReader("IXIC", "2022-06-01"); X = X[X.Close > 0]; r = X.Close.pct_change() * 100; r.index = r.index.strftime("%Y%m%d"); nd = r.index.values
        nas_prev = lambda d: float(r.iloc[np.searchsorted(nd, d) - 1]) if np.searchsorted(nd, d) > 0 else np.nan
    else:
        nas_prev = lambda d: 0.0
    files = sorted(glob.glob(str(BASE / "data" / "m1" / ("KR" if MK == "kr" else "US") / "bf" / "*.parquet")))
    if os.environ.get("LIM"): files = files[:int(os.environ["LIM"])]
    ev, base = [], {}
    for fi, f in enumerate(files):
        t = Path(f).stem
        if t in IDX or (MK == "kr" and not t.endswith("0")): continue
        try: days, O, Cf, V = load(f)
        except Exception: continue
        nD = len(days)
        if nD < 30: continue
        op = first_open(O); cl = Cf[:, -1]
        pc = np.r_[np.nan, cl[:-1]]; nop = np.r_[op[1:], np.nan]; ncl = np.r_[cl[1:], np.nan]
        val = np.nancumsum(np.where(V > 0, Cf * V, 0), axis=1)
        tr = V > 0
        nxt = np.full((nD, NMIN + 1), -1, dtype=np.int32)                 # m 이상인 첫 체결 분(없으면 -1)
        for m in range(NMIN - 1, -1, -1):
            nxt[:, m] = np.where(tr[:, m], m, nxt[:, m + 1])
        dint = days.astype(np.int32)
        IA = {k: np.array([IP[k].get(d, np.full(NMIN, np.nan)) for d in days]) for k in IDX}
        NS_ = np.array([nas_prev(d) for d in days], dtype=float)
        lim = 1.25 if MK == "kr" else 1.5

        def vex(rows, s, e):
            """rows·s(신호 분)·e(매수 분) 배열 → 매수가와 매도 수익 5종(벡터)."""
            p = O[rows, e]
            X = {}
            for nm, k in (("x30", 30), ("x60", 60)):
                X[nm] = (Cf[rows, np.minimum(e + k, NMIN - 1)] / p - 1) * 100 - COST
            X["xc"] = (cl[rows] / p - 1) * 100 - COST
            a = nop[rows] / p - 1; X["xno"] = np.where(np.abs(a) < 0.4, a * 100 - COST, np.nan)
            a = ncl[rows] / p - 1; X["xnc"] = np.where(np.abs(a) < 0.6, a * 100 - COST, np.nan)
            ok = (p >= MINP) & (p < pc[rows] * lim) & (val[rows, s - 1] >= MINV) & ~np.isnan(pc[rows])
            return p, X, ok
        for kb in range(1, 13):                                            # 대조: 30분 칸 경계마다 아무 종목
            s = 30 * kb; e = nxt[:, s]; rows = np.flatnonzero(e >= 0)
            if not len(rows): continue
            p, X, ok = vex(rows, s, e[rows])
            for q, nm in enumerate(EXN):
                x = X[nm][ok]; dd = dint[rows][ok]; good = ~np.isnan(x)
                sm = pd.Series(x[good]).groupby(dd[good]).agg(["sum", "count"])
                for d_, (a_, c_) in zip(sm.index, sm.values):
                    b = base.setdefault((str(d_), kb), np.zeros(2 * len(EXN))); b[2 * q] += a_; b[2 * q + 1] += c_
        for si, (sn, bs, N) in enumerate(SPECS):
            nb = 390 // bs
            cb = Cf[:, bs - 1::bs][:, :nb]
            prv = np.column_stack([op, cb[:, :-1]])
            for ki, M in enumerate((cb > prv, cb < prv)):
                run_ = np.zeros(nD, int); hit = np.full(nD, -1)
                for b_ in range(nb):
                    run_ = np.where(M[:, b_], run_ + 1, 0)
                    hit = np.where((run_ >= N) & (hit < 0), b_, hit)
                rows = np.flatnonzero(hit >= 0)
                s = (hit[rows] + 1) * bs
                keep = s <= LASTSIG; rows, s = rows[keep], s[keep]
                e = nxt[rows, s]; keep = e >= 0; rows, s, e = rows[keep], s[keep], e[keep]
                if not len(rows): continue
                p, X, ok = vex(rows, s, e)
                rows, s, e, p = rows[ok], s[ok], e[ok], p[ok]
                X = {k: v[ok] for k, v in X.items()}
                ch = pd.DataFrame({"date": dint[rows], "spec": np.int8(si), "kind": np.int8(ki), "open_": hit[rows] == N - 1,
                                   "kb": np.clip(np.ceil(s / 30), 1, 12).astype(np.int8),
                                   "mv": ((Cf[rows, s - 1] / op[rows] - 1) * 100).astype("float32"), "val": val[rows, s - 1].astype("float32"),
                                   "i1": IA[IDX[0]][rows, s - 1].astype("float32"), "i2": IA[IDX[1]][rows, s - 1].astype("float32"),
                                   "nas": NS_[rows].astype("float32"), **{k: v.astype("float32") for k, v in X.items()}})
                ev.append(ch)
        if fi % 200 == 0: print(fi, len(files), sum(len(x) for x in ev), flush=True)
    E = pd.concat(ev, ignore_index=True)
    E.to_pickle(OUTD / "ev.pkl"); pickle.dump(base, open(OUTD / "base.pkl", "wb")); print("끝", len(E))


OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))


def rep():
    from verdict import log_trials
    E = pd.read_pickle(OUTD / "ev.pkl"); Bs = pickle.load(open(OUTD / "base.pkl", "rb"))
    E["date"] = E.date.astype(str); E["spec"] = E.spec.map({i: x[0] for i, x in enumerate(SPECS)}); E["kind"] = E.kind.map({0: "up", 1: "dn"})
    BL = {nm: {k: v[2 * q] / v[2 * q + 1] for k, v in Bs.items() if v[2 * q + 1] >= 20} for q, nm in enumerate(EXN)}
    nm_ = "국장" if MK == "kr" else "미장"
    P("# [%s] 장중 연속 상승·하락 × 지수 반대 — 변형 판 · 2026-11-11" % nm_); P("")
    P("- 사건 %s건 · 비용 %.2f 뒤 · 칸 = 건당 학습 / 검증 (건수) · [대조 대비 학습 / 검증] = 같은 날·같은 매수 30분 칸 아무 종목을 뺀 값" % (f"{len(E):,}", COST)); P("")
    def cellx(z, col):
        out = []
        for _, a, b in PER:
            x = z[(z.date >= a) & (z.date <= b)].dropna(subset=[col])
            if len(x) < 30: out.append("—(%d)" % len(x)); continue
            bl = np.array([BL[col].get(k, np.nan) for k in zip(x.date, x.kb)])
            out.append("%+.2f(%d)[%+.2f]" % (x[col].mean(), len(x), np.nanmean(x[col].values - bl)))
        return " / ".join(out)
    n = 0
    d1 = (E.i1 <= 0.3) & (E.i2 <= 0.3); u1 = (E.i1 >= -0.3) & (E.i2 >= -0.3)
    if MK == "kr": d1 &= E.nas <= 0.3; u1 &= E.nas >= -0.3
    for kind, cname, conds in (("up", "A 역행 강세(지수 보합·하락 & 종목 연속 상승)",
                                (("보합(말한 그대로)", d1), ("지수 -0.5%↓", (E.i1 <= -0.5) & (E.i2 <= -0.5)), ("지수 -1%↓", (E.i1 <= -1) & (E.i2 <= -1)), ("지수 조건 없음", E.i1 == E.i1))),
                               ("dn", "B 역행 약세(지수 보합·상승 & 종목 연속 하락)",
                                (("보합(말한 그대로)", u1), ("지수 +0.5%↑", (E.i1 >= 0.5) & (E.i2 >= 0.5)), ("지수 +1%↑", (E.i1 >= 1) & (E.i2 >= 1)), ("지수 조건 없음", E.i1 == E.i1)))):
        P("## " + cname); P("")
        P("| 봉 | 시작 | 지수 조건 | 30분 뒤 | 60분 뒤 | 종가 | 다음 날 시가 | 다음 날 종가 |"); P("|---|---|---|---|---|---|---|---|")
        for sn, _, _ in SPECS:
            for st, sm in (("개장부터", E.open_), ("아무 때나", E.open_ | ~E.open_)):
                for cn, cm in conds:
                    z = E[(E.kind == kind) & (E.spec == sn) & sm & cm]
                    P("| %s | %s | %s | %s |" % (sn, st, cn, " | ".join(cellx(z, c) for c in EXN))); n += 5
        P("")
        P("### 30분×2 · 개장부터 · 말한 그대로 지수 — 거래대금 위·아래 절반"); P("")
        P("| 대상 | 종가 | 다음 날 시가 | 다음 날 종가 |"); P("|---|---|---|---|")
        z = E[(E.kind == kind) & (E.spec == "30분×2") & E.open_ & (d1 if kind == "up" else u1)]
        med = z.val.median()
        for nm2, m in (("위 절반", z.val >= med), ("아래 절반", z.val < med)):
            P("| %s | %s |" % (nm2, " | ".join(cellx(z[m], c) for c in ("xc", "xno", "xnc")))); n += 3
        P("")
    P("(칸 %d)" % n)
    log_trials("bar30v_%s_1111" % MK, n)
    (ROOT / "reports" / ("bar30v_%s_1111.md" % MK)).write_text("\n".join(OUT) + "\n", encoding="utf-8")


if __name__ == "__main__":
    {"run": run, "rep": rep}[CMD]()
