# -*- coding: utf-8 -*-
"""1억 1년 — 재료 넓혀 새로 찾기(2026-11-05 사용자 "1 2번 해봐" 중 1번).
y2_search 와 같은 규율에 새 재료를 더한다(전부 '어제까지' 아는 값):
  수급(investor.db flow11, 2018~, 원): 외인·기관(금투+보험+투신+사모+은행+기타금융+연기금)·연기금·투신·사모·개인 1·5·20일 순매수 ÷ 20일 평균 거래대금 %
  공매도(krx_daily): 거래 비중 어제·5일 평균 · 잔고 비율(3거래일 늦춤, T+2 공개) · 잔고 20일 변화 %(3일 늦춤)
  재무(krx_daily fundamental): PER·PBR·배당수익률 · 적자(EPS≤0) — 그날 KRX 표(어제 값)
  공시(dart disclosures, 접수일 ≤ 어제, 최근 5거래일 안): 공급계약·전환사채/신주인수권·유상증자·실적(잠정)·최대주주변경·무상증자/분할
  조합엔 새 재료가 하나 이상 · 자사주·내부자·외인 장기 매집(외인 20일 위 + 5일↑ 보유)·저PBR+깊은 낙폭 스윙은 기존 계열이라 건너뜀
  플러스 해 기준은 '자료 있는 해의 70%↑'(수급은 2018~)
  ⚠ flow11 은 지금 상장 종목 위주로 받은 것이라(2018 1,854종목 → 지금 2,657) 폐지 종목이 빠져 수급 조건 성적이 좋게 나올 수 있다
    python research/y3_search.py
"""
import sys, sqlite3, itertools
from pathlib import Path
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "factory"))
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
import FinanceDataReader as fdr
import y2_search as Y2

CACHE = BASE / "data" / "y3_hist.pkl"
FLOW = ["frgn", "inst", "pens", "tru", "pef", "indiv"]
NEWC = [f"{k}{w}" for k in FLOW for w in (1, 5, 20)] + ["sv1", "sv5", "sb", "sbc20", "per", "pbr", "div"]
NEWB = ["neg_eps", "ev_contract", "ev_cb", "ev_rights", "ev_earn", "ev_owner", "ev_bonus"]
EV = {"ev_contract": "단일판매|공급계약", "ev_cb": "전환사채|신주인수권부사채|교환사채", "ev_rights": "유상증자", "ev_earn": "영업\\(잠정\\)실적|매출액또는손익구조",
      "ev_owner": "최대주주변경", "ev_bonus": "무상증자|주식분할"}
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))


