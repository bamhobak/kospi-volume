# -*- coding: utf-8 -*-
"""H0414 쌍둥이 시장 이식 (2026-11-12 사용자 "기억 rulefind-1112 3번") — 일본 PTS·미국 장후·대만/중국 가격제한폭 문헌 효과를 국장 자료로.

겹쳐서 뺀 것: 상한가 잠김(H0233·H0288·H0304 — 종가에 못 삼) · 장후 공시(H0396 보류) · 갭×주목도([갭하락]·[장전 되돌림] 계열).
 A. 장후 시간대별 되돌림(Eaton·Shkilko·Werner 2025: 늦은 밤 변화일수록 되돌림 −10%→−50%) + 장후 거래량 터짐(Walkup 2009: 평소 거래면 되돌림, +2σ 터지면 지속)
    장후 구간 s1 15:40~16:00 · s2 16:00~18:00 · s3 18:00~19:50 (시장 평균 뺀 값) → 19:50 가격 매수 → 다음 날 시가 / 종가
 B. KRX 종가 단일가 쏠림(15:19→종가, Bogousslavsky·Muravyev 2023) → NXT 장후 초반(15:40 첫 가격 매수 → 16:10 / 다음 날 시가)
 C. 하한가 잠김 마감(종가 = 저가 & 한도 근처, Chen 외 2019 중국: 다음 날 시가 −1.13 → 2~3일 지속 → 6~60일 반등) → 다음 날 시가→종가 · 3일차 종가 매수 → 10·20일
    대조: 한도 근처까지 빠졌지만 저가 마감 아님 / 한도의 80~90%
 D. 자석 효과(대만·한국 Du 외 2009): 장중 처음 +24/+27%(한도 80·90%) · VI 근처 +9% 닿은 뒤 1분봉 다음 봉 시가 매수 → 종가 / 다음 날 시가, 한도(+29.5%) 닿을 확률. 아래쪽도
 표본: A·B 2025-03~ (KRX 애프터마켓 2026-09-14 시작 전후로 나눔) · C 2009~ (2015-06-15 전 한도 15%) · D 1분봉 2022-12~. 비용 0.23.
    python research/twin_1112.py ab | c | d    → C:/temp/kp/twin/*.pkl · 끝에 rep
    python research/twin_1112.py rep          → research/reports/twin_1112.md
"""
import os, sys, glob, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
os.chdir(BASE); sys.path[:0] = [str(ROOT), str(ROOT / "factory"), str(BASE)]
if sys.stdout is not None: sys.stdout.reconfigure(encoding="utf-8")
CMD = sys.argv[1] if len(sys.argv) > 1 else "rep"
OUTD = Path("C:/temp/kp/twin"); OUTD.mkdir(parents=True, exist_ok=True)
COST = 0.23
SPLIT = "20260914"


def m1load(f, start="20221201"):
    B = pd.read_parquet(f, columns=["ts", "o", "h", "l", "c", "v"])
    k = pd.to_datetime(B.ts.values + 9 * 3600, unit="s")
    B["d"] = k.strftime("%Y%m%d"); B["hm"] = k.hour * 100 + k.minute
    B = B[(B.d >= start) & (B.hm >= 901) & (B.hm <= 1530)]
    return B


