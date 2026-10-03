# -*- coding: utf-8 -*-
"""B — 1분봉 연구 도구 + 첫 시험: A 의 '갭 하락 데이' 후보를 장중 언제 사고 언제 팔면 좋은가 (2026-10-03).

도구: day_points(mk, tickers) — 1분봉(data/m1/{mk}/bf · day)을 종목-일 한 줄로: 시가(09:01 봉 시가) · 정해진 시각 가격 ·
      그날 종가(15:31 봉) · 첫 30분 VWAP·고저. 다른 장중 연구도 이걸 쓴다.
시험(국장 · 지금까지 받은 거래대금 상위 종목 · 2022-12~):
  후보 = A(oc_day.py)와 같은 정의 — 그날 유니버스(거래대금 상위 40%) 안에서 오늘 갭 하위 10% & 어제 거래량 배수 하위 30%
  들어가기: 시가(장전 단일가) / 09:05 / 09:10 / 09:30 / 첫 30분 VWAP 아래에서 사는 지정가(10:00 까지 안 닿으면 안 산다)
  나오기:   종가(15:31) / 11:00 / 13:00 / 15:00
  비용: 시가·종가 단일가 0.22% · 장중 시장가가 끼면 +0.05%(미끄러짐)
  견줄 것: 같은 종목들의 '후보 아닌 날'(아무 날)
    python research/m1_lab.py
"""
import glob, sys, time
from pathlib import Path
import numpy as np, pandas as pd
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(BASE))
KST = ZoneInfo("Asia/Seoul")
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))
TIMES = ["0905", "0910", "0930", "1100", "1300", "1500"]


def day_points(mk="KR", tickers=None):
    fs = sorted(glob.glob(str(BASE / f"data/m1/{mk}/bf/*.parquet")))
    if tickers is not None:
        fs = [f for f in fs if Path(f).stem in set(tickers)]
    out = []
    for f in fs:
        D = pd.read_parquet(f)
        t = pd.to_datetime(D.ts, unit="s", utc=True).dt.tz_convert(KST)
        D["date"] = t.dt.strftime("%Y%m%d"); D["hm"] = t.dt.strftime("%H%M")
        D = D.sort_values("ts")
        g = D.groupby("date")
        r = pd.DataFrame({"o": g.o.first(), "c": g.c.last(), "n": g.size()})
        for hm in TIMES:                                   # 그 시각에 끝난 봉의 종가(없으면 그 전 마지막 봉)
            r["p" + hm] = D[D.hm <= hm].groupby("date").c.last()
        f30 = D[D.hm <= "0930"]; g30 = f30.groupby("date")
        r["vwap30"] = (f30.c * f30.v).groupby(f30.date).sum() / g30.v.sum().replace(0, np.nan)
        r["lo30"] = g30.l.min()
        # 첫 30분 VWAP 아래 지정가: 09:31~10:00 저가가 VWAP 이하로 내려오면 VWAP 에 체결
        f60 = D[(D.hm > "0930") & (D.hm <= "1000")]
        r["lo3060"] = f60.groupby("date").l.min()
        r["ticker"] = Path(f).stem
        out.append(r.reset_index())
    return pd.concat(out, ignore_index=True)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    t0 = time.time()
    import oc_day as O
    A, feats = O.build("KR")
    A["q_gap"] = A.groupby("date").gap.rank(pct=True); A["q_vm"] = A.groupby("date").vm.rank(pct=True)
    A["cand"] = (A.q_gap <= 0.10) & (A.q_vm <= 0.30)
    M = day_points("KR")
    J = M.merge(A[["ticker", "date", "cand", "open", "close", "gap"]], on=["ticker", "date"], how="inner")
    P("# B — 1분봉으로 본 '갭 하락 데이'(국장) · %s" % time.strftime("%Y-%m-%d")); P("")
    P("- 1분봉 종목 %d · 종목-일 %s · %s~%s · 그중 후보 %d건(%d일)" % (M.ticker.nunique(), f"{len(J):,}", J.date.min(), J.date.max(), J.cand.sum(), J[J.cand].date.nunique()))
    P("- 1분봉 시가 ↔ 일봉 시가 0.5%% 안 일치 %.1f%% (A 와 같은 가격인지)" % (((J.o / J.open - 1).abs() < 0.005).mean() * 100)); P("")
    ent = [("시가", "o", 0.0), ("09:05", "p0905", 0.05), ("09:10", "p0910", 0.05), ("09:30", "p0930", 0.05)]
    ext = [("종가", "c", 0.0), ("11:00", "p1100", 0.05), ("13:00", "p1300", 0.05), ("15:00", "p1500", 0.05)]
    rows = []
    for grp, S in (("후보", J[J.cand]), ("같은 종목 아무 날", J[~J.cand])):
        for en, ec, es in ent:
            for xn, xc, xs in ext:
                if (xc != "c" and xc[1:] <= ec[1:]) if ec != "o" else False: continue
                r = (S[xc] / S[ec] - 1) * 100 - 0.22 - es - xs
                r = r.replace([np.inf, -np.inf], np.nan).dropna()
                if len(r) < 20: continue
                d = r.groupby(S.loc[r.index, "date"]).mean()
                yr = r.groupby(S.loc[r.index, "date"].str[:4]).mean()
                rows.append((grp, en, xn, len(r), r.mean(), (r > 0).mean() * 100, d.mean() / (d.std() / np.sqrt(len(d))) if len(d) > 2 else np.nan, (yr > 0).sum(), len(yr)))
        # VWAP 지정가
        hit = S.lo3060 <= S.vwap30
        r = ((S.c / S.vwap30 - 1) * 100 - 0.22 - 0.02)[hit].dropna()
        if len(r) >= 20:
            yr = r.groupby(S.loc[r.index, "date"].str[:4]).mean()
            rows.append((grp, "VWAP 아래 지정가(체결 %.0f%%)" % (hit.mean() * 100), "종가", len(r), r.mean(), (r > 0).mean() * 100, np.nan, (yr > 0).sum(), len(yr)))
    P("| 무리 | 사는 때 | 파는 때 | 건수 | 평균(비용 뒤) | 승률 | t(일별) | 플러스 해 |"); P("|---|---|---|---|---|---|---|---|")
    for g_, en, xn, n, m, w, t, yp, ny in rows:
        P("| %s | %s | %s | %d | %+.3f%% | %.0f%% | %s | %d/%d |" % (g_, en, xn, n, m, w, ("%.1f" % t) if t == t else "-", yp, ny))
    P(""); P("(%.1f분)" % ((time.time() - t0) / 60))
    pd.to_pickle(rows, ROOT / "cache" / "m1_lab_gapday.pkl")
    from verdict import log_trials
    log_trials("m1_gapday_%s" % time.strftime("%Y%m%d"), len(rows))
    (ROOT / "reports" / ("m1_gapday_%s.md" % time.strftime("%Y%m%d"))).write_text("\n".join(OUT) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
