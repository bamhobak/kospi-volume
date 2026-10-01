# -*- coding: utf-8 -*-
"""후보 2개 더 조이기 — 승률·수익 올리는 거르개 (2026-10-02 사용자 요청).

A 자사주 신탁계약 + 낙폭(H0271): 기반 = 신탁 공시 & 20일 -10% 이하(표본 넉넉) · 다음날 시가 · 보유 10·20일
   재료 = 신호일 패널 숫자 열 전부 + 계약 규모(시총 대비 %) + 계약기간(일) + 1년 안 첫 신탁인가 + 코스피 60일선 위/아래
B S&P 500 편출(H0263): 기반 = 편출 뒤 30거래일↑ 거래된 종목 · 편출 +21일 진입 · 보유 40·60일
   재료 = 편출 전 60일 낙폭 · 진입 시점 20일 등락 · 시총 · 주가 · 거래대금 · S&P 60일선 위/아래
판정: 거르개(학습 분위 33·50·67% 문턱 · 이상/이하)마다 학습(16~22)·검증(23~) 중앙·승률, 2020 뺀 중앙,
  같은 건수 무작위 선택 대비 z(평균 기준). 둘 다 중앙·승률이 오르고 z≥1.5 인 것만 '후보', 그 후보끼리 두 개 조합도 본다.

    python research/tighten2.py A B
"""
import sqlite3, sys, time, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(BASE)); sys.path.insert(0, str(ROOT))
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))
f2 = lambda v: "%+.2f" % v if v == v else "-"
TR = ("20160101", "20221231"); VA = ("20230101", "20991231")


def per(df, a, b):
    return df[(df.date >= a) & (df.date <= b)]


def zsc(r_all, keep):
    r_all = np.asarray(r_all, float); keep = np.asarray(keep, bool)
    n, k = len(r_all), keep.sum()
    if k < 15 or n - k < 5:
        return np.nan
    se = r_all.std() * np.sqrt(1 / k * (n - k) / (n - 1))
    return (r_all[keep].mean() - r_all.mean()) / se if se > 0 else np.nan


def row(lab, z, base=None):
    tr, va = per(z, *TR), per(z, *VA)
    no20 = z[(z.date >= TR[0]) & ~z.date.str.startswith("2020")]
    ys = z[z.date >= TR[0]].groupby(z.date.str[:4]).r.median()
    yrs = (z.date >= TR[0]).sum() / 10.75
    return dict(lab=lab, n=len(z[z.date >= TR[0]]), py=yrs, trn=len(tr), trm=tr.r.median(), trw=(tr.r > 0).mean() * 100 if len(tr) else np.nan,
                van=len(va), vam=va.r.median(), vaw=(va.r > 0).mean() * 100 if len(va) else np.nan, vamean=va.r.mean(),
                no20=no20.r.median(), ypos=int((ys > 0).sum()), ny=len(ys))


def table(rows, title):
    P("### " + title); P("")
    P("| 조건 | 건수(16~) · 연 | 학습 중앙 · 승률 | 검증 중앙 · 승률 · 평균 | 2020 뺀 중앙 | 중앙 플러스 해 | z 학·검 |"); P("|---|---|---|---|---|---|---|")
    for x in rows:
        P("| %s | %d · %.0f | %s · %.0f%% | %s · %.0f%% · %s | %s | %d/%d | %s |" % (
            x["lab"], x["n"], x["py"], f2(x["trm"]), x["trw"], f2(x["vam"]), x["vaw"], f2(x["vamean"]), f2(x["no20"]), x["ypos"], x["ny"],
            x.get("zz", "")))
    P("")