def build_ab():
    A = pd.read_parquet(ROOT / "cache" / "ah_m1.parquet")
    A["hm"] = A.hm.astype(int); A = A[(A.hm >= 1541) & (A.hm <= 2000) & (A.v > 0)]
    D = pd.read_parquet(ROOT / "cache" / "m1_daysum.parquet")[["t", "d", "o", "c"]]
    D = D.sort_values(["t", "d"]); D["o1"] = D.groupby("t").o.shift(-1); D["c1"] = D.groupby("t").c.shift(-1)
    last = lambda z, hi: z[z.hm <= hi].groupby(["t", "d"]).c.last()
    P = pd.concat({"p1600": last(A, 1600), "p1800": last(A, 1800), "p1950": last(A, 1950), "p1610": last(A, 1610),
                   "p1540": A[A.hm <= 1545].groupby(["t", "d"]).c.first()}, axis=1)
    V = pd.concat({"v1": A[A.hm <= 1600].groupby(["t", "d"]).v.sum(), "v2": A[(A.hm > 1600) & (A.hm <= 1800)].groupby(["t", "d"]).v.sum(),
                   "v3": A[(A.hm > 1800) & (A.hm <= 1950)].groupby(["t", "d"]).v.sum(), "vall": A.groupby(["t", "d"]).v.sum(),
                   "a10": (A[A.hm >= 1951].c * A[A.hm >= 1951].v).groupby([A[A.hm >= 1951].t, A[A.hm >= 1951].d]).sum()}, axis=1)
    X = D.merge(P.reset_index(), on=["t", "d"]).merge(V.reset_index(), on=["t", "d"], how="left")
    X = X.sort_values(["t", "d"])
    X["vz"] = (X.vall - X.groupby("t").vall.transform(lambda s: s.shift(1).rolling(20, min_periods=10).mean())) / X.groupby("t").vall.transform(lambda s: s.shift(1).rolling(20, min_periods=10).std())
    # 종가 단일가 쏠림: 1분봉에서 15:19 마지막 가격
    sel = set(X.t.unique()); rows = []
    for f in glob.glob(str(BASE / "data" / "m1" / "KR" / "bf" / "*.parquet")):
        t = Path(f).stem
        if t not in sel: continue
        try: B = m1load(f, "20250301")
        except Exception: continue
        B = B[B.v > 0]
        p19 = B[B.hm <= 1519].groupby("d").c.last()
        rows.append(pd.DataFrame({"t": t, "d": p19.index, "p1519": p19.values}))
    X = X.merge(pd.concat(rows), on=["t", "d"], how="left")
    X.to_pickle(OUTD / "ab.pkl"); print("ab", len(X), flush=True)


def build_c():
    import common as C
    P = pd.read_pickle(C.CACHE / "factory_px.pkl")
    P = P[P.date >= "20090101"].sort_values(["ticker", "date"])
    g = P.groupby("ticker")
    P["pc"] = g.close.shift(1)
    P["ret"] = (P.close / P.pc - 1) * 100
    for k in (1, 2, 3, 5, 10, 20, 60): P["c%d" % k] = g.close.shift(-k)
    P["o1"] = g.open.shift(-1)
    P["lim"] = np.where(P.date < "20150615", 15.0, 30.0)
    P = P[(P.pc >= 1000) & (P.ret > -P.lim - 1) & (P.ret <= -0.5 * P.lim)]
    P.to_pickle(OUTD / "c.pkl"); print("c", len(P), flush=True)


