# -*- coding: utf-8 -*-
"""되밀림·되오름 상태를 **지금 규칙 신호의 거르개**로 (2026-09-30 사용자: "방금 테스트한 거 지금 쓰는 규칙들이랑 접목").

재료(신호일 종가 기준, 미래 없음) — L = 20·40·60·120거래일, X = 10·20·30%:
  U(L,X,f)  L일 전 종가 대비 그 뒤 최고가가 +X%↑ 이고, 지금 상승분의 f 이상을 반납(기준가 아래는 아님)
  D(L,X,f)  L일 전 종가 대비 그 뒤 최저가가 -X%↓ 이고, 지금 하락분의 f 이상을 회복(기준가 위는 아님)
  f = 1/4·1/3·1/2·2/3  → 거르개 96개 × '그 상태인 신호만 남김' / '그 상태인 신호를 뺌' 두 방향
판정(자리 제한 없음 = 신호 나면 전부 산다 → 거래 단위):
  남는 신호의 평균 − 규칙 전체 평균(Δ)을, **같은 건수를 무작위로 남겼을 때의 흔들림**(표준오차)으로 나눈 z.
  학습(16~22) z ≥ 2 **그리고** 검증(23~) z ≥ 2, 옛날 Δ ≥ 0 이면 통과. 남는 신호 구간마다 30건↑.
  칸이 많으니(규칙 15 × 192) 우연 통과 기대치도 같이 적는다.
거래 수익: 국장 = portfolio.py 실제 청산 규칙 그대로(rule_scan.kr_signals r) · 미장 = 사이트 보유기간 끝 종가(폐지는 마지막 가격)

    python research/rule_retrace.py
"""
import io, sys, time, contextlib, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(BASE)); sys.path.insert(0, str(ROOT))
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))
LS = [20, 40, 60, 120]; LN = {20: "1달", 40: "2달", 60: "3달", 120: "6달"}
XS = [10, 20, 30]
FS = [(1 / 4, "1/4"), (1 / 3, "1/3"), (1 / 2, "1/2"), (2 / 3, "2/3")]
NAME = {"P1": "조용한 신고가", "P2": "조정매집", "P3": "낙폭과대", "P4": "급락 반등", "P5": "P5", "P6": "P6", "P7": "외인 매집",
        "D1": "D1", "D2": "D2", "N1": "상승장 신고가", "N2": "낙폭과대(미)", "N3": "저PBR 낙폭", "N4": "자사주 낙폭",
        "N5": "잔잔한 급등주", "N6": "실적 서프라이즈"}


def log(m):
    print("%s %s" % (time.strftime("%H:%M:%S"), m), file=sys.stderr, flush=True)


def feats(D, col):
    """D: ticker·date·가격(col) 정렬된 패널 → L 별 base·hi·lo"""
    D = D.sort_values(["ticker", "date"]).reset_index(drop=True)
    g = D.groupby("ticker", sort=False)[col]
    for L in LS:
        D["b%d" % L] = g.shift(L)
        D["h%d" % L] = g.transform(lambda s: s.rolling(L + 1, min_periods=L + 1).max())
        D["l%d" % L] = g.transform(lambda s: s.rolling(L + 1, min_periods=L + 1).min())
    return D


def masks(S, col):
    """신호표 S(가격 col·b/h/l 열 붙은) → {거르개 이름: bool 배열}"""
    M = {}
    c = S[col].values
    for L in LS:
        b, h, l = S["b%d" % L].values, S["h%d" % L].values, S["l%d" % L].values
        with np.errstate(all="ignore"):
            up = (h / b - 1) * 100; ru = (h - c) / (h - b)
            dn = (1 - l / b) * 100; rd = (c - l) / (b - l)
        for X in XS:
            for fv, fl in FS:
                M["U %s +%d%% 반납≥%s" % (LN[L], X, fl)] = (up >= X) & (ru >= fv) & (ru < 1)
                M["D %s -%d%% 회복≥%s" % (LN[L], X, fl)] = (dn >= X) & (rd >= fv) & (rd < 1)
    return M


def judge(S, M, mk):
    per = np.where(S.date.values <= "20151231", 0, np.where(S.date.values <= "20221231", 1, 2))
    rows = []
    for rid in sorted(S.rid.unique()):
        sel = S.rid.values == rid
        r = S.r.values
        for nm, m in M.items():
            for mode in ("남김", "뺌"):
                keep = m if mode == "남김" else ~m
                rec = dict(mk=mk, rid=rid, f=nm, mode=mode)
                okp = True
                for p_ in (0, 1, 2):
                    a = sel & (per == p_) & np.isfinite(r)
                    k = a & keep
                    n, kk = a.sum(), k.sum()
                    rec["k%d" % p_] = int(kk); rec["n%d" % p_] = int(n)
                    if kk < 30 or n - kk < 1:
                        rec["z%d" % p_] = np.nan; rec["d%d" % p_] = np.nan; rec["m%d" % p_] = np.nan; rec["all%d" % p_] = r[a].mean() if n else np.nan
                        continue
                    d = r[k].mean() - r[a].mean()
                    se = r[a].std() * np.sqrt(1 / kk * (n - kk) / max(n - 1, 1))
                    rec["d%d" % p_] = d; rec["z%d" % p_] = d / se if se > 0 else np.nan
                    rec["m%d" % p_] = r[k].mean(); rec["all%d" % p_] = r[a].mean()
                    rec["w%d" % p_] = (r[k] > 0).mean() * 100; rec["wall%d" % p_] = (r[a] > 0).mean() * 100
                rows.append(rec)
    return pd.DataFrame(rows)


