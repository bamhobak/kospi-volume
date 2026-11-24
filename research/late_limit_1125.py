# -*- coding: utf-8 -*-
"""2026-11-25 [갭하락] 돈이 모자라 시가에 못 낸 주문을, [장후 낙폭]이 09:00 에 팔린 뒤 **지정가로** 다시 걸면.
사용자 "갭 하락을 나중에 사는 거 시장가 말고 원래 사려던 가격에 매수 시도하는 건 안 돼?"
  대상 = timing_day_1107.py 의 T1 시가 체결(시가 ≤ 지정가 — 돈만 있었으면 시가에 사졌을 건, 2022-12~). 종가 매도 · 비용 0.23.
  값 A = 시가(돈이 있었으면 사졌을 값) · 값 B = 원래 지정가(어제 종가 × (1 + 시장 갭 - 1.5%), 시가보다 같거나 높음)
  시작 = '첫 봉부터'(09:00 직후 — 첫 봉 안에서 시가 아래로 거래됐으면 체결, 낙관) · '09:01부터'(둘째 봉부터, 보수)
  체결 = '뚫림'(저가 < 값 — 줄 맨 뒤라 값이 아래로 지나가야 사짐) · '닿음'(저가 ≤ 값, 낙관). 걸 때 이미 값 아래면 그때 값에 삼(둘째 봉 시가).
    python research/memguard.py research/late_limit_1125.py build → python research/memguard.py research/late_limit_1125.py"""
import glob, sys, time
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path[:0] = [str(ROOT), str(BASE)]
sys.stdout.reconfigure(encoding="utf-8")
COST = 0.23
CUTS = [902, 903, 905, 910, 930, 1000, 1200, 1430]
OLD = ROOT / "cache" / "timing1107_t1_day.parquet"; CACHE = ROOT / "cache" / "late_limit_1125.parquet"


def base():
    A = pd.read_parquet(OLD)
    A["pc"] = A.o / (1 + A.gap / 100); A["mg"] = A.gap - A.rgap; A["lim"] = A.pc * (1 + (A.mg - 1.5) / 100)
    return A[A.o <= A.lim].copy()


def build():
    t0 = time.time(); T = base()
    need = T.groupby("ticker").date.apply(set).to_dict()
    M1 = BASE / "data" / "m1" / "KR"; D = []
    for f in sorted(glob.glob(str(M1 / "day" / "*.parquet"))):
        x = pd.read_parquet(f); D.append(x[x.t.isin(need)])
    D = pd.concat(D, ignore_index=True); DG = {k: g for k, g in D.groupby("t")}; rows = []
    for i, (t, ds) in enumerate(sorted(need.items())):
        f = M1 / "bf" / ("%s.parquet" % t)
        parts = [pd.read_parquet(f)] if f.exists() else []
        if t in DG: parts.append(DG[t])
        parts = [p for p in parts if len(p)]
        if not parts: continue
        x = pd.concat(parts, ignore_index=True).drop_duplicates("ts")
        k = pd.to_datetime(x.ts.values, unit="s", utc=True).tz_convert("Asia/Seoul")
        x = x.assign(d=pd.Index(k.year * 10000 + k.month * 100 + k.day).astype(str).values, hm=(k.hour * 100 + k.minute).values)
        x = x[(x.hm >= 901) & (x.hm <= 1531) & x.d.isin(ds)].sort_values("ts")
        for d, g in x.groupby("d"):
            if len(g) < 30: continue
            hm = g.hm.values; lo = g.l.values
            R = {"ticker": t, "date": d, "hm1": int(hm[0]), "l1": float(lo[0]), "c1": float(g.c.values[0])}
            k2 = np.arange(len(g)) >= 1                         # 둘째 봉부터(첫 봉 = 시가 단일가 + 첫 1분)
            R["o2"] = float(g.o.values[1]); R["hm2"] = int(hm[1])
            for u in CUTS:
                kk = k2 & (hm <= u); R["N%d" % u] = float(lo[kk].min()) if kk.any() else np.nan
            rows.append(R)
        if i % 300 == 0: print(f"{i}/{len(need)} {time.time() - t0:.0f}s", flush=True)
    pd.DataFrame(rows).to_parquet(CACHE)
    print(f"완료 {len(rows):,}행 · {(time.time() - t0) / 60:.1f}분")


