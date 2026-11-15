# -*- coding: utf-8 -*-
"""시초가 매매 실측 — 장전 움직임으로 고르고 시가에 사서 10·30·60분 뒤(또는 종가) 판다 (2026-11-16 사용자 "어떤 기준으로 종목 선별하는 걸까 → 응 이어서").
흔히 쓰는 선별 기준 6가지를 그대로: ① 갭(시가 ÷ 어제 종가) 크기 ② 장전 거래대금 ③ (재료 — 자료 없음) ④ 전날 흐름(상한가·급등·고가 마감) ⑤ 호가 쏠림(녹화 25일뿐) ⑥ 전날 외국인·기관 순매수.
자료  A 전 종목 2022-12~ : 토스 1분봉 bf(시가·10/30/60분 뒤·종가) + flow11 — 갭은 **실제 시가**로 쟀다(실전은 08:59 예상가로 골라야 해서 조금 다르다)
      B NXT 종목 2025-03~: NXT 장전 1분봉(research/cache/bf_nxt_pre + C:/temp/kp/pm_parts·pm_parts2) — 08:50 까지 장전 등락·거래대금·막판 20분 흐름
      C 녹화 25일(10-12~): 장전 호가 균형가·쏠림(research/factory/auction.features)
매수 = KRX 시가(단일가) · 매도 = 10·30·60분 뒤 1분봉 종가 / 종가 · 비용 0.28(0.23 + 파는 쪽 미끄러짐 0.05)
대조 = 같은 날 유니버스(20일 평균 거래대금 3억↑·1천원↑) 전부 같은 매도 평균. 학습 22-12~24(B 는 2025) · 검증 25~(B 는 2026).
    python research/memguard.py research/openplay_1116.py run | rep
"""
import glob, math, os, sqlite3, sys, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path[:0] = [str(ROOT), str(ROOT / "factory")]
if sys.stdout is not None: sys.stdout.reconfigure(encoding="utf-8")
import m10_1116 as M
US = M.MK == "us"                              # MK=us 면 미장(장전·수급·호가 칸 없음)
OUTD = Path("C:/temp/kp/openplay" + ("_us" if US else "")); OUTD.mkdir(parents=True, exist_ok=True)
COST = M.COST
EX = ("x10", "x30", "x60", "xc")


def run():
    files = sorted(glob.glob(str(BASE / "data" / "m1" / M.MDIR / "bf" / "*.parquet")))
    rows = []
    for fi, f in enumerate(files):
        t = Path(f).stem
        if not US and not t.endswith("0"): continue
        try: days, O, Cf, V = M.load(f)
        except Exception: continue
        nD = len(days)
        if nD < 40: continue
        j = np.argmax(~np.isnan(O), axis=1); op = O[np.arange(nD), j]; bad = np.isnan(O).all(axis=1) | (j > 5); op[bad] = np.nan     # 09:06 넘어 첫 체결이면 뺀다
        cl = Cf[:, -1]; hi = np.nanmax(Cf, axis=1)
        dval = np.nansum(np.where(V > 0, Cf * V, 0), axis=1)
        a20 = pd.Series(dval).rolling(20, min_periods=10).mean().shift(1).values
        pc = np.r_[np.nan, cl[:-1]]; ppc = np.r_[np.nan, pc[:-1]]; phi = np.r_[np.nan, hi[:-1]]; pval = np.r_[np.nan, dval[:-1]]
        v1 = np.nansum(np.where(V[:, :2] > 0, Cf[:, :2] * V[:, :2], 0), axis=1)                 # 시가 단일가+첫 1분 거래대금(사후 — 참고용)
        E = pd.DataFrame({"t": t, "d": days, "op": op, "pc": pc, "a20": a20, "gap": (op / pc - 1) * 100, "pret": (pc / ppc - 1) * 100,
                          "pch": pc / phi, "pvr": pval / a20, "v1r": v1 / a20,
                          "x10": (Cf[:, 10] / op - 1) * 100 - COST, "x30": (Cf[:, 30] / op - 1) * 100 - COST,
                          "x60": (Cf[:, 60] / op - 1) * 100 - COST, "xc": (cl / op - 1) * 100 - COST})
        E = E[(E.a20 >= M.MINA) & (E.op >= M.MINP) & E.gap.notna() & (E.gap.abs() < (60 if US else 29.5))]
        rows.append(E)
        if fi % 400 == 0: print(fi, len(files), flush=True)
    A = pd.concat(rows, ignore_index=True)
    for x in EX: A[x] = A[x].where(A[x].abs() < 40).astype("float32")
    A.to_parquet(OUTD / "days.parquet", index=False)
    print("종목-일", len(A))
    if US: return
    # NXT 장전 요약
    fs = glob.glob(str(BASE / "research" / "cache" / "bf_nxt_pre" / "bars_*.parquet")) + glob.glob(r"C:\temp\kp\pm_parts\bars_*.parquet") + \
         glob.glob(r"C:\temp\kp\pm_parts2\bars_*.parquet") + glob.glob(r"C:\temp\kp\pm_m1_1103.parquet")
    parts = []
    for f in fs:
        try:
            B = pd.read_parquet(f, columns=["t", "d", "hm", "c", "v"]); B["hm"] = B.hm.astype(int); B["d"] = B.d.astype(str)
            parts.append(B[(B.hm >= 801) & (B.hm <= 850) & (B.v > 0)])
        except Exception as ex: print("못 읽음", f, repr(ex)[:80])
    B = pd.concat(parts, ignore_index=True).drop_duplicates(["t", "d", "hm"]).sort_values(["t", "d", "hm"])
    B["val"] = B.c * B.v
    g = B.groupby(["t", "d"])
    Pm = pd.DataFrame({"p850": g.c.last(), "pval": g.val.sum(), "nbar": g.size(), "hm_last": g.hm.last()})
    e = B[B.hm <= 830].groupby(["t", "d"]).c.last().rename("p830")
    Pm = Pm.join(e).reset_index()
    Pm.to_parquet(OUTD / "pre.parquet", index=False)
    print("장전 종목-일", len(Pm))


