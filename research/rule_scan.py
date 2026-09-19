# -*- coding: utf-8 -*-
"""**규칙 안 스캔** — 우리 규칙이 실제로 산 종목 **안에서** 무엇이 잘된 쪽과 안된 쪽을 가르나 (2026-09-19).

왜: 시장 전체 축 스캔에서 살아남은 공매도 거래 비중(H0081)이 우리 규칙 신호 안에서는 아무것도 못 갈랐다
(같은 달 짝비교 -0.11%p). 우리 규칙은 폭락 직후 같은 특수한 종목만 산다 — 시장 전체의 경향이 그 안에서도
통하는지는 따로 재야 한다. 그래서 순서를 뒤집어 **규칙 신호 안에서 직접** 훑는다.

방법 (같은 규칙 · 같은 달 짝비교 — [[p4-credit-adopted]] 의 판정 도구)
  · 신호마다 실제 거래 수익 r(보유기간 끝 종가 청산·비용 차감)
  · (규칙, 달) 묶음마다 신호가 4개↑ 이면 재료 기준 위 절반·아래 절반의 **중앙값 차이**
  · 묶음 차이를 모아 평균 D · 묶음 부트스트랩 95% 구간 · 학습(~2022)과 검증(2023~) 방향 ·
    규칙별 방향(묶음 5개↑ 규칙 중 같은 방향 2/3↑)
  · 통과 = 95% 구간이 0 을 안 걸침 & 학습·검증 같은 방향 & 규칙 2/3 같은 방향
  통과한 재료는 **계좌 얹기**(sv_overlay.py 방식)로 넘긴다. 여기서는 후보만 고른다.

재료 = 보유 재료(features / features_us) + 패널의 수치 열. 미래 열(n5·n20·buy·exit 등)은 이름으로 막는다.

    python research/rule_scan.py KR      → research/reports/rule_scan_kr_YYYYMMDD.md
    python research/rule_scan.py US
"""
import os, pickle, re, sys, time, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(BASE)); sys.path.insert(0, str(ROOT))
from verdict import log_trials

DENY = re.compile(r"^(n\d+|buy|exit|cost|hold|pct|mx|stop|trail|di|rid|ret|r|ym|_.*"
                  r"|close|open|high|low|volume|rawclose|px|p_open|p_high|p_low)$|fwd|next|fut")   # 미래 열·가격 수준
TR1 = "20221231"
OUT = []


def P(x=""):
    OUT.append(x)


def log(m):
    print("%s %s" % (time.strftime("%H:%M:%S"), m), file=sys.stderr, flush=True)


def kr_signals():
    SRC = (BASE / "portfolio.py").read_text(encoding="utf-8")
    HEAD, REST = SRC.split("# 신호를 한 표로 모은다", 1)
    MID = "# 신호를 한 표로 모은다" + REST.split("# @@ANALYSIS", 1)[0]
    os.environ["SKIP"] = ""
    real = sys.stdout; ns = {"__file__": str(BASE / "portfolio.py")}
    exec(compile(HEAD, "portfolio.py", "exec"), ns); exec(compile(MID, "portfolio.py", "exec"), ns)
    globals()["_KEEP"] = sys.stdout; sys.stdout = real
    S = ns["S"].copy()
    S["r"] = (S.exit / S.buy - 1) * 100 - S.cost
    S = S[["date", "ticker", "rid", "r", "amt20"]]
    # 패널 수치 열(규칙 조건 판정 시점의 값)
    panels = []
    for key in ("KP", "KQ", "KB"):
        K = ns.get(key)
        if K is not None:
            num = [c for c in K.columns if c not in ("date", "ticker") and not DENY.search(c)
                   and pd.api.types.is_numeric_dtype(K[c]) and K[c].dtype != bool]
            panels.append(K[["date", "ticker"] + num])
    Pn = pd.concat(panels).drop_duplicates(["date", "ticker"])
    S = S.merge(Pn, on=["date", "ticker"], how="left", suffixes=("", "_p"))
    cal = sorted(set(ns["KP"].date) | set(ns["KQ"].date))
    import features as FT
    FT.attach(S, cal=cal)
    return S


def us_signals():
    S = pickle.load(open(BASE / "data" / "sector_drop_us_sig.pkl", "rb"))["S"].copy()
    S["r"] = S.ret.astype(float)
    if S.r.abs().median() < 1:                      # 비율이면 % 로
        S["r"] = S.r * 100
    S = S[["date", "ticker", "rid", "r", "amt20"]]
    K = pd.read_pickle(BASE / "data/us_scan.pkl")
    cal = sorted(K.date.unique())
    num = [c for c in K.columns if c not in ("date", "ticker", "amt20") and not DENY.search(c)
           and pd.api.types.is_numeric_dtype(K[c]) and K[c].dtype != bool]
    S = S.merge(K[["date", "ticker"] + num], on=["date", "ticker"], how="left")
    del K
    import features_us as FU
    FU.attach(S, cal=cal)
    return S