def build_d():
    rows = []
    files = sorted(glob.glob(str(BASE / "data" / "m1" / "KR" / "bf" / "*.parquet")))
    for i, f in enumerate(files):
        t = Path(f).stem
        try: B = m1load(f)
        except Exception: continue
        B = B[B.v > 0]
        if not len(B): continue
        dc = B.groupby("d").c.last(); pc = dc.shift(1)
        do = B.groupby("d").o.first(); no = do.shift(-1)
        B = B.merge(pd.DataFrame({"pc": pc, "dc": dc, "no": no}), left_on="d", right_index=True)
        B = B[B.pc.notna()]
        B["hp"] = (B.h / B.pc - 1) * 100; B["lp"] = (B.l / B.pc - 1) * 100
        B = B.reset_index(drop=True); B["i"] = B.groupby("d").cumcount()
        day = B.groupby("d").agg(dc=("dc", "first"), no=("no", "first"), pc=("pc", "first"))
        day["val"] = (B.c * B.v).groupby(B.d).sum()
        oi = B.set_index(["d", "i"]).o; hmi = B.set_index(["d", "i"]).hm
        firsts = {}
        for key, m in (("u29", B.hp >= 29.5), ("d29", B.lp <= -29.5), ("u10", B.hp >= 10), ("d10", B.lp <= -10)):
            firsts[key] = B[m].groupby("d").i.min()
        for lvl in (9, 24, 27, -9, -24, -27):
            m = (B.hp >= lvl) if lvl > 0 else (B.lp <= lvl)
            first = B[m].groupby("d").i.min()
            first = first[first > 0]                       # 시가부터 넘어 열린 날은 '다가가며 닿음'이 아님
            if not len(first): continue
            E = pd.DataFrame({"d": first.index, "i0": first.values})
            E["en"] = oi.reindex(list(zip(E.d, E.i0 + 1))).values
            E["hm"] = hmi.reindex(list(zip(E.d, E.i0))).values
            E = E.dropna(subset=["en"])
            fl = firsts["u29" if lvl > 0 else "d29"].reindex(E.d).values; fv = firsts["u10" if lvl > 0 else "d10"].reindex(E.d).values
            dl, dv = fl - E.i0.values, fv - E.i0.values
            E["hit10"] = (dl > 0) & (dl <= 10); E["hit30"] = (dl > 0) & (dl <= 30); E["hitall"] = dl > 0
            E["vi5"] = (dv > 0) & (dv <= 5); E["vi30"] = (dv > 0) & (dv <= 30)
            E = E.join(day, on="d"); E["t"] = t; E["lvl"] = lvl
            rows.extend(E.drop(columns=["i0"]).to_dict("records"))
        if i % 300 == 0: print(i, len(files), len(rows), flush=True)
    pd.DataFrame(rows).to_pickle(OUTD / "d.pkl"); print("d", len(rows), flush=True)


def cell(z, col, dcol="d"):
    z = z.dropna(subset=[col])
    if len(z) < 10: return "%d건" % len(z)
    dd = z.groupby(dcol)[col].mean()
    t = dd.mean() / dd.std() * np.sqrt(len(dd)) if len(dd) > 3 and dd.std() > 0 else float("nan")
    return "%d건 중앙 %+.2f · 날 %d **%+.2f** t%.1f" % (len(z), z[col].median(), len(dd), dd.mean(), t)