def st(Z, x):
    Z = Z.dropna(subset=[x])
    if len(Z) < 30: return None
    d = Z.groupby("d")[x].mean(); e = Z.assign(e=Z[x] - Z["m_" + x]).groupby("d").e.mean()
    t = lambda s: s.mean() / s.std(ddof=1) * math.sqrt(len(s)) if len(s) > 2 and s.std(ddof=1) > 0 else 0
    return dict(n=len(Z), days=len(d), mean=Z[x].mean(), win=(Z[x] > 0).mean() * 100, dm=d.mean(), t=t(d), ex=e.mean(), ext=t(e))


def rep():
    OUT = []; P = lambda s="": (OUT.append(s), print(s, flush=True))
    A = pd.read_parquet(OUTD / "days.parquet")
    mk = A.groupby("d")[list(EX)].mean().rename(columns={x: "m_" + x for x in EX}).reset_index()
    A = A.merge(mk, on="d", how="left")
    if US:
        for k_ in ("f1", "i1", "f5", "i5", "fstreak"): A[k_] = np.nan
    else:
        F = M.flows(); A = A.merge(F[["t", "d", "f1", "i1", "f5", "i5", "fstreak"]], on=["t", "d"], how="left")
    for k in ("f1", "i1", "f5", "i5"): A[k + "r"] = A[k] / A.a20 * 100
    A["f1rk"] = A.groupby("d").f1r.rank(ascending=False); A["gaprk"] = A.groupby("d").gap.rank(ascending=False)
    A["pvalrk"] = A.groupby("d").pvr.rank(ascending=False)
    P("A 전 종목 %d 종목-일 · %s~%s · 하루 %.0f종목 · 시장 평균 시가→10분 %+.2f · 30분 %+.2f · 60분 %+.2f · 종가 %+.2f (비용 뒤)\n" % (
        len(A), A.d.min(), A.d.max(), len(A) / A.d.nunique(), *[A.groupby("d")[x].mean().mean() for x in EX]))

    def table(title, D, sets, per):
        P("\n### %s\n" % title)
        P("| 고르는 기준 | 매도 | 학습 건·날 | 학습 건당 | 학습 날 바구니(t) | 학습 시장 대비(t) | 검증 건·날 | 검증 건당 | 검증 날 바구니(t) | 검증 시장 대비(t) |"); P("|---|---|---|---|---|---|---|---|---|---|")
        for nm, m in sets:
            Z = D[m(D)]
            for x in EX:
                r = [st(Z[(Z.d >= a) & (Z.d <= b)], x) for a, b in per]
                if not r[0] or not r[1]: continue
                c = lambda s: "%d·%d | %+.2f%% | %+.2f%% (%.1f) | %+.2f (%.1f)" % (s["n"], s["days"], s["mean"], s["dm"], s["t"], s["ex"], s["ext"])
                flag = " ★" if r[0]["dm"] > 0 and r[1]["dm"] > 0 and r[0]["t"] >= 2 and r[1]["t"] >= 2 else ""
                P("| %s%s | %s | %s | %s |" % (nm, flag, x, c(r[0]), c(r[1])))
    PA = (("20211201" if US else "20221201", "20241231"), ("20250101", "20991231"))
    BIG, MID = (1e8, 1e7) if US else (1e10, 2e9)
    table("A-1. 갭 크기(시가 ÷ 어제 종가)", A, [
        ("갭 +1~3%", lambda z: (z.gap >= 1) & (z.gap < 3)), ("갭 +3~6%", lambda z: (z.gap >= 3) & (z.gap < 6)), ("갭 +6~10%", lambda z: (z.gap >= 6) & (z.gap < 10)),
        ("갭 +10~15%", lambda z: (z.gap >= 10) & (z.gap < 15)), ("갭 +15%↑", lambda z: z.gap >= 15), ("그날 갭 상위 5종목", lambda z: (z.gaprk <= 5) & (z.gap >= 3)),
        ("갭 -3~-6% (거울)", lambda z: (z.gap <= -3) & (z.gap > -6)), ("갭 -6%↓ (거울)", lambda z: z.gap <= -6)], PA)
    table("A-2. 전날 흐름", A, [
        ("전날 상한가(+29%↑·미장은 +30%↑ 급등)", lambda z: z.pret >= 29), ("전날 상한가 · 오늘 갭 +3~15%", lambda z: (z.pret >= 29) & (z.gap >= 3) & (z.gap < 15)),
        ("전날 +10~29%", lambda z: (z.pret >= 10) & (z.pret < 29)), ("전날 +10%↑ · 고가 마감(종가 ≥ 고가 99%)", lambda z: (z.pret >= 10) & (z.pch >= 0.99)),
        ("전날 +10%↑ · 고가 마감 · 오늘 갭 +3~10%", lambda z: (z.pret >= 10) & (z.pch >= 0.99) & (z.gap >= 3) & (z.gap < 10)),
        ("전날 +10%↑ · 윗꼬리(종가 < 고가 95%)", lambda z: (z.pret >= 10) & (z.pch < 0.95)),
        ("전날 거래대금 20일 평균 5배↑ · 전날 +5%↑", lambda z: (z.pvr >= 5) & (z.pret >= 5)),
        ("전날 거래대금 5배↑ · 전날 +5%↑ · 오늘 갭 +3~10%", lambda z: (z.pvr >= 5) & (z.pret >= 5) & (z.gap >= 3) & (z.gap < 10)),
        ("전날 +5%↑ · 오늘 갭 하락(-1%↓)", lambda z: (z.pret >= 5) & (z.gap <= -1))], PA)
    table("A-3. 전날 수급(외국인·기관)", A, [
        ("전날 외국인 순매수 ÷ 거래대금 상위 10종목", lambda z: (z.f1rk <= 10) & (z.f1r > 0)), ("전날 외국인·기관 둘 다 순매수 · 갭 +1~6%", lambda z: (z.f1r > 0) & (z.i1r > 0) & (z.gap >= 1) & (z.gap < 6)),
        ("외국인 3일↑ 연속 순매수 · 갭 +1~6%", lambda z: (z.fstreak >= 3) & (z.gap >= 1) & (z.gap < 6)), ("외국인 5일 순매수 5%↑ · 갭 +3~10%", lambda z: (z.f5r >= 5) & (z.gap >= 3) & (z.gap < 10)),
        ("전날 외국인 대량 순매도(-5%↓) · 갭 상승 +3%↑", lambda z: (z.f1r <= -5) & (z.gap >= 3))], PA)
    table("A-4. 종목 크기 × 갭 +3~10%", A, [
        ("큰 종목(거래대금 100억↑·미장 1억달러↑)", lambda z: (z.a20 >= BIG) & (z.gap >= 3) & (z.gap < 10)), ("중간", lambda z: (z.a20 >= MID) & (z.a20 < BIG) & (z.gap >= 3) & (z.gap < 10)),
        ("작은(20억↓·미장 1천만달러↓)", lambda z: (z.a20 < MID) & (z.gap >= 3) & (z.gap < 10))], PA)
    if US:
        (ROOT / "openplay_1116_us.out").write_text(chr(10).join(OUT), encoding="utf-8"); return
    # ── B NXT 장전 ──
    Pm = pd.read_parquet(OUTD / "pre.parquet")
    Bz = A.merge(Pm, on=["t", "d"], how="inner")
    Bz = Bz[Bz.hm_last >= 840]
    Bz["pre"] = (Bz.p850 / Bz.pc - 1) * 100; Bz["pvr2"] = Bz.pval / Bz.a20 * 100; Bz["mom"] = (Bz.p850 / Bz.p830 - 1) * 100; Bz["og"] = (Bz.op / Bz.p850 - 1) * 100
    Bz["prerk"] = Bz.groupby("d").pre.rank(ascending=False); Bz["pvrk"] = Bz.groupby("d").pval.rank(ascending=False); Bz["pvr2rk"] = Bz.groupby("d").pvr2.rank(ascending=False)
    P("\nB NXT 장전 체결 있는 종목-일 %d · %s~%s · 하루 %.0f종목" % (len(Bz), Bz.d.min(), Bz.d.max(), len(Bz) / Bz.d.nunique()))
    PB = (("20250301", "20251231"), ("20260101", "20991231"))
    table("B. NXT 장전(08:00~08:50) 움직임으로 고르기 — 학습 2025 · 검증 2026", Bz, [
        ("장전 +2~5%", lambda z: (z.pre >= 2) & (z.pre < 5)), ("장전 +5~10%", lambda z: (z.pre >= 5) & (z.pre < 10)), ("장전 +10%↑", lambda z: z.pre >= 10),
        ("장전 등락 상위 5종목(+2%↑)", lambda z: (z.prerk <= 5) & (z.pre >= 2)), ("장전 거래대금 상위 10 · 장전 +2%↑", lambda z: (z.pvrk <= 10) & (z.pre >= 2)),
        ("장전 거래대금 ÷ 평소 하루 5%↑ · 장전 +2%↑", lambda z: (z.pvr2 >= 5) & (z.pre >= 2)), ("장전 거래대금 ÷ 평소 20%↑ · 장전 +2%↑", lambda z: (z.pvr2 >= 20) & (z.pre >= 2)),
        ("장전 +2%↑ · 막판 20분도 상승(+0.5%↑)", lambda z: (z.pre >= 2) & (z.mom >= 0.5)), ("장전 +2%↑ · 막판 20분 꺾임(-0.5%↓)", lambda z: (z.pre >= 2) & (z.mom <= -0.5)),
        ("장전 +2%↑ · KRX 시가가 장전가보다 낮게(-1%↓)", lambda z: (z.pre >= 2) & (z.og <= -1)), ("장전 +2%↑ · KRX 시가가 장전가보다 높게(+1%↑)", lambda z: (z.pre >= 2) & (z.og >= 1)),
        ("장전 +2%↑ · 전날 외국인 순매수", lambda z: (z.pre >= 2) & (z.f1r > 0)), ("장전 +2%↑ · 전날 +5%↑(이틀째 강세)", lambda z: (z.pre >= 2) & (z.pret >= 5)),
        ("장전 -2~-5% (거울)", lambda z: (z.pre <= -2) & (z.pre > -5)), ("장전 -5%↓ (거울)", lambda z: z.pre <= -5)], PB)
    # ── C 호가 녹화 ──
    try:
        import auction as AU
        rows = []
        for f in sorted(glob.glob(str(BASE / "data" / "factory" / "auction" / "KR_*_am.parquet"))):
            d = Path(f).name[3:11]; Fz = AU.features(d)
            if Fz is not None and len(Fz): rows.append(Fz[["ticker", "eq59", "imb59"]].assign(d=d).rename(columns={"ticker": "t"}))
        C_ = A.merge(pd.concat(rows), on=["t", "d"], how="inner")
        C_["eg"] = (C_.eq59 / C_.pc - 1) * 100
        P("\nC 장전 호가 녹화 %d일 · %d 종목-일 (기간이 짧아 학습·검증 대신 전체 한 칸 — 참고만)" % (C_.d.nunique(), len(C_)))
        P("\n| 고르는 기준(08:56 예상가) | 매도 | 건·날 | 건당 | 날 바구니(t) | 시장 대비(t) |"); P("|---|---|---|---|---|---|")
        for nm, m in (("예상 갭 +3~10%", lambda z: (z.eg >= 3) & (z.eg < 10)), ("예상 갭 +3~10% · 매수 쏠림", lambda z: (z.eg >= 3) & (z.eg < 10) & (z.imb59 > 0)),
                      ("예상 갭 +3~10% · 매도 쏠림", lambda z: (z.eg >= 3) & (z.eg < 10) & (z.imb59 < 0)), ("예상 갭 +10%↑", lambda z: z.eg >= 10),
                      ("예상 갭 +1%↑ · 쏠림 상위 20%", lambda z: (z.eg >= 1) & (z.imb59 >= C_.imb59.quantile(.8)))):
            Z = C_[m(C_)]
            for x in EX:
                s = st(Z, x)
                if s: P("| %s | %s | %d·%d | %+.2f%% | %+.2f%% (%.1f) | %+.2f (%.1f) |" % (nm, x, s["n"], s["days"], s["mean"], s["dm"], s["t"], s["ex"], s["ext"]))
    except Exception as ex:
        P("C 호가 녹화 부분 실패: %s" % repr(ex)[:200])
    (ROOT / "openplay_1116.out").write_text("\n".join(OUT), encoding="utf-8")


if __name__ == "__main__":
    {"run": run, "rep": rep}[sys.argv[1]]()