OUT = []
def P(s=""): print(s, flush=True); OUT.append(str(s))
rng = np.random.default_rng(7)
def ci(v, ym):
    v = pd.Series(np.asarray(v, float)); g = v.groupby(np.asarray(ym)).agg(["sum", "count"])
    s, c = g["sum"].values, g["count"].values; k = rng.integers(0, len(g), (2000, len(g)))
    bs = s[k].sum(1) / c[k].sum(1); return np.percentile(bs, 2.5), np.percentile(bs, 97.5)
hh = lambda u: "%d:%02d" % (u // 100, u % 100)


def analyze():
    T = base().merge(pd.read_parquet(CACHE), on=["ticker", "date"])
    T["ym"] = T.date.str[:6]; T["y"] = T.date.str[:4]
    T["ret"] = (T.c / T.o - 1) * 100 - COST
    n = len(T); nd = T.date.nunique()
    P("# [갭하락] 돈 모자라 못 낸 주문 — 개장 뒤 지정가로 다시 걸면 (2026-11-25)\n")
    P(f"- 대상: 시가 ≤ 지정가라 돈만 있었으면 시가에 사졌을 {n:,}건 · {T.date.min()}~{T.date.max()} · {nd}일 · 종가 매도 · 비용 {COST}%")
    P(f"- 기준(시가에 샀다면) 건당 {T.ret.mean():+.2f}% · 이긴 비율 {(T.ret > 0).mean() * 100:.0f}% · 참고 09:01 시장가(첫 봉 종가) {((T.c / T.c1 - 1) * 100 - COST).mean():+.2f}% · 둘째 봉 시가에 시장가 {((T.c / T.o2 - 1) * 100 - COST).mean():+.2f}%")
    P(f"- 시가 뒤 흐름: 첫 봉 안에서 시가 아래로 거래 {(T.l1 < T.o).mean() * 100:.0f}% · 둘째 봉 시가가 시가보다 높음 {(T.o2 > T.o).mean() * 100:.0f}% · 같음 {(T.o2 == T.o).mean() * 100:.0f}% · 낮음 {(T.o2 < T.o).mean() * 100:.0f}% · 둘째 봉 시가 ÷ 시가 평균 {((T.o2 / T.o - 1) * 100).mean():+.2f}%")
    cells = 0

    def fill(px, start, kind, u):
        """돌려줌: (체결 여부, 산 값). start 'first' = 첫 봉부터(낙관 — 걸자마자 값은 못 봄, 값이 지나가야 체결) · 'second' = 둘째 봉 시가에 걸기"""
        N = T["N%d" % u].values; p = px.values
        if start == "second":
            now = T.o2.values <= p                                   # 걸 때 이미 값 아래(또는 같음) → 그때 값에 바로 삼
            later = (N < p) if kind == "뚫림" else (N <= p)
            f = now | later; buy = np.where(now, T.o2.values, p)
        else:
            lo = np.fmin(T.l1.values, N)
            f = (lo < p) if kind == "뚫림" else (lo <= p)
            buy = p.copy()
        return f, buy

    def table(title, px, start):
        nonlocal cells
        P("\n## " + title + "\n")
        P("| 체결 기준 | 언제까지 걸어 둠 | 사진 비율 | 사진 건 건당 | 이긴 비율 | 사진 건 95% 구간 | 주문 100건당 손익 합(%p) | 시가에 샀다면 100건당 | 안 사진 건이 시가였다면 | 플러스인 해 |")
        P("|---|---|---|---|---|---|---|---|---|---|")
        for kind in ("뚫림", "닿음"):
            for u in CUTS:
                f, buy = fill(px, start, kind, u); cells += 1
                r = pd.Series((T.c.values / buy - 1) * 100 - COST, index=T.index)
                rf = r[f]; lo, hi = ci(rf.values, T.ym[f].values)
                yr = (r.where(f, 0.0)).groupby(T.y).sum()
                P(f"| {kind} | {hh(u)} | {f.mean() * 100:.0f}% | {rf.mean():+.2f}% | {(rf > 0).mean() * 100:.0f}% | {lo:+.2f}~{hi:+.2f} | {rf.sum() / n * 100:+.1f} | {T.ret.mean() * 100:+.1f} | {T.ret[~f].mean():+.2f}% ({(~f).sum()}건) | {(yr > 0).sum()}/{len(yr)} |")

    table("1) 시가 값에 지정가 — 09:00 직후부터(첫 봉 포함, 낙관)", T.o, "first")
    table("2) 시가 값에 지정가 — 09:01 부터(둘째 봉, 보수)", T.o, "second")
    table("3) 원래 지정가에 지정가 — 09:00 직후부터(첫 봉 포함, 낙관)", T.lim, "first")
    table("4) 원래 지정가에 지정가 — 09:01 부터(둘째 봉, 보수 · 걸 때 값이 지정가 아래면 그 값에 바로 삼)", T.lim, "second")

    P("\n## 5) 깊이별 — 시가 값 지정가 · 09:01 부터 · 뚫림 · 10:00 까지\n")
    P("| 시장 대비 갭 | 건 | 시가에 샀다면 건당 | 사진 비율 | 사진 건 건당 | 주문 100건당 손익 합 | 안 사진 건이 시가였다면 |"); P("|---|---|---|---|---|---|---|")
    f, buy = fill(T.o, "second", "뚫림", 1000); r = pd.Series((T.c.values / buy - 1) * 100 - COST, index=T.index)
    for lab, k in (("-1.5 ~ -3%p", T.rgap > -3), ("-3 ~ -5%p", (T.rgap <= -3) & (T.rgap > -5)), ("-5 ~ -10%p", (T.rgap <= -5) & (T.rgap > -10)), ("-10%p↓ (자료 의심)", T.rgap <= -10)):
        k = k.values; fk = f & k
        P(f"| {lab} | {k.sum():,} | {T.ret[k].mean():+.2f}% | {fk.sum() / k.sum() * 100:.0f}% | {r[fk].mean():+.2f}% | {r[fk].sum() / k.sum() * 100:+.1f} | {T.ret[k & ~f].mean():+.2f}% |")

    P("\n## 6) 해마다 — 주문 100건당 손익 합(%p)\n")
    P("| 해 | 건 | 시가에 샀다면 | 시가 값·09:01부터·뚫림·10:00 | 시가 값·첫 봉부터·뚫림·10:00 | 지정가·09:01부터·뚫림·09:05 | 09:01 시장가 |"); P("|---|---|---|---|---|---|---|")
    S = {}
    for nm, (px, st, u) in {"a": (T.o, "second", 1000), "b": (T.o, "first", 1000), "c": (T.lim, "second", 905)}.items():
        f, buy = fill(px, st, "뚫림", u); S[nm] = pd.Series(np.where(f, (T.c.values / buy - 1) * 100 - COST, 0.0), index=T.index)
    mk = (T.c / T.c1 - 1) * 100 - COST
    for y, g in T.groupby("y"):
        i = g.index
        P(f"| {y} | {len(g)} | {g.ret.mean() * 100:+.1f} | {S['a'][i].mean() * 100:+.1f} | {S['b'][i].mean() * 100:+.1f} | {S['c'][i].mean() * 100:+.1f} | {mk[i].mean() * 100:+.1f} |")
    P("\n## 7) -10%p↓ 64건을 빼고(종가÷시가가 딱 0.70 인 줄이 여럿 — 시가 값이 의심스러움) — 주문 100건당 손익 합(%p)\n")
    K = (T.rgap > -10).values
    P("| 건 | 시가에 샀다면 | 시가 값·09:01부터·뚫림·10:00 | 시가 값·첫 봉부터·뚫림·10:00 | 지정가·09:01부터·뚫림·09:05 | 09:01 시장가 |"); P("|---|---|---|---|---|---|")
    P(f"| {K.sum():,} | {T.ret[K].mean() * 100:+.1f} | {S['a'][K].mean() * 100:+.1f} | {S['b'][K].mean() * 100:+.1f} | {S['c'][K].mean() * 100:+.1f} | {mk[K].mean() * 100:+.1f} |")
    P("\n- 1)의 '닿음'은 시가 체결 자체가 '닿음'이라 기준과 같은 값(뜻 없음) · 3)은 걸자마자 지정가에 사진다고 본 것(실제론 그때 호가에 사짐)이라 참고만 — 볼 것은 1)의 뚫림·2)·4)")
    P("\n시험 칸 %d" % cells)
    (ROOT / "reports" / "late_limit_1125.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
    if "--nolog" not in sys.argv:
        try:
            from verdict import log_trials
            log_trials("late_limit_1125", cells)
        except Exception as ex: print("칸 수 기록 실패:", repr(ex)[:200])


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "build": build()
    else: analyze()
