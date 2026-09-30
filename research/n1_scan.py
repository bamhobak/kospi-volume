# -*- coding: utf-8 -*-
"""[상승장 신고가] N1 좁히기 — 건수는 줄이고 건당 성적은 올리는 거르개 찾기 (2026-09-30 사용자 요청, N6 좁히기처럼).

신호: us_capture 준비부(폐지 포함 us_full_2007 · 사이트 정의 · 40일 보유 · 2008~)
재료(신호일 종가까지 아는 값):
  패널 숫자 열 전부(fromhi·remo·pinr·hl20·absr·su1·ret20·ret60·PBR·부채비율·marcap·a240·amt20 …)
  + 직접 만든 것: 6·12개월 수익(ret120·ret250) · 20일 변동성 · 오늘 등락 · 5일 등락 · 20일선 이격
    · S&P 60일선 이격·20일 수익 · 그날 N1 신호 수(신고가 쏠림) · 같은 업종(sic2) 같은 날 N1 수 · 거래대금 그날 백분위
  + 되밀림·되오름 상태 192개(rule_retrace 와 같음)
거르개: 재료마다 **학습 신호의 분위(20·33·50·67·80%)** 를 문턱으로 '이상만 남김'·'이하만 남김'
판정: 남는 신호 평균 − 규칙 전체 평균을, 같은 건수 무작위 선택의 표준오차로 나눈 z.
  학습(16~22) z ≥ 2 & 검증(23~) z ≥ 2 & 옛날(08~15) Δ ≥ 0 & 남는 비율 ≤ 70%  → 통과
  통과 칸은 중앙값·상위5% 절삭·해별로 다시 본다. 칸 수만큼 우연 통과 기대치도 적는다.

    python research/n1_scan.py
"""
import sys, time, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(BASE)); sys.path.insert(0, str(ROOT))
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))


def log(m):
    print("%s %s" % (time.strftime("%H:%M:%S"), m), file=sys.stderr, flush=True)


def prep():
    src = (ROOT / "us_capture.py").read_text(encoding="utf-8").split("# ── ① 미장 계좌")[0]
    src = src.replace('"--since", "20160101"', '"--since", "20080101"').replace('S = S[S.date >= "20160101"]', 'S = S[S.date >= "20080101"]')
    src = src.split("# ── 기준 지수")[0]
    ns = {"__file__": str(ROOT / "us_capture.py"), "__name__": "us_capture_prep"}
    exec(compile(src, "us_capture.py", "exec"), ns)
    return ns


