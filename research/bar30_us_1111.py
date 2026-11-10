# -*- coding: utf-8 -*-
"""H0406·H0407 [미장판] 장중 30분봉 연속 상승/하락 × 지수 반대 방향 → 매수 → 종가 매도 또는 15분봉 깨지면 매도 (2026-11-11 사용자).

 A [역행 강세] 장 시작 후 지수(QQQ·SPY 개장 대비)는 보합이나 하락(≤ +0.3%)인데
   그 종목 30분봉이 개장부터 연속 N번(2·3) 올랐다 → 매수
 B [역행 약세] 지수(QQQ·SPY)는 보합이나 상승(≥ -0.3%)인데 그 종목 30분봉이 개장부터 연속 N번 내렸다 → 매수
 '오른 봉' = 30분봉 종가 > 그 앞 30분봉 종가(첫 봉은 > 그날 시가). 신호 = N번째 봉 끝(N=2 → 10:30 · N=3 → 11:00 (미 동부)).
 매수 = 신호 뒤 첫 체결(거래량>0) 1분봉 시가. 매도 ① 종가(그날 마지막 봉) ② 15분봉 종가가 직전 15분봉 저가 아래로 깨지면 다음 첫 체결 시가(안 깨지면 종가).
 비용 0.25(공장 US_COST) + 미끄러짐 0.05 = 0.30. 살 수 있는 종목만: 개장~신호 거래대금 $100만↑ · 주가 $5↑ · 매수가가 전날 종가 +50% 미만.
 대조(바닥선) = 같은 날·같은 매수 시각에 같은 거르개를 통과한 아무 종목. 학습 2021-12~2024 · 검증 2025~ · 날 바구니 t.
 지수 조건을 뺀 판(종목 모양만)도 같이 낸다 — 지수 조건이 하는 일을 보려고.
    python research/bar30_us_1111.py run    # → C:/temp/kp/bar30us/
    python research/bar30_us_1111.py rep    # → research/reports/bar30_us_1111.md
"""
import os, sys, glob, pickle, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
os.chdir(BASE); sys.path[:0] = [str(ROOT), str(BASE)]
if sys.stdout is not None: sys.stdout.reconfigure(encoding="utf-8")
OUTD = Path("C:/temp/kp/bar30us"); OUTD.mkdir(parents=True, exist_ok=True)
COST = 0.25 + 0.05
NMIN = 391                                   # 1분봉 끝 시각 09:31 … 16:00(390개) + 16:01(종가 경매) · 미 동부
IDX = ("QQQ", "SPY")                       # 나스닥100 · S&P500 ETF — 지수 대신
NS = (2, 3)
MINV = 1e6


def load(t):
    f = BASE / "data" / "m1" / "US" / "bf" / (t + ".parquet")
    B = pd.read_parquet(f, columns=["ts", "o", "h", "l", "c", "v"])
    k = pd.DatetimeIndex(pd.to_datetime(B.ts.values, unit="s", utc=True)).tz_convert("America/New_York")
    mi = (k.hour * 60 + k.minute).values - (9 * 60 + 31)      # 09:31 → 0(미 동부, 서머타임 자동)
    ok = (mi >= 0) & (mi < NMIN)
    B = B[ok]; day = k.strftime("%Y%m%d")[ok]; mi = mi[ok]
    days, di = np.unique(day, return_inverse=True)
    sh = (len(days), NMIN)
    O = np.full(sh, np.nan); H = np.full(sh, np.nan); L = np.full(sh, np.nan); C = np.full(sh, np.nan); V = np.zeros(sh)
    O[di, mi] = B.o.values; H[di, mi] = B.h.values; L[di, mi] = B.l.values; C[di, mi] = B.c.values; V[di, mi] = B.v.values
    traded = V > 0
    O[~traded] = np.nan; H[~traded] = np.nan; L[~traded] = np.nan
    Cf = pd.DataFrame(np.where(traded, C, np.nan)).ffill(axis=1).values          # 체결 있던 봉 종가로 앞으로 채움
    return days, O, H, L, Cf, V, C


def dopen(O):
    """그날 첫 체결 시가."""
    j = np.argmax(~np.isnan(O), axis=1); v = O[np.arange(len(O)), j]
    v[np.isnan(O).all(axis=1)] = np.nan
    return v


