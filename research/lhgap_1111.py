# -*- coding: utf-8 -*-
"""H0408·H0409 전날 장 끝 1시간 시장 대비 × 오늘 시가 갭 시장 대비가 반대 방향 → 시가 매수 (2026-11-11 사용자).

 A 막판 강세 → 갭 하락: 전날 장 끝 1시간 시장 대비 올랐는데 오늘 시가가 시장 대비 낮게 열림
 B 막판 약세 → 갭 상승: 전날 장 끝 1시간 시장 대비 빠졌는데 오늘 시가가 시장 대비 높게 열림
 ① 말한 그대로 판: 막판 1시간(국장 14:30→종가 · 미장 15:00→종가) 시장 대비 > 0 · 갭 시장 대비 < 0 (반대는 부호만 바꿈)
 ② 변형 판: 문턱(막판 0·1·2·3%p × 갭 0·1·2·3%p) · 막판 창(30분·1시간·2시간) · 매도(30분·1시간·종가·다음 날 시가)
            · 대상(거래대금 아래·위 절반) · 그날 시장(시장 갭 하락·상승 날) · 갭 깊이 대조(막판 조건 없이 갭만 같은 종목)
 '시장' = 그날 유니버스 중앙값. 매수 = 오늘 시가(첫 체결). 1분봉: 국장 2022-12~2026-10(비용 0.23) · 미장 2021-12~2026-10(비용 0.25).
 학습 ~2024 / 검증 2025~ · 날 바구니 t. 살 수 있는 것만: 전날 거래대금 국장 10억↑·미장 $500만↑, 국장 1,000원↑·미장 $5↑, |갭|<25%, 시가가 개장 5분 안 체결.
    python research/lhgap_1111.py kr build|rep    python research/lhgap_1111.py us build|rep
"""
import os, sys, glob, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
os.chdir(BASE); sys.path[:0] = [str(ROOT), str(BASE)]
if sys.stdout is not None: sys.stdout.reconfigure(encoding="utf-8")
MK = sys.argv[1]; CMD = sys.argv[2]
OUTD = Path("C:/temp/kp/lhgap"); OUTD.mkdir(parents=True, exist_ok=True)
if MK == "kr":
    TZ, START, COST, MINV, MINP = None, 9 * 60 + 1, 0.23, 1e9, 1000
    PER = (("학습 22.12~24", "20221201", "20241231"), ("검증 25~", "20250101", "20991231"))
    NAME, LHN = "국장", "14:30"
else:
    TZ, START, COST, MINV, MINP = "America/New_York", 9 * 60 + 31, 0.25, 5e6, 5
    PER = (("학습 21.12~24", "20211201", "20241231"), ("검증 25~", "20250101", "20991231"))
    NAME, LHN = "미장", "15:00"
NMIN = 391
LHW = {"30분": 359, "1시간": 329, "2시간": 269}          # 끝 시각 봉 인덱스: 장 끝 30분·60분·120분 전(국장 15:00·14:30·13:30 · 미장 15:30·15:00·14:00)


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