def scan(Z, feats, title, hold_col="r"):
    """Z: 기반 신호 표(date, r, 재료…) → 단일 거르개 스캔 → 후보 → 두 개 조합"""
    trm = per(Z, *TR); vam = per(Z, *VA)
    base = row("기반(거르개 없음)", Z)
    cands = []
    for f in feats:
        x = Z[f].astype(float)
        xt = x[(Z.date >= TR[0]) & (Z.date <= TR[1])]
        if xt.notna().sum() < 40 or xt.nunique() < 3:
            continue
        for q in (0.33, 0.5, 0.67):
            th = xt.quantile(q)
            for op in (">=", "<="):
                keep = (x >= th) if op == ">=" else (x <= th)
                keep = keep.fillna(False)
                sub = Z[keep]
                if len(per(sub, *TR)) < 30 or len(per(sub, *VA)) < 15:
                    continue
                rr = row("%s %s %.3g" % (f, "≥" if op == ">=" else "≤", th), sub)
                ztr = zsc(trm.r, keep[trm.index]); zva = zsc(vam.r, keep[vam.index])
                rr["zt"], rr["zv"] = ztr, zva
                rr["zz"] = "%.1f · %.1f" % (ztr, zva)
                rr["keep"] = keep
                ok = (rr["trm"] > base["trm"] and rr["vam"] > base["vam"] and rr["trw"] > base["trw"] and rr["vaw"] > base["vaw"]
                      and ztr >= 1.5 and zva >= 1.5)
                if ok:
                    cands.append(rr)
    cands.sort(key=lambda r: -(r["zt"] + r["zv"]))
    # 재료 하나에 한 칸만(가장 강한 것)
    seen, top = set(), []
    for c in cands:
        f = c["lab"].split(" ")[0]
        if f not in seen:
            seen.add(f); top.append(c)
    table([base] + top[:12], title + " — 단일 거르개(학습·검증 둘 다 중앙·승률↑, z≥1.5)")
    combos = []
    for i in range(min(len(top), 8)):
        for j in range(i + 1, min(len(top), 8)):
            keep = top[i]["keep"] & top[j]["keep"]
            sub = Z[keep]
            if len(per(sub, *TR)) < 25 or len(per(sub, *VA)) < 12:
                continue
            rr = row(top[i]["lab"] + " & " + top[j]["lab"], sub)
            rr["zt"] = zsc(trm.r, keep[trm.index]); rr["zv"] = zsc(vam.r, keep[vam.index])
            rr["zz"] = "%.1f · %.1f" % (rr["zt"], rr["zv"])
            combos.append(rr)
    combos.sort(key=lambda r: -(min(r["trw"], r["vaw"])))
    if combos:
        table(combos[:10], title + " — 두 개 조합(학습·검증 승률 중 낮은 쪽 순)")
    return base, top, combos


def part_a():
    import event_lab as E
    L = E.Lab(); A = L.A
    c = sqlite3.connect("file:" + str(BASE / "data" / "dart" / "disclosures.db") + "?mode=ro", uri=True)
    cm = dict(c.execute("select corp_code, max(stock_code) from disclosure where stock_code!='' group by corp_code").fetchall())
    B = pd.read_pickle(ROOT / "cache" / "buyback_kr.pkl").dropna(subset=["rcept_no"])
    B = B[B._api == "tsstkAqTrctrCnsDecsn"].copy()
    B["date"] = B.rcept_no.str[:8]; B["ticker"] = B.corp_code.map(cm)
    B = B.dropna(subset=["ticker"]).drop_duplicates(["ticker", "date"]).sort_values("date")
    num = lambda s: pd.to_numeric(str(s).replace(",", ""), errors="coerce")
    B["amt"] = B.ctr_prc.map(num)
    def days(a, b):
        try:
            import re
            f = lambda s: pd.Timestamp(re.sub(r"[^0-9]", "", s)[:8])
            return (f(b) - f(a)).days
        except Exception:
            return np.nan
    B["ctrdays"] = [days(a, b) for a, b in zip(B.get("ctr_pd_bgd", ""), B.get("ctr_pd_edd", ""))]
    prev = B.groupby("ticker").date.shift(1)
    B["first1y"] = [(1.0 if (p != p or (pd.Timestamp(d) - pd.Timestamp(p)).days > 365) else 0.0) for d, p in zip(B.date, prev)]
    B["sd"] = [L.shift(d, 0) for d in B.date]
    B = B.dropna(subset=["sd"])
    import FinanceDataReader as fdr
    k = fdr.DataReader("KS11", "2014-01-01"); k = k[k.Close > 0]
    up = dict(zip(k.index.strftime("%Y%m%d"), (k.Close > k.Close.rolling(60).mean()).astype(float)))
    ret1 = (A.close / A.groupby("ticker", sort=False).close.shift(1) - 1) * 100
    A["ret1"] = ret1
    num_cols = [c for c in A.columns if c not in ("ticker", "date", "buy", "cost", "up", "u", "mk", "pref", "_di", "jw")
                and not c.startswith("n") and pd.api.types.is_numeric_dtype(A[c]) and A[c].dtype != bool]
    feat = A[["ticker", "date"] + num_cols]
    F = B[["ticker", "sd", "date", "amt", "ctrdays", "first1y"]].rename(columns={"date": "rdate"}).merge(
        feat, left_on=["ticker", "sd"], right_on=["ticker", "date"], how="left")
    F["size"] = F.amt / F.marcap * 100
    F["kup"] = F.sd.map(up)
    P("## A 자사주 신탁계약 + 낙폭"); P("")
    out = {}
    for h in (10, 20):
        Fb = F[F.ret20 <= -10].copy()
        L.cells.clear()
        L.cell("A", "b", list(zip(Fb.ticker, Fb.rdate)), 0, h)
        Y = L.cells[-1]["Y"][["date", "ticker", "r"]]
        Z = Y.merge(Fb.drop(columns=["date"]).rename(columns={"sd": "date"}), on=["ticker", "date"], how="left")
        Z = Z.drop_duplicates(["ticker", "date"]).reset_index(drop=True)
        feats = [c for c in Z.columns if c not in ("date", "ticker", "r", "rdate", "amt")]
        out[h] = scan(Z, feats, "A · 보유 %d일 · 기반 20일 -10%%↓" % h)
        # 지금 추천(-15%)도 같은 표로
        rr = [row("20일 -10%↓ (기반)", Z), row("20일 -15%↓ (지난번 조정)", Z[Z.ret20 <= -15]), row("20일 -20%↓", Z[Z.ret20 <= -20])]
        table(rr, "A · 보유 %d일 · 낙폭 문턱만" % h)
    return out