def idx_paths():
    P = {}
    for t in IDX:
        days, O, H, L, Cf, V, C = load(t)
        op = dopen(O)
        P[t] = {d: (Cf[i] / op[i] - 1) * 100 for i, d in enumerate(days)}
    return P


def nasdaq():
    import FinanceDataReader as fdr
    X = fdr.DataReader("IXIC", "2022-06-01"); X = X[X.Close > 0]
    r = X.Close.pct_change() * 100; r.index = r.index.strftime("%Y%m%d")
    return r


def run():
    IP = idx_paths()
    nas_prev = lambda d: 0.0                                          # 미장판은 지수 장중 값(QQQ·SPY)만 본다
    files = sorted(glob.glob(str(BASE / "data" / "m1" / "US" / "bf" / "*.parquet")))
    if os.environ.get("LIM"): files = files[:int(os.environ["LIM"])]
    ev, base = [], {}
    for fi, f in enumerate(files):
        t = Path(f).stem
        if t in IDX: continue
        try: days, O, H, L, Cf, V, C = load(t)
        except Exception: continue
        if len(days) < 30: continue
        op = dopen(O)
        last = Cf[:, -1]
        pc = np.r_[np.nan, last[:-1]]                                     # 전 거래일 종가(같은 파일 앞 날 — 거래정지 날은 건너뜀)
        c30 = Cf[:, 29::30][:, :13]                                       # 30분봉 끝(09:30 … 15:30) 종가
        prev30 = np.column_stack([op, c30[:, :-1]])
        up = c30 > prev30; dn = c30 < prev30
        L15 = np.column_stack([np.nanmin(L[:, j * 15:(j + 1) * 15], axis=1) for j in range(26)])
        C15 = Cf[:, 14::15][:, :26]
        val = np.nancumsum(np.where(V > 0, Cf * V, 0), axis=1)
        for N in NS:
            s = 30 * N                                                    # 신호 뒤 첫 분 인덱스
            sub = V[:, s:] > 0
            has = sub.any(axis=1); e = s + np.argmax(sub, axis=1)
            ent = O[np.arange(len(days)), np.minimum(e, NMIN - 1)]
            okb = has & (val[:, s - 1] >= MINV) & (ent >= 5) & (ent < pc * 1.5) & ~np.isnan(pc) & ~np.isnan(last)
            rc = (last / ent - 1) * 100 - COST
            for i in np.flatnonzero(okb):
                b = base.setdefault((days[i], N), [0.0, 0])
                b[0] += rc[i]; b[1] += 1
            upN = up[:, :N].all(axis=1); dnN = dn[:, :N].all(axis=1)
            for i in np.flatnonzero(okb & (upN | dnN)):
                d = days[i]
                k = 0 if upN[i] else 1
                # 15분봉 깨짐: 매수 분 e[i] 가 든 15분봉 다음 봉부터, 그 봉 종가 < 직전 15분봉 저가 → 다음 첫 체결 시가
                jb = e[i] // 15 + 1; xb = np.nan; xhm = None
                for j in range(max(jb, 1), 26):
                    if C15[i, j] < L15[i, j - 1]:
                        q = (j + 1) * 15
                        nx = np.flatnonzero(V[i, q:] > 0)
                        if len(nx):
                            xb = O[i, q + nx[0]]; xhm = q + nx[0]
                        break
                rb = ((xb / ent[i] - 1) * 100 - COST) if xb == xb else rc[i]
                ix = {nm: (IP[nm].get(d, np.full(NMIN, np.nan))[s - 1]) for nm in IDX}
                ev.append(dict(t=t, date=d, N=N, kind="up" if k == 0 else "dn", ent=ent[i], pc=pc[i], gap=(op[i] / pc[i] - 1) * 100, mv=(Cf[i, s - 1] / op[i] - 1) * 100,
                               val=val[i, s - 1], rc=rc[i], rb=rb, brk=xhm is not None, xmin=xhm, kp=ix["QQQ"], kq=ix["SPY"], nas=nas_prev(d)))
        if fi % 200 == 0: print(fi, len(files), len(ev), flush=True)
    pd.DataFrame(ev).to_pickle(OUTD / "ev.pkl")
    pickle.dump(base, open(OUTD / "base.pkl", "wb"))
    print("끝", len(ev))


OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))
PER = (("학습 21.12~24", "20211201", "20241231"), ("검증 25~", "20250101", "20991231"))