# ── 국장 ─────────────────────────────────────────────────────────────────
def kr():
    import rule_scan as RS
    S = RS.kr_signals()[["date", "ticker", "rid", "r"]]
    sys.stdout = sys.__stdout__; sys.stdout.reconfigure(encoding="utf-8")
    K = pd.read_pickle(BASE / "data" / "kr_scan.pkl")[["ticker", "date", "close"]]
    K = feats(K, "close")
    S = S.merge(K, on=["ticker", "date"], how="left")
    log("국장 신호 %s건" % f"{len(S):,}")
    return judge(S, masks(S, "close"), "KR"), S


# ── 미장 ─────────────────────────────────────────────────────────────────
def us():
    src = (ROOT / "us_capture.py").read_text(encoding="utf-8").split("# ── ① 미장 계좌")[0]
    src = src.replace('"--since", "20160101"', '"--since", "20080101"').replace('S = S[S.date >= "20160101"]', 'S = S[S.date >= "20080101"]')
    ns = {"__file__": str(ROOT / "us_capture.py"), "__name__": "us_capture_prep"}
    exec(compile(src, "us_capture.py", "exec"), ns)
    S, PATH, K = ns["S"], ns["PATH"], ns["K"]
    r = []
    for i in range(len(S)):
        ddi, ratio = PATH[i]
        done = len(ddi) and ddi[-1] >= S.di[i] + S.hold[i] - 3
        r.append((ratio[-1] - 1) * 100 - S.cost[i] if done else np.nan)
    S = S.assign(r=r)[["date", "ticker", "rid", "r"]]
    F = feats(K[["ticker", "date", "px"]].copy(), "px")
    S = S.merge(F, on=["ticker", "date"], how="left")
    log("미장 신호 %s건" % f"{len(S):,}")
    return judge(S, masks(S, "px"), "US"), S


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    t0 = time.time()
    if "--us-only" in sys.argv:
        G2, S2 = us(); S2.to_pickle(ROOT / "cache" / "rule_retrace_us_S.pkl"); return
    G1, S1 = kr(); G2, S2 = us()
    S2.to_pickle(ROOT / "cache" / "rule_retrace_us_S.pkl")
    G = pd.concat([G1, G2], ignore_index=True)
    G.to_pickle(ROOT / "cache" / "rule_retrace.pkl")
    P("# 되밀림·되오름 상태를 지금 규칙에 얹기 · %s" % time.strftime("%Y-%m-%d")); P("")
    P("자리 제한 없음(신호 나면 전부 산다) 전제 · 거래 단위. z = (남는 신호 평균 − 규칙 전체 평균) ÷ 같은 건수 무작위 선택의 표준오차.")
    P("통과 = 학습 z≥2 & 검증 z≥2 & 옛날 Δ≥0(표본 있으면). 옛날 = 국장 2005~15 · 미장 2008~15."); P("")
    ok = G[(G.z1 >= 2) & (G.z2 >= 2) & ((G.d0 >= 0) | G.d0.isna())]
    tested = G.dropna(subset=["z1", "z2"])
    P("- 판정 가능한 칸 %s개(학습·검증 모두 남는 신호 30↑) · 통과 **%d칸** · 우연히 통과할 기대치 ≈ %.1f칸(두 구간 독립 가정 2.3%%×2.3%%)"
      % (f"{len(tested):,}", len(ok), len(tested) * 0.0228 ** 2)); P("")
    P("## 규칙별 요약 — 판정 가능 칸 수 · 학습·검증 둘 다 z≥2 칸 · 둘 다 z≤-2 칸(그 상태가 확실히 나쁨)"); P("")
    P("| 규칙 | 신호(옛·학·검) | 판정 가능 칸 | 둘 다 좋아짐 | 둘 다 나빠짐 |"); P("|---|---|---|---|---|")
    for (mk, rid), g in G.groupby(["mk", "rid"]):
        t = g.dropna(subset=["z1", "z2"])
        x = g.iloc[0]
        P("| [%s] %s | %d·%d·%d | %d | %d | %d |" % (NAME.get(rid, rid), rid, x.n0, x.n1, x.n2, len(t), ((t.z1 >= 2) & (t.z2 >= 2)).sum(), ((t.z1 <= -2) & (t.z2 <= -2)).sum()))
    if len(ok):
        P(""); P("## 통과 칸 전부"); P("")
        P("| 규칙 | 거르개 | 방향 | 남는 비율(학·검) | 옛날 평균 남김/전체 | 학습 평균 남김/전체 · 승률 | 검증 평균 남김/전체 · 승률 | z 학·검 |"); P("|---|---|---|---|---|---|---|---|")
        for _, x in ok.sort_values(["mk", "rid", "z2"], ascending=[True, True, False]).iterrows():
            f0 = "%+.2f / %+.2f" % (x.m0, x.all0) if x.m0 == x.m0 else "-"
            P("| [%s] %s | %s | %s | %.0f%% · %.0f%% | %s | %+.2f / %+.2f · %.0f%%/%.0f%% | %+.2f / %+.2f · %.0f%%/%.0f%% | %.1f · %.1f |" % (
                NAME.get(x.rid, x.rid), x.rid, x.f, x["mode"], x.k1 / x.n1 * 100, x.k2 / x.n2 * 100, f0,
                x.m1, x.all1, x.w1, x.wall1, x.m2, x.all2, x.w2, x.wall2, x.z1, x.z2))
    P(""); P("(%.0f분)" % ((time.time() - t0) / 60))
    from verdict import log_trials
    log_trials("rule_retrace_%s" % time.strftime("%Y%m%d"), len(tested))
    (ROOT / "reports" / ("rule_retrace_%s.md" % time.strftime("%Y%m%d"))).write_text("\n".join(OUT) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