def build():
    files = sorted(glob.glob(str(BASE / "data" / "m1" / ("KR" if MK == "kr" else "US") / "bf" / "*.parquet")))
    if os.environ.get("LIM"): files = files[:int(os.environ["LIM"])]
    rows = []
    for i, f in enumerate(files):
        t = Path(f).stem
        if MK == "kr" and not t.endswith("0"): continue
        try: days, O, Cf, V = load(f)
        except Exception: continue
        if len(days) < 30: continue
        j = np.argmax(~np.isnan(O), axis=1); op = O[np.arange(len(days)), j]; op[np.isnan(O).all(axis=1)] = np.nan
        cl = Cf[:, -1]
        d = {"t": t, "date": days, "op": op, "cl": cl, "val": np.nansum(np.where(V > 0, Cf * V, 0), axis=1), "x30": Cf[:, 29], "x60": Cf[:, 59], "late": j > 5}
        for k_, ix in LHW.items(): d["lh_" + k_] = (cl / Cf[:, ix] - 1) * 100
        rows.append(pd.DataFrame(d))
        if i % 300 == 0: print(i, len(files), flush=True)
    D = pd.concat(rows, ignore_index=True).sort_values(["t", "date"]).reset_index(drop=True)
    g = D.groupby("t")
    D["pcl"] = g.cl.shift(1); D["pval"] = g.val.shift(1); D["nop"] = g.op.shift(-1)
    for k_ in LHW: D["p_" + k_] = g["lh_" + k_].shift(1)
    D["gap"] = (D.op / D.pcl - 1) * 100
    D["oc"] = (D.cl / D.op - 1) * 100 - COST; D["o30"] = (D.x30 / D.op - 1) * 100 - COST; D["o60"] = (D.x60 / D.op - 1) * 100 - COST
    D["on"] = (D.nop / D.op - 1) * 100 - COST
    D.loc[D.on.abs() > 40, "on"] = np.nan
    D = D.dropna(subset=["gap", "p_1시간", "oc"])
    D = D[(D.gap.abs() < 25) & (D["p_1시간"].abs() < 25)]
    D["mgap"] = D.groupby("date").gap.transform("median"); D["rgap"] = D.gap - D.mgap
    for k_ in LHW:
        D["r_" + k_] = D["p_" + k_] - D.groupby("date")["p_" + k_].transform("median")
    D["ok"] = (D.pval >= MINV) & (D.pcl >= MINP) & ~D.late
    D["big"] = D.pval >= D.pval.where(D.ok).groupby(D.date).transform("median")
    keep = ["t", "date", "gap", "rgap", "mgap", "oc", "o30", "o60", "on", "ok", "big", "pval"] + ["r_" + k_ for k_ in LHW]
    D[keep].to_pickle(OUTD / ("%s.pkl" % MK)); print("끝", len(D), int(D.ok.sum()))


OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))
EXITS = (("o30", "30분 뒤"), ("o60", "1시간 뒤"), ("oc", "종가"), ("on", "다음 날 시가"))


def cell(z, col):
    z = z.dropna(subset=[col])
    if len(z) < 30: return "%d건" % len(z)
    d = z.groupby("date")[col].mean(); t = d.mean() / d.std() * np.sqrt(len(d)) if len(d) > 3 and d.std() > 0 else np.nan
    return "%d건 **%+.2f** (중앙 %+.2f·승 %.0f%%) · 날 %+.2f t%.1f" % (len(z), z[col].mean(), z[col].median(), (z[col] > 0).mean() * 100, d.mean(), t)


def two(z, col): return " | ".join(cell(z[(z.date >= a) & (z.date <= b)], col) for _, a, b in PER)


def short(z, col):
    out = []
    for _, a, b in PER:
        x = z[(z.date >= a) & (z.date <= b)][col].dropna()
        out.append("%+.2f(%d)" % (x.mean(), len(x)) if len(x) >= 30 else "—(%d)" % len(x))
    return " / ".join(out)