def scan(S, col, rng):
    z = S[["rid", "date", "r", col]].dropna()
    z = z[np.isfinite(z[col])]
    if len(z) < 300 or z[col].nunique() < 5:
        return None
    z["ym"] = z.date.str[:6]
    rows = []
    for (rid, ym), g in z.groupby(["rid", "ym"]):
        if len(g) < 4 or g[col].nunique() < 2:
            continue
        hi = g[col].rank(pct=True, method="average") > 0.5
        if hi.sum() == 0 or (~hi).sum() == 0:
            continue
        rows.append((rid, ym, g.r[hi].median() - g.r[~hi].median(), min(hi.sum(), (~hi).sum())))
    if len(rows) < 30:
        return None
    G = pd.DataFrame(rows, columns=["rid", "ym", "d", "w"])
    D = np.average(G.d, weights=G.w)
    bs = [np.average(G.d.values[i], weights=G.w.values[i])
          for i in (rng.integers(0, len(G), len(G)) for _ in range(1000))]
    lo, hi = np.percentile(bs, [2.5, 97.5])
    tr = G[G.ym <= TR1[:6]]; va = G[G.ym > TR1[:6]]
    dtr = np.average(tr.d, weights=tr.w) if len(tr) >= 10 else np.nan
    dva = np.average(va.d, weights=va.w) if len(va) >= 10 else np.nan
    per = {}
    for rid, g in G.groupby("rid"):
        if len(g) >= 5:
            per[rid] = np.average(g.d, weights=g.w)
    same = sum(1 for v in per.values() if np.sign(v) == np.sign(D))
    ok = (lo > 0 or hi < 0) and np.sign(dtr) == np.sign(D) and np.sign(dva) == np.sign(D) \
        and len(per) >= 2 and same * 3 >= len(per) * 2
    return dict(col=col, n=len(z), groups=len(G), D=D, lo=lo, hi=hi, dtr=dtr, dva=dva,
                per=per, same=same, nr=len(per), ok=ok)


def main():
    sys.stdout.reconfigure(encoding="utf-8"); t0 = time.time()
    mk = (sys.argv[1] if len(sys.argv) > 1 else "KR").upper()
    log("%s 규칙 신호" % mk)
    S = kr_signals() if mk == "KR" else us_signals()
    cols = [c for c in S.columns if c not in ("date", "ticker", "rid", "r", "amt20") and not DENY.search(c)
            and pd.api.types.is_numeric_dtype(S[c]) and S[c].dtype != bool]
    log("신호 %s건 · 재료 %d개" % (f"{len(S):,}", len(cols)))
    rng = np.random.default_rng(0)
    R = [x for x in (scan(S, c, rng) for c in cols) if x]
    R.sort(key=lambda x: -abs(x["D"]) / max((x["hi"] - x["lo"]) / 3.92, 1e-9))
    rules = sorted(S.rid.unique())
    P("# 규칙 안 스캔 · %s · %s" % (mk, time.strftime("%Y-%m-%d"))); P("")
    P("신호 %s건 · 규칙 %s · 재료 %d개(잰 것 %d개). D = 같은 규칙·같은 달 안에서 재료 **위 절반 − 아래 절반**의 "
      "거래 수익 중앙값 차(%%p). 양수면 재료가 클수록 좋다." % (f"{len(S):,}", " ".join(rules), len(cols), len(R))); P("")
    P("통과 = 95%% 구간이 0 을 안 걸침 · 학습(~2022)·검증(2023~) 같은 방향 · 규칙 2/3 이상 같은 방향"); P("")
    P("| 재료 | 신호 | 묶음 | D | 95%% 구간 | 학습 | 검증 | 규칙 같은방향 | 규칙별 D | 통과 |")
    P("|---|---|---|---|---|---|---|---|---|---|")
    for x in R[:40]:
        P("| %s | %s | %d | %+.2f | %+.2f ~ %+.2f | %+.2f | %+.2f | %d/%d | %s | %s |" % (
            x["col"], f"{x['n']:,}", x["groups"], x["D"], x["lo"], x["hi"], x["dtr"], x["dva"], x["same"], x["nr"],
            " ".join("%s%+.1f" % (k, v) for k, v in sorted(x["per"].items())), "✅" if x["ok"] else ""))
    ok = [x for x in R if x["ok"]]
    P(""); P("통과 %d개: %s" % (len(ok), ", ".join("%s(%+.2f)" % (x["col"], x["D"]) for x in ok) or "없음"))
    exp = len(R) * 0.05
    P("※ 재료 %d개를 5%% 유의수준으로 봤으니 **운으로도 %.1f개쯤은 95%% 구간을 통과**한다 — 학습·검증·규칙 방향 조건이 그걸 거른다." % (len(R), exp))
    P(""); P("총 %.0f초" % (time.time() - t0))
    log_trials("rule_scan_%s_%s" % (mk.lower(), time.strftime("%Y%m%d")), len(R))
    rp = ROOT / "reports" / ("rule_scan_%s_%s.md" % (mk.lower(), time.strftime("%Y%m%d")))
    rp.write_text("\n".join(OUT) + "\n", encoding="utf-8")
    print("\n".join(OUT)); print("\n보고서:", rp)


if __name__ == "__main__":
    main()