def build():
    if CACHE.exists(): return pd.read_pickle(CACHE)
    U = Y2.hist()
    days = sorted(U.date.unique()); prev = dict(zip(days[1:], days[:-1])); lag3 = dict(zip(days[3:], days[:-3]))
    key = U[["ticker", "date"]].copy(); key["d1"] = key.date.map(prev); key["d3"] = key.date.map(lag3)
    a8 = U.amt20.astype(float).to_numpy() * 1e8
    # 수급
    con = sqlite3.connect(BASE / "data" / "investor.db")
    Fl = pd.read_sql("SELECT ticker,date,fin,ins,tru,pef,bank,ofin,pens,indiv,frgn FROM flow11 WHERE date>='20171101'", con)
    Fl["inst"] = Fl[["fin", "ins", "tru", "pef", "bank", "ofin", "pens"]].sum(axis=1, min_count=1)
    Fl = Fl.sort_values(["ticker", "date"]); g = Fl.groupby("ticker")
    for k in FLOW:
        for w in (1, 5, 20):
            Fl[f"{k}{w}"] = Fl[k] if w == 1 else g[k].transform(lambda s: s.rolling(w, min_periods=max(1, w * 3 // 5)).sum())
    m = key.merge(Fl[["ticker", "date"] + [f"{k}{w}" for k in FLOW for w in (1, 5, 20)]].rename(columns={"date": "d1"}), on=["ticker", "d1"], how="left")
    for c in [f"{k}{w}" for k in FLOW for w in (1, 5, 20)]: U[c] = (m[c].to_numpy() / a8 * 100).astype("float32")
    # 공매도·재무
    k = sqlite3.connect(BASE / "data" / "krx_daily.db")
    Sv = pd.read_sql("SELECT ticker,date,vol_rto FROM short_volume WHERE date>='20151101'", k).sort_values(["ticker", "date"])
    Sv["sv5"] = Sv.groupby("ticker").vol_rto.transform(lambda s: s.rolling(5, min_periods=3).mean())
    m = key.merge(Sv.rename(columns={"date": "d1", "vol_rto": "sv1"}), on=["ticker", "d1"], how="left")
    U["sv1"], U["sv5"] = m.sv1.to_numpy(), m.sv5.to_numpy()
    Sb = pd.read_sql("SELECT ticker,date,bal_qty,bal_rto FROM short_balance", k).sort_values(["ticker", "date"])
    Sb["sbc20"] = Sb.groupby("ticker").bal_qty.transform(lambda s: (s / s.shift(20) - 1) * 100)
    m = key.merge(Sb.rename(columns={"date": "d3", "bal_rto": "sb"})[["ticker", "d3", "sb", "sbc20"]], on=["ticker", "d3"], how="left")
    U["sb"], U["sbc20"] = m.sb.to_numpy(), m.sbc20.clip(-100, 500).to_numpy()
    Fu = pd.read_sql("SELECT ticker,date,per,pbr,div,eps FROM fundamental WHERE date>='20151101'", k)
    m = key.merge(Fu.rename(columns={"date": "d1"}), on=["ticker", "d1"], how="left")
    U["per"] = m.per.where(m.per > 0).to_numpy(); U["pbr"] = m.pbr.where(m.pbr > 0).to_numpy(); U["div"] = m["div"].to_numpy()
    U["neg_eps"] = (m.eps <= 0).astype("float32").where(m.eps.notna()).to_numpy()
    # 공시(최근 5거래일, 접수일 ≤ 어제)
    D = pd.read_sql("SELECT stock_code AS ticker, rcept_dt AS date, report_nm FROM disclosure WHERE length(stock_code)=6 AND rcept_dt>='20151101'",
                    sqlite3.connect(BASE / "data" / "dart" / "disclosures.db"))
    D["t"] = D.report_nm.str.replace(r"\s+", "", regex=True)
    di = {d: i for i, d in enumerate(days)}
    D["di"] = np.searchsorted(np.array(days), D.date.to_numpy(), side="left")          # 그 날(또는 다음 거래일)
    ui = U.date.map(di).to_numpy()
    for nm, pat in EV.items():
        E = D[D.t.str.contains(pat)][["ticker", "di"]].drop_duplicates()
        flag = np.zeros(len(U), "float32")
        S = {}
        for t, i in zip(E.ticker, E.di): S.setdefault(t, []).append(i)
        for j, (t, i) in enumerate(zip(U.ticker.to_numpy(), ui)):
            L = S.get(t)
            if L and any(1 <= i - x <= 5 for x in L): flag[j] = 1
        U[nm] = flag
    gd = U.groupby("date")
    for f in NEWC: U["q_" + f] = gd[f].rank(pct=True).astype("float32")
    for f in NEWB: U["q_" + f] = U[f]                                     # 0/1 그대로(조건은 '=1')
    U.to_pickle(CACHE); return U


def main():
    U = build()
    Y2.F = Y2.F + NEWC + NEWB
    S = Y2.Scorer(U)
    P("자료 %s줄 · 새 재료 %d개(연속 %d · 0/1 %d)" % (f"{len(U):,}", len(NEWC) + len(NEWB), len(NEWC), len(NEWB)))
    P("공시 칸 비율: " + " · ".join("%s %.2f%%" % (b, U[b].mean() * 100) for b in NEWB if b.startswith("ev")))
    old_score = S.score

    def score(m, mode, per):                                              # 플러스 해 = 자료 있는 해의 70%↑ 로 바꿔 씀
        r = old_score(m, mode, per)
        if r: r["ypos_ok"] = r["ypos"] >= max(2, int(np.ceil(0.7 * r["ny"])))
        return r
    S.score = score
    # 11-05: 값이 잘리거나 몇 개뿐인 재료는 순위를 자르면 동점 때문에 '그날 시장에 그런 종목이 많나' 로 바뀐다(bigd 위 20% 가 2016~19 0건·2020 과열장만)
    DISC = {"bigd", "dn", "up", "align", "engulf", "sweep", "st_up", "lu20", "age"}
    singles_pool = [(f, s, q) for f in NEWC + Y2.F[:49] if f not in DISC for s in ("lo", "hi") for q in (0.1, 0.2, 0.3)] + [(b, "hi", 0.0001) for b in NEWB]
    picks = {}
    for mode in Y2.MODES:
        P("\n## 방식 %s\n" % mode)
        rs = []
        for c in singles_pool:
            r = S.score(S.mask([c]), mode, "L")
            if r and r["nd"] >= 150: rs.append((c, r))
        best = {}
        for c, r in sorted(rs, key=lambda x: -x[1]["dmean"]): best.setdefault(c[0], (c, r))
        new_top = [x for x in sorted(best.values(), key=lambda x: -x[1]["dmean"]) if x[0][0] in NEWC + NEWB][:12]
        old_top = [x for x in sorted(best.values(), key=lambda x: -x[1]["dmean"]) if x[0][0] not in NEWC + NEWB][:8]
        P("새 재료 위 12: " + ", ".join("%s(%+.2f)" % (Y2.txt([c]), r["dmean"]) for c, r in new_top))
        cands = [[c] for c, _ in new_top] + [[a[0], b[0]] for a, b in itertools.combinations(new_top, 2)] \
              + [[a[0], b[0]] for a in new_top for b in old_top] + [[a[0], b[0], c[0]] for a, b, c in itertools.combinations(new_top[:7], 3)]
        rows = []
        for cs in cands:
            m = S.mask(cs); rl = S.score(m, mode, "L")
            if not (rl and rl["t"] >= 2.5 and rl["ypos_ok"] and rl["nd"] >= 150): continue
            rv = S.score(m, mode, "V" + mode)
            ok = bool(rv and rv["avg"] >= 0.5 and rv["t"] >= 2 and rv["med"] > 0 and rv["ypos"] >= 2)
            rows.append((cs, rl, rv, ok))
        P("찾기 통과 %d칸 · 확인 통과 %d칸 (시험 %d칸)" % (len(rows), sum(r[3] for r in rows), len(cands)))
        P("| 조건 | 찾기 건·건당·날 t | 확인 건·건당·승률·중앙·날 평균·t | 통과 |"); P("|---|---|---|---|")
        for cs, rl, rv, ok in sorted(rows, key=lambda x: -(x[2]["dmean"] if x[2] else -9))[:10]:
            P("| %s | %d · %+.2f%% · %.1f | %s | %s |" % (Y2.txt(cs), rl["n"], rl["avg"], rl["t"],
              ("%d · %+.2f%% · %.0f%% · %+.2f · %+.2f · %.1f" % (rv["n"], rv["avg"], rv["win"], rv["med"], rv["dmean"], rv["t"])) if rv else "-", "O" if ok else ""))
        for cs, rl, rv, ok in sorted([r for r in rows if r[3]], key=lambda x: -x[2]["dmean"]):
            why = Y2.existing_like(cs, mode)
            fs = {(f, s) for f, s, q in cs}
            if not why and Y2.MODES[mode] >= 5 and ("frgn20", "hi") in fs: why = "외인 장기 매집 계열"
            if not why and Y2.MODES[mode] >= 5 and ("pbr", "lo") in fs and any(s == "lo" and f in Y2.DEEP for f, s, q in cs): why = "저PBR 낙폭 계열"
            if why: P("· %s — 기존 계열(%s) → 다음" % (Y2.txt(cs), why)); continue
            picks[mode] = (cs, rl, rv); P("**뽑힘: %s**" % Y2.txt(cs)); break
        if mode not in picks: P("뽑힌 것 없음")
    if not picks:
        P("\n확인 통과 0 — 현금"); (ROOT / "y3_search.out").write_text("\n".join(OUT), encoding="utf-8"); return
    imp, fill = Y2.impact()
    share = 1e8 / len(picks); cfg = {}
    P("\n## 한 종목 금액 고르기(2016~2025-10 계좌)\n")
    for mode, (cs, _, _) in picks.items():
        m = S.mask(cs); best = None
        for base in (0.005, 0.01, 0.02, 0.04):
            y = Y2.yearly(Y2.acct(S, m, mode, Y2.LEARN[0], Y2.VALID[1], base, imp, fill, share), share)
            md = np.median(list(y.values()))
            P("· %s 기본 %.1f%%: 해 중앙 %+.1f%% · 최악 %+.1f%% · %s" % (mode, base * 100, md, min(y.values()), " ".join("%s %+.0f" % kv for kv in y.items())))
            if best is None or md > best[0]: best = (md, base)
        cfg[mode] = best[1]
    P("\n## 굴리기 %s~%s (1억 · 고친 것 없음)\n" % Y2.RUN)
    days = S.days[(S.days >= Y2.RUN[0]) & (S.days <= Y2.RUN[1])]
    res = {}
    for isc, lb in ((1.0, "새로 찾은 방법"), (0.5, "— 체결 손해 절반이면"), (0.0, "— 체결 손해 없으면")):
        tot = 0
        for mode, (cs, _, _) in picks.items():
            tot = tot + Y2.acct(S, S.mask(cs), mode, *Y2.RUN, cfg[mode], imp, fill, share, isc).reindex(days).ffill().fillna(share)
        res[lb] = tot
    for sym, k in (("KS11", "코스피 그냥 들고 있기"), ("KQ11", "코스닥 그냥 들고 있기")):
        X = fdr.DataReader(sym, "2025-10-01"); X.index = X.index.strftime("%Y%m%d")
        res["참고: " + k] = (1e8 * X.Close / X.Close[X.index < Y2.RUN[0]].iloc[-1]).reindex(days).ffill()
    P("| 판 | 1년 뒤 | 수익 | 가장 크게 빠진 폭 |"); P("|---|---|---|---|")
    for k_, s in res.items():
        s = s.dropna(); P("| %s | %s원 | %+.1f%% | %.1f%% |" % (k_, f"{s.iloc[-1]:,.0f}", (s.iloc[-1] / 1e8 - 1) * 100, (s / s.cummax() - 1).min() * 100))
    for mode, (cs, _, _) in picks.items():
        r = S.score(S.mask(cs), mode, "R")
        if r: P("굴리기 구간 %s 신호: %d건 · 건당 %+.2f%% · 승률 %.0f%% · 중앙 %+.2f" % (mode, r["n"], r["avg"], r["win"], r["med"]))
    pd.DataFrame(res).to_pickle(BASE / "data" / "y3_paths.pkl")
    (ROOT / "y3_search.out").write_text("\n".join(OUT), encoding="utf-8")


if __name__ == "__main__":
    main()