def rep():
    from verdict import log_trials
    D = pd.read_pickle(OUTD / ("%s.pkl" % MK)); D = D[D.ok]
    P("# [%s] 전날 막판 시장 대비 × 오늘 시가 갭 시장 대비 반대 (H0408·H0409) · 2026-11-11" % NAME); P("")
    P("- 1분봉 %s~%s · 살 수 있는 종목·날 %s행 · 비용 %.2f 뒤 · 시장 = 그날 유니버스 중앙 · 칸 = 건수 **건당**(중앙·승률) · 날 바구니 평균 t" % (D.date.min(), D.date.max(), f"{len(D):,}", COST))
    P("- 바닥선(아무 종목 시가 매수): " + " · ".join("%s 30분 %+.2f / 1시간 %+.2f / 종가 %+.2f / 다음 날 시가 %+.2f" % (
        pn, *(D[(D.date >= a) & (D.date <= b)][c].mean() for c in ("o30", "o60", "oc", "on"))) for pn, a, b in PER)); P("")
    n = 0
    A0 = (D["r_1시간"] > 0) & (D.rgap < 0); B0 = (D["r_1시간"] < 0) & (D.rgap > 0)
    P("## ① 말한 그대로 — 막판 1시간(%s→종가) 시장 대비 부호 × 갭 시장 대비 반대 부호, 시가 매수" % LHN); P("")
    P("| 무리 | 매도 | 학습 | 검증 |"); P("|---|---|---|---|")
    for nm, m in (("A 막판 시장보다 오름 → 시장보다 낮게 열림", A0), ("B 막판 시장보다 빠짐 → 시장보다 높게 열림", B0),
                  ("대조: 시장보다 낮게 열림(막판 조건 없음)", D.rgap < 0), ("대조: 시장보다 높게 열림(막판 조건 없음)", D.rgap > 0), ("대조: 아무 종목", D.rgap == D.rgap)):
        for col, cn in EXITS:
            P("| %s | %s | %s |" % (nm, cn, two(D[m], col))); n += 1
    P("")
    P("## ② 변형 — 문턱 그리드(막판 1시간) · 칸 = 건당 학습 / 검증 (건수)"); P("")
    for kind in ("A", "B"):
        P("### %s · 매도별" % ("A 막판 강세 → 갭 하락" if kind == "A" else "B 막판 약세 → 갭 상승")); P("")
        P("| 막판 | 갭 | 30분 뒤 | 1시간 뒤 | 종가 | 다음 날 시가 | 대조(갭만) 종가 |"); P("|---|---|---|---|---|---|---|")
        for X in (0, 1, 2, 3):
            for Y in (0, 1, 2, 3):
                if kind == "A": m = (D["r_1시간"] > X) & (D.rgap < -Y); c = D.rgap < -Y
                else: m = (D["r_1시간"] < -X) & (D.rgap > Y); c = D.rgap > Y
                P("| %s%d | %s%d | %s | %s |" % ("+" if kind == "A" else "-", X, "-" if kind == "A" else "+", Y, " | ".join(short(D[m], col) for col, _ in EXITS), short(D[c], "oc"))); n += 4
        P("")
    P("## ③ 변형 — 막판 창 길이(문턱 1%p·1%p) · 종가 / 다음 날 시가"); P("")
    P("| 무리 | 막판 창 | 종가 | 다음 날 시가 |"); P("|---|---|---|---|")
    for kind in ("A", "B"):
        for k_ in LHW:
            m = ((D["r_" + k_] > 1) & (D.rgap < -1)) if kind == "A" else ((D["r_" + k_] < -1) & (D.rgap > 1))
            P("| %s | %s | %s | %s |" % (kind, k_, short(D[m], "oc"), short(D[m], "on"))); n += 2
    P("")
    P("## ④ 변형 — 대상·그날 시장(문턱 1%p·1%p · 막판 1시간) · 종가"); P("")
    P("| 무리 | 나눔 | 종가 | 대조(갭만) 종가 |"); P("|---|---|---|---|")
    for kind in ("A", "B"):
        m = ((D["r_1시간"] > 1) & (D.rgap < -1)) if kind == "A" else ((D["r_1시간"] < -1) & (D.rgap > 1))
        c = (D.rgap < -1) if kind == "A" else (D.rgap > 1)
        for nm, s in (("거래대금 위 절반", D.big), ("거래대금 아래 절반", ~D.big), ("시장 갭 하락 날(중앙 <0)", D.mgap < 0), ("시장 갭 상승 날(중앙 ≥0)", D.mgap >= 0)):
            P("| %s | %s | %s | %s |" % (kind, nm, short(D[m & s], "oc"), short(D[c & s], "oc"))); n += 1
    P("")
    P("## 참고 — 막판 효과만(갭 조건 없음) · 다음 날 시가 매수 → 종가"); P("")
    P("| 전날 막판 1시간(시장 대비) | 학습 | 검증 |"); P("|---|---|---|")
    for a_, b_ in ((-99, -3), (-3, -1), (-1, 1), (1, 3), (3, 99)):
        z = D[(D["r_1시간"] > a_) & (D["r_1시간"] <= b_)]
        P("| %s~%s%%p | %s |" % (a_, b_, two(z, "oc"))); n += 1
    P(""); P("(칸 %d)" % n)
    log_trials("lhgap_%s_1111" % MK, n)
    (ROOT / "reports" / ("lhgap_%s_1111.md" % MK)).write_text("\n".join(OUT) + "\n", encoding="utf-8")


if __name__ == "__main__":
    {"build": build, "rep": rep}[CMD]()
