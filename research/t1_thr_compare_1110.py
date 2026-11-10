# -*- coding: utf-8 -*-
"""[갭 하락 조용주] 지정가 문턱을 깊게 하면 지금과 얼마나 다른가(2026-11-10 사용자 "바꾸면 기존이랑 어느 정도 차이 나는지 상세 비교표").
실전 기록(data/day/snap_*.json 후보 전부 · 10-13 부터 문턱 -1.5 고정) 위에서 지정가만 바꿔 다시 맞춘다:
  새 지정가 = 그날 실전 지정가 × (1 + (새 문턱 − (−1.5))%) (호가 단위 내림) · 사짐 = KRX 시가 ≤ 새 지정가 → 시가에 사서 KRX 종가에 판다, 비용 0.23
  KRX 시가·종가 = 서버 1분봉 파일(첫 봉 시가·마지막 봉 종가 — 정규장 값) · 연구 조건(실제 시장 대비 ≤ -1.5) = KRX 어제 종가·그날 시장 갭(유니버스 중앙)
  금액 판 = 실전 금액 규칙(기준 30만 × 깊이 1~3 × 거래대금 배율 0.3~3), 돈 제한 없음 · 덤(T2·T3)·T4 도 같은 지정가로 같이 본다
    python research/t1_thr_compare_1110.py
"""
import sys, json, glob
from pathlib import Path
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(BASE)); sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
import day_alert as D

THRS = (-1.5, -1.75, -2.0, -2.25, -2.5, -3.0)
COST = 0.23
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))