def part_b():
    K = pd.read_pickle(BASE / "data" / "us_full_2007.pkl")[["ticker", "date", "px", "buy", "cost", "amt20", "rawclose", "marcap", "ret20"]]
    K = K.sort_values(["ticker", "date"]).reset_index(drop=True)
    g = K.groupby("ticker", sort=False).px
    for h in (40, 60):
        K["n%d" % h] = (g.shift(-h) / K.buy - 1) * 100 - K.cost
    K["dd60"] = (K.px / g.transform(lambda s: s.rolling(60, min_periods=40).max()) - 1) * 100
    K["r20b"] = (K.px / g.shift(20) - 1) * 100
    cal = np.array(sorted(K.date.unique()))
    pos = {k: i for i, k in enumerate(K.ticker + "|" + K.date)}
    dates_of = K.groupby("ticker").date.apply(np.array)
    import FinanceDataReader as fdr
    ix = fdr.DataReader("US500", "2007-01-01"); ix = ix[ix.Close > 0]
    spup = dict(zip(ix.index.strftime("%Y%m%d"), (ix.Close > ix.Close.rolling(60).mean()).astype(float)))
    T = pd.read_csv(BASE / "data" / "us" / "sp500" / "ticker_start_end.csv", dtype=str).dropna(subset=["end_date"])
    T["e"] = T.end_date.str.replace("-", ""); T = T[T.e >= "20080101"]
    ev = []
    for t, e in zip(T.ticker, T.e):
        tt = t if t in dates_of.index else t.replace(".", "-")
        if tt in dates_of.index and (dates_of[tt] > e).sum() >= 30:
            ev.append((tt, e))
    P("## B S&P 500 편출"); P("")
    for h in (40, 60):
        rows = []
        for t, e in ev:
            i = np.searchsorted(cal, e, "left") + 21
            if i >= len(cal):
                continue
            ix0 = pos.get(t + "|" + e); ix1 = pos.get(t + "|" + cal[i])
            if ix1 is None or ix0 is None:
                continue
            r = K["n%d" % h].values[ix1]
            if r != r:
                continue
            rows.append(dict(date=cal[i], ticker=t, r=r, dd60_pre=K.dd60.values[ix0], ret_pre20=K.r20b.values[ix0],
                             ret_since=(K.px.values[ix1] / K.px.values[ix0] - 1) * 100, marcap=K.marcap.values[ix1],
                             price=K.rawclose.values[ix1], amt20=K.amt20.values[ix1], spup=spup.get(cal[i], np.nan)))
        Z = pd.DataFrame(rows)
        feats = ["dd60_pre", "ret_pre20", "ret_since", "marcap", "price", "amt20", "spup"]
        scan(Z, feats, "B · 편출 +21일 · 보유 %d일" % h)
        rr = [row("기반", Z), row("편출 전 60일 -30%↓", Z[Z.dd60_pre <= -30]), row("편출 전 60일 -15%↓", Z[Z.dd60_pre <= -15]),
              row("편출 뒤 21일 동안 안 오름(≤0%)", Z[Z.ret_since <= 0]), row("S&P 60일선 위", Z[Z.spup == 1])]
        table(rr, "B · 보유 %d일 · 미리 정한 조건" % h)


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    pick = set(argv) or {"A", "B"}
    P("# 후보 2개 더 조이기 · %s" % time.strftime("%Y-%m-%d")); P("")
    if "A" in pick: part_a()
    if "B" in pick: part_b()
    (ROOT / "reports" / ("tighten2_%s.md" % time.strftime("%Y%m%d"))).write_text("\n".join(OUT) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1:])