def main():
    t0 = time.time()
    ns = prep()
    sys.stdout.reconfigure(encoding="utf-8")
    S, PATH, K = ns["S"], ns["PATH"], ns["K"]
    r = []
    for i in range(len(S)):
        ddi, ratio = PATH[i]
        done = len(ddi) and ddi[-1] >= S.di[i] + S.hold[i] - 3
        r.append((ratio[-1] - 1) * 100 - S.cost[i] if done else np.nan)
    S = S.assign(r=r)
    S = S[(S.rid == "N1")].dropna(subset=["r"]).reset_index(drop=True)
    log("N1 신호 %s건" % f"{len(S):,}")
    # ── 재료 ──
    K = K.sort_values(["ticker", "di"])
    g = K.groupby("ticker", sort=False).px
    K["ret120"] = (K.px / g.shift(120) - 1) * 100
    K["ret250"] = (K.px / g.shift(250) - 1) * 100
    K["ret5"] = (K.px / g.shift(5) - 1) * 100
    K["ret1"] = (K.px / g.shift(1) - 1) * 100
    K["_r"] = g.pct_change()
    K["vol20"] = K.groupby("ticker", sort=False)._r.transform(lambda z: z.rolling(20, min_periods=16).std()) * 100
    K["dma20"] = (K.px / g.transform(lambda z: z.rolling(20).mean()) - 1) * 100
    K["dma50"] = (K.px / g.transform(lambda z: z.rolling(50).mean()) - 1) * 100
    K["amtq"] = K.groupby("date").amt20.rank(pct=True)
    for L in (20, 40, 60, 120):
        K["b%d" % L] = g.shift(L)
        K["h%d" % L] = g.transform(lambda s: s.rolling(L + 1, min_periods=L + 1).max())
        K["l%d" % L] = g.transform(lambda s: s.rolling(L + 1, min_periods=L + 1).min())
    DENY = {"n5", "n10", "n20", "n40", "n60", "buy", "cost", "di", "_r", "grp", "ticker", "date"}
    num = [c for c in K.columns if c not in DENY and pd.api.types.is_numeric_dtype(K[c]) and K[c].dtype != bool]
    S = S.merge(K[["ticker", "date"] + num + ([] if "sic2" in num else ["sic2"])], on=["ticker", "date"], how="left", suffixes=("", "_k"))
    import FinanceDataReader as fdr
    ix = fdr.DataReader("US500", "2007-01-01"); ix = ix[ix.Close > 0]
    sp = pd.Series(ix.Close.values, index=ix.index.strftime("%Y%m%d"))
    S["spx60"] = S.date.map((sp / sp.rolling(60).mean() - 1) * 100)
    S["spx20"] = S.date.map((sp / sp.shift(20) - 1) * 100)
    S["crowd"] = S.groupby("date").ticker.transform("size")
    S["seccrowd"] = S.groupby(["date", "sic2"]).ticker.transform("size")
    S.to_pickle(ROOT / "cache" / "n1_scan_S.pkl")
    # ── 거르개 ──
    per = np.where(S.date.values <= "20151231", 0, np.where(S.date.values <= "20221231", 1, 2))
    R_ = S.r.values
    F = {}
    skip = {"b20", "h20", "l20", "b40", "h40", "l40", "b60", "h60", "l60", "b120", "h120", "l120", "sic2", "nh5", "hold", "rid"}
    feats = [c for c in S.columns if c not in skip | {"date", "ticker", "r", "rid"} and pd.api.types.is_numeric_dtype(S[c]) and S[c].dtype != bool]
    tr = per == 1
    for c in feats:
        x = S[c].values.astype(float)
        if np.isfinite(x[tr]).sum() < 300 or np.nanstd(x[tr]) == 0:
            continue
        for q in (0.2, 0.33, 0.5, 0.67, 0.8):
            th = np.nanquantile(x[tr], q)
            F["%s ≥ %.3g (학습 %d분위)" % (c, th, round(q * 100))] = x >= th
            F["%s ≤ %.3g (학습 %d분위)" % (c, th, round(q * 100))] = x <= th
    px = S.px.values
    LN = {20: "1달", 40: "2달", 60: "3달", 120: "6달"}
    for L in (20, 40, 60, 120):
        b, h, l = S["b%d" % L].values, S["h%d" % L].values, S["l%d" % L].values
        with np.errstate(all="ignore"):
            up = (h / b - 1) * 100; ru = (h - px) / (h - b); dn = (1 - l / b) * 100; rd = (px - l) / (b - l)
        for X in (10, 20, 30):
            for fv, fl in ((0.25, "1/4"), (1 / 3, "1/3"), (0.5, "1/2"), (2 / 3, "2/3")):
                F["U %s +%d%% 반납≥%s" % (LN[L], X, fl)] = (up >= X) & (ru >= fv) & (ru < 1)
                F["D %s -%d%% 회복≥%s" % (LN[L], X, fl)] = (dn >= X) & (rd >= fv) & (rd < 1)
    log("거르개 %d개" % len(F))
    rows = []
    for nm, m in F.items():
        for mode, keep in (("남김", m), ("뺌", ~m)) if nm.startswith(("U ", "D ")) else (("남김", m),):
            rec = dict(f=nm, mode=mode)
            for p_ in (0, 1, 2):
                a = per == p_; k = a & keep
                n, kk = a.sum(), k.sum()
                rec["k%d" % p_], rec["n%d" % p_] = int(kk), int(n)
                if kk < 30 or n - kk < 30:
                    rec["z%d" % p_] = rec["d%d" % p_] = rec["m%d" % p_] = np.nan; continue
                d = R_[k].mean() - R_[a].mean()
                se = R_[a].std() * np.sqrt(1 / kk * (n - kk) / (n - 1))
                rec["d%d" % p_], rec["z%d" % p_] = d, d / se
                rec["m%d" % p_], rec["all%d" % p_] = R_[k].mean(), R_[a].mean()
                rec["md%d" % p_], rec["mdall%d" % p_] = np.median(R_[k]), np.median(R_[a])
                rec["w%d" % p_], rec["wall%d" % p_] = (R_[k] > 0).mean() * 100, (R_[a] > 0).mean() * 100
            rows.append(rec)
    G = pd.DataFrame(rows)
    G.to_pickle(ROOT / "cache" / "n1_scan.pkl")
    T = G.dropna(subset=["z1", "z2"])
    share = (T.k1 + T.k2) / (T.n1 + T.n2)
    ok = T[(T.z1 >= 2) & (T.z2 >= 2) & ((T.d0 >= 0) | T.d0.isna()) & (share <= 0.7)]
    P("# [상승장 신고가] N1 좁히기 · %s" % time.strftime("%Y-%m-%d")); P("")
    a0, a1, a2 = [S.r[per == i] for i in range(3)]
    P("N1 신호(40일 보유 끝난 것): 옛날 08~15 %d건 평균 %+.2f%% · 학습 16~22 %d건 %+.2f%% · 검증 23~ %d건 %+.2f%%(승률 %.0f/%.0f/%.0f%%)" % (
        len(a0), a0.mean(), len(a1), a1.mean(), len(a2), a2.mean(), (a0 > 0).mean() * 100, (a1 > 0).mean() * 100, (a2 > 0).mean() * 100)); P("")
    P("- 판정 가능 %s칸 · 통과 **%d칸** · 우연 기대 ≈ %.1f칸" % (f"{len(T):,}", len(ok), len(T) * 0.0228 ** 2)); P("")
    if len(ok):
        P("| 거르개 | 남는 비율 | 옛날 평균 남김/전체 | 학습 평균 남김/전체 · 중앙 · 승률 | 검증 평균 남김/전체 · 중앙 · 승률 | z 학·검 |"); P("|---|---|---|---|---|---|")
        for _, x in ok.assign(sh=share).sort_values("z2", ascending=False).head(40).iterrows():
            f0 = "%+.2f / %+.2f" % (x.m0, x.all0) if x.m0 == x.m0 else "-"
            P("| %s %s | %.0f%% | %s | %+.2f / %+.2f · %+.2f/%+.2f · %.0f/%.0f%% | %+.2f / %+.2f · %+.2f/%+.2f · %.0f/%.0f%% | %.1f · %.1f |" % (
                x.f, "" if x["mode"] == "남김" else "(뺌)", x.sh * 100, f0, x.m1, x.all1, x.md1, x.mdall1, x.w1, x.wall1,
                x.m2, x.all2, x.md2, x.mdall2, x.w2, x.wall2, x.z1, x.z2))
    P(""); P("(%.0f분)" % ((time.time() - t0) / 60))
    from verdict import log_trials
    log_trials("n1_scan_%s" % time.strftime("%Y%m%d"), len(T))
    (ROOT / "reports" / ("n1_scan_%s.md" % time.strftime("%Y%m%d"))).write_text("\n".join(OUT) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