def tick(p):
    t = 1 if p < 2000 else 5 if p < 5000 else 10 if p < 20000 else 50 if p < 50000 else 100 if p < 200000 else 500 if p < 500000 else 1000
    return int(p // t * t)


def m1(day):
    f = BASE / "data" / "m1" / "KR" / "day" / ("%s.parquet" % day)
    if not f.exists(): return None
    X = pd.read_parquet(f, columns=["t", "ts", "o", "c", "v"]); X = X[X.v > 0].sort_values(["t", "ts"]); g = X.groupby("t")
    return pd.DataFrame({"o": g.o.first(), "c": g.c.last()})


def main():
    days = sorted(p[-13:-5] for p in glob.glob(str(BASE / "data" / "day" / "snap_*.json")) if p[-13:-5] >= "20261013")
    rows, prev = [], None
    allm = sorted(p[-16:-8] for p in glob.glob(str(BASE / "data" / "m1" / "KR" / "day" / "*.parquet")))
    for d in days:
        K = m1(d); pv = max([x for x in allm if x < d], default=None); Kp = m1(pv) if pv else None
        if K is None or Kp is None: continue
        s = json.loads((BASE / "data" / "day" / ("snap_%s.json" % d)).read_text(encoding="utf-8"))
        uni = [t for t in (s.get("all") or {}) if t in K.index and t in Kp.index]
        mg = float(np.median([(K.o[t] / Kp.c[t] - 1) * 100 for t in uni])) if uni else np.nan    # 그날 실제 시장 갭(유니버스 중앙, KRX)
        for x, rid in D.order_list(s.get("cand") or []):
            t = x["t"]
            if t not in K.index or t not in Kp.index or not x.get("lim") or not x.get("pc"): continue
            o, c, pcK = float(K.o[t]), float(K.c[t]), float(Kp.c[t])
            rows.append(dict(date=d, t=t, name=x.get("name"), rid=rid, lim=float(x["lim"]), pc=float(x["pc"]), o=o, c=c,
                             relK=(o / pcK - 1) * 100 - mg, ret=(c / o - 1) * 100 - COST,
                             amt=D.DAY_BASE * D.day_mult(x) * (float(x.get("lm") or 1) if rid != "T4" else 1)))
    A = pd.DataFrame(rows)
    P("후보 줄 %d · %s~%s · %d거래일 (T1 %d · 덤·T4 %d)\n" % (len(A), A.date.min(), A.date.max(), A.date.nunique(), (A.rid == "T1").sum(), (A.rid != "T1").sum()))
    nd = A.date.nunique()

    def cell(Z):
        if not len(Z): return "0건", "-", "-", "-", "-", "-"
        w = (Z.amt * Z.ret / 100).sum()
        return ("%d건(하루 %.1f)" % (len(Z), len(Z) / nd), "%+.2f%%" % Z.ret.mean(), "%.0f%%" % ((Z.ret > 0).mean() * 100), "%+.2f%%" % Z.ret.median(),
                "%.0f%%" % ((Z.relK <= -1.5).mean() * 100), "%+.0f만(하루 %+.1f만)" % (w / 1e4, w / 1e4 / nd))
    for nm, S in (("T1 본체", A[A.rid == "T1"]), ("전체(T1+덤+T4)", A)):
        P("### %s\n" % nm)
        P("| 지정가 문턱 | 사진 건수 | 건당 | 승률 | 중앙 | 연구 조건 맞는 비율 | 30만 기준 손익 |"); P("|---|---|---|---|---|---|---|")
        base = None
        for th in THRS:
            sh = th - (-1.5)
            lim = np.array([tick(l * (1 + sh / 100)) for l in S.lim]) if sh else S.lim.to_numpy()
            Z = S[S.o.to_numpy() <= lim]
            if th == -1.5: base = Z
            P("| %s%.2f%%p | %s |" % ("**지금** " if th == -1.5 else "", th, " | ".join(cell(Z))))
        P("")
    S = A[A.rid == "T1"]
    P("### 지금(-1.5) 대비 -2.0 으로 바꾸면 빠지는 몫·남는 몫 (T1 본체)\n")
    lim2 = np.array([tick(l * 0.995) for l in S.lim])
    now = S[S.o <= S.lim]; new = S[S.o.to_numpy() <= lim2]; drop = now[~now.index.isin(new.index)]
    P("| 몫 | 건수 | 건당 | 승률 | 연구 조건 맞는 비율 |"); P("|---|---|---|---|---|")
    for nm, Z in (("남는 몫(-2.0 에서도 사짐)", new), ("빠지는 몫(-1.5 에선 사지고 -2.0 에선 안 사짐)", drop)):
        P("| %s | %d | %+.2f%% | %.0f%% | %.0f%% |" % (nm, len(Z), Z.ret.mean() if len(Z) else 0, (Z.ret > 0).mean() * 100 if len(Z) else 0, (Z.relK <= -1.5).mean() * 100 if len(Z) else 0))
    P("\n### 구간별(T1 본체 · 건당 / 건수)\n")
    P("| 문턱 | 10-13~10-31(어제 종가 = 토스 통합) | 11-02~(어제 종가 = KRX) |"); P("|---|---|---|")
    for th in THRS:
        sh = th + 1.5; lim = np.array([tick(l * (1 + sh / 100)) for l in S.lim]) if sh else S.lim.to_numpy()
        Z = S[S.o.to_numpy() <= lim]
        a, b = Z[Z.date <= "20261031"], Z[Z.date >= "20261102"]
        P("| %.2f | %+.2f%% / %d | %+.2f%% / %d |" % (th, a.ret.mean() if len(a) else 0, len(a), b.ret.mean() if len(b) else 0, len(b)))
    P("\n참고: 연구 조건을 그대로(실제 시장 대비 ≤ -1.5) 맞췄다면 T1 본체 %d건 · 건당 %+.2f%% · 승률 %.0f%%" % (
        (S.relK <= -1.5).sum(), S[S.relK <= -1.5].ret.mean(), (S[S.relK <= -1.5].ret > 0).mean() * 100))
    (ROOT / "t1_thr_compare_1110.out").write_text("\n".join(OUT), encoding="utf-8")


if __name__ == "__main__":
    main()