def cell(z, col, B):
    z = z.dropna(subset=[col])
    if len(z) < 30: return "%d건" % len(z)
    d = z.groupby("date")[col].mean()
    bl = pd.Series({k: B.get(k) for k in zip(z.date, z.N)}).dropna()
    ex = (z[col].values - np.array([B.get(k, np.nan) for k in zip(z.date, z.N)]))
    db = pd.Series(ex, index=z.date.values).groupby(level=0).mean()
    t = d.mean() / d.std() * np.sqrt(len(d)) if len(d) > 3 and d.std() > 0 else np.nan
    return "%d건 **%+.2f** (중앙 %+.2f·승 %.0f%%) · 날 %d개 %+.2f t%.1f · 대조 대비 %+.2f" % (len(z), z[col].mean(), z[col].median(), (z[col] > 0).mean() * 100, len(d), d.mean(), t, np.nanmean(db.values))


def rep():
    from verdict import log_trials
    E = pd.read_pickle(OUTD / "ev.pkl"); Bs = pickle.load(open(OUTD / "base.pkl", "rb"))
    B = {k: v[0] / v[1] for k, v in Bs.items() if v[1] >= 20}
    P("# [미장] 장중 30분봉 연속 상승·하락 × 지수 반대 방향 (H0406·H0407) · 2026-11-11"); P("")
    P("- 미장 1분봉 2021-12~2026-10 · %d종목 묶음 · 개장~신호 거래대금 $100만↑ · 비용 0.25 + 미끄러짐 0.05 · 사건 %d건" % (E.t.nunique(), len(E)))
    P("- 지수 = QQQ·SPY 개장 대비(신호 시각) · '보합' = ±0.3%")
    P("- 대조 = 같은 날·같은 매수 시각 아무 종목(같은 거르개). '대조 대비' = 같은 날 대조를 뺀 값의 날 평균"); P("")
    bl = pd.DataFrame([(k[0], k[1], v) for k, v in B.items()], columns=["date", "N", "r"])
    P("**바닥선(아무 종목, 종가 매도)**: " + " · ".join("%s N=%d %+.2f" % (nm, n, bl[(bl.N == n) & (bl.date >= a) & (bl.date <= b)].r.mean()) for nm, a, b in PER for n in NS)); P("")
    flatdn = (E.kp <= 0.3) & (E.kq <= 0.3) & (E.nas <= 0.3)
    flatup = (E.kp >= -0.3) & (E.kq >= -0.3) & (E.nas >= -0.3)
    n = 0
    for kind, nm, cond in (("up", "A 역행 강세 — 지수 보합·하락인데 종목 30분봉 연속 상승", flatdn), ("dn", "B 역행 약세 — 지수 보합·상승인데 종목 30분봉 연속 하락", flatup)):
        P("## " + nm); P("")
        P("| N | 조건 | 매도 | 학습 22.12~24 | 검증 25~ |"); P("|---|---|---|---|---|")
        for N in NS:
            for cn, m in (("지수 조건 O", cond), ("지수 조건 X(모양만)", cond | ~cond)):
                for col, cl in (("rc", "종가"), ("rb", "15분봉 깨지면")):
                    z = E[(E.kind == kind) & (E.N == N) & m]
                    P("| %d | %s | %s | %s |" % (N, cn, cl, " | ".join(cell(z[(z.date >= a) & (z.date <= b)], col, B) for _, a, b in PER))); n += 1
        P("")
        P("### 지수 조건 O · 종가 매도 — 신호까지 오른(내린) 폭별"); P("")
        P("| N | 개장→신호 | 학습 | 검증 |"); P("|---|---|---|---|")
        bins = ((0, 2), (2, 4), (4, 7), (7, 99)) if kind == "up" else ((-2, 0), (-4, -2), (-7, -4), (-99, -7))
        for N in NS:
            for a_, b_ in bins:
                z = E[(E.kind == kind) & (E.N == N) & cond & (E.mv > min(a_, b_)) & (E.mv <= max(a_, b_))]
                P("| %d | %s~%s%% | %s |" % (N, a_, b_, " | ".join(cell(z[(z.date >= a) & (z.date <= b)], "rc", B) for _, a, b in PER))); n += 1
        P("")
    P("(칸 %d)" % n)
    log_trials("bar30_us_1111", n)
    (ROOT / "reports" / "bar30_us_1111.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")


if __name__ == "__main__":
    {"run": run, "rep": rep}[sys.argv[1] if len(sys.argv) > 1 else "rep"]()