def rep():
    from verdict import log_trials
    OUT = []; P = lambda s="": (OUT.append(s), print(s, flush=True)); n = 0
    P("# 쌍둥이 시장 이식 — 장후 시간대·거래량 터짐 · 종가 쏠림 · 하한가 잠김 · 자석 (H0414) · 2026-11-12"); P("")
    P("- 칸 = 건수 · 중앙 · 날 바구니 **평균** t · 비용 0.23 뒤. 장후 자료 2025-03~2026-10, 2026-09-14 KRX 애프터마켓 시작 전/후 나눔"); P("")
    # ── A ──
    X = pd.read_pickle(OUTD / "ab.pkl")
    X["p1600"] = X.p1600.fillna(X.c); X["p1800"] = X.p1800.fillna(X.p1600)          # 그 구간 거래 없으면 직전 가격 그대로
    X = X[(X.c > 0) & X.p1950.notna() & X.o1.notna()]
    X["s1"] = (X.p1600 / X.c - 1) * 100; X["s2"] = (X.p1800 / X.p1600 - 1) * 100; X["s3"] = (X.p1950 / X.p1800 - 1) * 100
    X["ah"] = (X.p1950 / X.c - 1) * 100
    for s in ("s1", "s2", "s3", "ah"): X["r" + s] = X[s] - X.groupby("d")[s].transform("mean")
    X["ro"] = (X.o1 / X.p1950 - 1) * 100 - COST; X["rc"] = (X.c1 / X.p1950 - 1) * 100 - COST
    X = X[(X.ah.abs() < 29) & (X.a10.fillna(0) >= 1e7)]
    PER = (("전 25-03~26-09-11", lambda z: z[z.d < SPLIT]), ("후 26-09-14~", lambda z: z[z.d >= SPLIT]))
    P("## A. 장후 구간별 움직임 → 19:50 가격 매수 → 다음 날 시가 / 종가 (시장 평균 뺀 장후 움직임, 장후 마지막 10분 거래대금 1천만↑)"); P("")
    P("| 무리 | 매도 | " + " | ".join(p for p, _ in PER) + " |"); P("|---|---|---|---|")
    G = [("말한 판: 장후 전체 -2%↓(시간대 무관)", X.rah <= -2),
         ("늦은 밤만 빠짐: s3(18~19:50) -2%↓ · s1·s2 ±1 안", (X.rs3 <= -2) & (X.rs1.abs() <= 1) & (X.rs2.abs() <= 1)),
         ("이른 장후만 빠짐: s1(15:40~16) -2%↓ · s3 ±1 안", (X.rs1 <= -2) & (X.rs3.abs() <= 1)),
         ("중간만 빠짐: s2(16~18) -2%↓ · s3 ±1 안", (X.rs2 <= -2) & (X.rs3.abs() <= 1)),
         ("장후 -2%↓ · 거래량 평소(z<2)", (X.rah <= -2) & (X.vz < 2)), ("장후 -2%↓ · 거래량 터짐(z≥2)", (X.rah <= -2) & (X.vz >= 2)),
         ("장후 +2%↑(오름, 참고) · 평소", (X.rah >= 2) & (X.vz < 2)), ("장후 +2%↑ · 터짐", (X.rah >= 2) & (X.vz >= 2)),
         ("대조: 장후 ±0.5 안", X.rah.abs() <= 0.5)]
    for nm, m in G:
        for col, lab in (("ro", "다음 날 시가"), ("rc", "다음 날 종가")):
            P("| %s | %s | %s |" % (nm, lab, " | ".join(cell(f(X[m]), col) for _, f in PER))); n += 2
    P("")
    P("되돌림 기울기(다음 날 시가까지 수익 ~ 구간 움직임, 시장 뺀 값, 전 구간): " + " · ".join(
        "%s %.2f" % (s, np.polyfit(X.dropna(subset=["r" + s, "ro"])["r" + s].clip(-15, 15), X.dropna(subset=["r" + s, "ro"]).ro.clip(-20, 20), 1)[0]) for s in ("s1", "s2", "s3")))
    P("")
    # ── B ──
    Y = X.dropna(subset=["p1519", "p1540", "p1610"]).copy()
    Y["auc"] = (Y.c / Y.p1519 - 1) * 100; Y["rauc"] = Y.auc - Y.groupby("d").auc.transform("mean")
    Y["b1"] = (Y.p1610 / Y.p1540 - 1) * 100 - COST; Y["b2"] = (Y.o1 / Y.p1540 - 1) * 100 - COST
    Y["b0"] = (Y.p1540 / Y.c - 1) * 100
    P("## B. KRX 종가 단일가 쏠림(15:19→종가, 시장 뺀 값) → NXT 15:40 첫 가격 매수"); P("")
    P("| 쏠림 | 매도 | " + " | ".join(p for p, _ in PER) + " |"); P("|---|---|---|---|")
    for nm, m in (("말한 판: -1%↓", Y.rauc <= -1), ("-2%↓", Y.rauc <= -2), ("+1%↑(참고)", Y.rauc >= 1), ("+2%↑(참고)", Y.rauc >= 2), ("대조 ±0.3", Y.rauc.abs() <= 0.3)):
        for col, lab in (("b1", "16:10"), ("b2", "다음 날 시가")):
            P("| %s | %s | %s |" % (nm, lab, " | ".join(cell(f(Y[m]), col) for _, f in PER))); n += 2
    P("")
    P("참고 — 15:40 첫 가격이 KRX 종가에서 이미 얼마나 되돌았나(쏠림 -1%%↓): 중앙 %+.2f%% · 15:40~15:45 가격 있는 건 %d" % (Y[Y.rauc <= -1].b0.median(), len(Y))); P("")
    # ── C ──
    Z = pd.read_pickle(OUTD / "c.pkl")
    Z["near"] = Z.ret <= -Z.lim + 0.6
    Z["lock"] = Z.near & (Z.close <= Z.low * 1.0005)
    for k in (1, 3, 5, 10, 20, 60): Z["f%d" % k] = (Z["c%d" % k] / Z.close - 1) * 100 - COST
    Z["oc1"] = (Z.c1 / Z.o1 - 1) * 100 - COST; Z["g1"] = (Z.o1 / Z.close - 1) * 100
    Z["d3_10"] = (Z.c10 / Z.c3 - 1) * 100 - COST; Z["d3_20"] = (Z.c20 / Z.c3 - 1) * 100 - COST
    PC = (("옛날 09~15(한도 15%)", lambda z: z[z.date < "20160101"]), ("학습 16~22", lambda z: z[(z.date >= "20160101") & (z.date < "20230101")]), ("검증 23~", lambda z: z[z.date >= "20230101"]))
    P("## C. 하한가 마감 다음 날들 (일봉 · 종가 매수 기준은 참고 — 잠긴 종가엔 팔자 잔량 쪽이라 살 수 있음)"); P("")
    P("| 무리 | 잼 | " + " | ".join(p for p, _ in PC) + " |"); P("|---|---|---|---|---|")
    for nm, m in (("말한 판: 하한가 잠김(한도 근처 & 저가 마감)", Z.lock), ("한도 근처인데 저가 마감 아님", Z.near & ~Z.lock),
                  ("한도의 80~90%(대조)", (Z.ret <= -0.8 * Z.lim) & (Z.ret > -0.9 * Z.lim))):
        z = Z[m]
        for col, lab in (("g1", "다음 날 갭(비용 전)"), ("oc1", "다음 날 시가→종가"), ("f3", "종가→3일"), ("d3_10", "3일차 종가→10일"), ("d3_20", "3일차 종가→20일"), ("f60", "종가→60일")):
            P("| %s | %s | %s |" % (nm, lab, " | ".join(cell(f(z), col, "date") for _, f in PC))); n += 3
    P("")
    # ── D ──
    if not (OUTD / "d.pkl").exists():
        P("(D 자석 효과는 아직 스캔 중)"); P("(칸 %d)" % n)
        (ROOT / "reports" / "twin_1112.md").write_text(chr(10).join(OUT) + chr(10), encoding="utf-8"); return
    W = pd.read_pickle(OUTD / "d.pkl")
    W["rc"] = (W.dc / W.en - 1) * 100 * np.sign(1) - COST; W["rn"] = (W.no / W.en - 1) * 100 - COST
    W = W[(W.pc >= 1000) & (W.val >= 1e9)]
    PD = (("학습 22.12~24", lambda z: z[z.d < "20250101"]), ("검증 25~", lambda z: z[z.d >= "20250101"]))
    P("## D. 자석 효과 — 장중 처음 닿은 다음 1분봉 시가 매수 (그날 거래대금 10억↑)"); P("")
    P("| 처음 닿은 선 | 건수 | 30분 안 한도(±29.5) | 장 끝까지 한도 | 5분 안 VI선(±10) | 종가 매도 학습 | 종가 매도 검증 | 다음 날 시가 학습 | 다음 날 시가 검증 |"); P("|---|---|---|---|---|---|---|---|---|")
    for lvl in (9, 24, 27, -9, -24, -27):
        z = W[W.lvl == lvl]
        if not len(z): continue
        P("| %+d%% | %d | %.0f%% | %.0f%% | %s | %s | %s | %s | %s |" % (lvl, len(z), z.hit30.mean() * 100, z.hitall.mean() * 100, ("%.0f%%" % (z.vi5.mean() * 100)) if abs(lvl) == 9 else "-",
            cell(PD[0][1](z), "rc"), cell(PD[1][1](z), "rc"), cell(PD[0][1](z), "rn"), cell(PD[1][1](z), "rn"))); n += 4
    P("")
    P("(칸 %d)" % n)
    (ROOT / "reports" / "twin_1112.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
    log_trials("twin_1112", n)


if __name__ == "__main__":
    {"ab": build_ab, "c": build_c, "d": build_d}.get(CMD, rep)()
