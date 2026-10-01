# -*- coding: utf-8 -*-
"""사건 실험실 — 사용자 제안 12개 중 국내 사건형 6개를 한 잣대로 (2026-10-02, "이거 다 해봐").

  1 인적분할 재상장(분사주 국내판)     — research/cache/kr_spinoff_list.csv(분할 공시 + 이름 줄기 + 첫 거래일) − 공모 오탐
  3 물량 폭탄 뒤(추가상장·전환청구·합병 신주) — 공시 제목
  4 거래정지 해제·관리종목 해제         — 공시 제목(일상 해제와 사건 해제를 나눔)
  5 공모주 보호예수 해제(1·3·6·12개월)  — 상장일 + 21·63·126·250거래일 (공모 = 패널 첫날이 상장일과 같은 종목)
  6 공시 42유형 '지연 진입'            — disc_scan TYPES 그대로, 진입을 공시 + 5·10·21·40거래일로
  8 대량보유 신규 보고자(행동주의·국민연금) — 그 보고자의 그 종목 첫 보고
진입 = 사건일(+k거래일)의 다음날 시가 · 보유 H거래일 종가 · 비용 차감 · 한 종목 보유 중 재사건 무시
잣대: 같은 날(진입일) 유니버스(거래대금 상위 40%) 중앙 대비 초과. 구간 옛날 05~15 / 학습 16~22 / 검증 23~.
통과 = 학습·검증 둘 다 중앙 수익 > 0 & 초과 중앙 > 0 & 2016~ 월별 초과 평균의 t ≥ **본페로니 문턱(전체 칸 수)** & 양수 해 60%↑
  & (옛날 표본이 있으면) 옛날 초과 ≥ 0. 사건 종목은 작아 유니버스 밖이 많아 사건 쪽은 유니버스로 거르지 않는다(거래대금 20일 평균 3억↑만).

    python research/event_lab.py              # 전부
    python research/event_lab.py 1 5          # 골라서
"""
import re, sqlite3, sys, time, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd
from scipy.stats import norm

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(BASE)); sys.path.insert(0, str(ROOT))
import run_spec as R
from verdict import log_trials

OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))
PER = [("옛날", "20050101", "20151231"), ("학습", "20160101", "20221231"), ("검증", "20230101", "20991231")]


def log(m):
    print("%s %s" % (time.strftime("%H:%M:%S"), m), file=sys.stderr, flush=True)


class Lab:
    def __init__(self):
        A, uni, _ = R.load_market("KR")
        A = A.sort_values(["ticker", "date"]).reset_index(drop=True)
        uni = A.amt20.groupby(A.date).rank(pct=True) >= 0.6
        g = A.groupby("ticker", sort=False).close
        for h in (120, 250):
            A["n%d" % h] = (g.shift(-h) / A.buy - 1) * 100 - A.cost
        self.A = A
        self.cal = np.array(sorted(A.date.unique())); self.ci = {d: i for i, d in enumerate(self.cal)}
        self.key = (A.ticker + "|" + A.date).values
        self.pos = {k: i for i, k in enumerate(self.key)}
        self.ok = (A.amt20 >= 3).values                       # 거래대금 20일 평균 3억↑ (사건 종목 최소 유동성)
        self.bench = {}
        for h in (20, 60, 120, 250):
            c = "n%d" % h
            self.bench[h] = A[uni].dropna(subset=[c]).groupby("date")[c].median()
        self.cells = []

    def shift(self, d, k):
        """d(YYYYMMDD) 이후(같은 날 포함) 첫 거래일에서 k거래일 뒤"""
        i = np.searchsorted(self.cal, d, "left") + k
        return self.cal[i] if 0 <= i < len(self.cal) else None

    def cell(self, group, name, events, k, h, needliq=True):
        """events: [(ticker, 사건일)] → 진입일 = 사건일 + k거래일(신호일) → 다음날 시가 매수 · h일"""
        c = "n%d" % h
        A = self.A
        rows = []
        for t, d in events:
            sd = self.shift(d, k)
            if sd is None:
                continue
            ix = self.pos.get(t + "|" + sd)
            if ix is None:
                continue
            if needliq and not self.ok[ix]:
                continue
            r = A[c].values[ix]
            if r == r:
                rows.append((sd, t, r))
        Y = pd.DataFrame(rows, columns=["date", "ticker", "r"]).sort_values("date")
        # 한 종목 보유 중 재사건 무시
        keep, last = [], {}
        for j, (d, t) in enumerate(zip(Y.date.values, Y.ticker.values)):
            i = self.ci[d]
            if last.get(t, -10 ** 9) >= i:
                continue
            last[t] = i + h; keep.append(j)
        Y = Y.iloc[keep].copy()
        Y["ex"] = Y.r - Y.date.map(self.bench[h])
        self.cells.append(dict(group=group, name=name, k=k, h=h, Y=Y))

    def judge(self):
        M = len(self.cells)
        zc = norm.ppf(1 - 0.05 / M)
        res = []
        for c in self.cells:
            Y = c["Y"]; rec = dict(group=c["group"], name=c["name"], k=c["k"], h=c["h"], n=len(Y))
            for i, (lab, a, b) in enumerate(PER):
                z = Y[(Y.date >= a) & (Y.date <= b)]
                rec["n%d" % i] = len(z)
                if len(z) >= 15:
                    rec["med%d" % i] = z.r.median(); rec["mean%d" % i] = z.r.mean()
                    rec["ex%d" % i] = z.ex.median(); rec["win%d" % i] = (z.r > 0).mean() * 100
                else:
                    for f in ("med", "mean", "ex", "win"):
                        rec["%s%d" % (f, i)] = np.nan
            z = Y[Y.date >= "20160101"].dropna(subset=["ex"])
            m = z.groupby(z.date.str[:6]).ex.mean()
            rec["t"] = m.mean() / (m.std() / np.sqrt(len(m))) if len(m) >= 12 and m.std() > 0 else np.nan
            ys = Y.groupby(Y.date.str[:4]).r.mean()
            rec["ypos"], rec["ny"] = int((ys > 0).sum()), len(ys)
            ok = (rec["med1"] > 0 and rec["med2"] > 0 and rec["ex1"] > 0 and rec["ex2"] > 0 and rec["t"] >= zc
                  and rec["ypos"] >= 0.6 * rec["ny"] and not (rec["n0"] >= 15 and rec["ex0"] < 0))
            rec["pass"] = bool(ok)
            rec["near"] = bool(rec["med1"] > 0 and rec["med2"] > 0 and rec["ex1"] > 0 and rec["ex2"] > 0 and rec["t"] >= 2)
            res.append(rec)
        return pd.DataFrame(res), zc


def disclosures():
    c = sqlite3.connect("file:" + str(BASE / "data" / "dart" / "disclosures.db") + "?mode=ro", uri=True)
    D = pd.read_sql("select stock_code, rcept_dt, report_nm, flr_nm, corp_name from disclosure where stock_code is not null and stock_code != ''", c)
    D = D[~D.report_nm.str.contains(r"\[[^\]]*정정\]|\[발행조건확정\]", regex=True)]
    D["t"] = D.report_nm.str.replace(r"\[[^\]]*\]", "", regex=True).str.replace(" ", "", regex=False)
    return D


def ev(df):
    return list(zip(df.stock_code.values, df.rcept_dt.values))


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    pick = set(a for a in argv if a.isdigit()) or {"1", "3", "4", "5", "6", "8"}
    t0 = time.time()
    L = Lab(); log("패널 준비")
    D = disclosures(); log("공시 %s건" % f"{len(D):,}")
    if "1" in pick:
        S = pd.read_csv(ROOT / "cache" / "kr_spinoff_list.csv", dtype=str)
        bad = {"207940", "323410", "484590", "475580", "495900", "200470", "224110", "192650", "034730", "175250",
               "137310", "357880", "047400", "103230", "089150", "094860", "041460", "143160"}
        S = S[~S.new.isin(bad)]
        evs = list(zip(S.new.values, S["first"].values))
        log("1 인적분할 재상장 %d건" % len(evs))
        for k in (0, 5, 10, 21, 40):
            for h in (60, 120, 250):
                L.cell("1 인적분할 재상장", "재상장일", evs, k, h, needliq=False)
    if "3" in pick:
        for nm, rx in (("추가상장", r"^추가상장"), ("전환청구권 행사", r"전환청구권행사"), ("합병 신주(합병 종료 보고)", r"합병등종료보고서\(합병\)")):
            e = ev(D[D.t.str.contains(rx, regex=True)])
            log("3 %s %d건" % (nm, len(e)))
            for k in (5, 10, 21, 40):
                for h in (20, 60):
                    L.cell("3 물량 폭탄 뒤", nm, e, k, h)
    if "4" in pick:
        x = D[D.t.str.contains(r"주권매매거래정지해제", regex=True)]
        routine = x.t.str.contains(r"분할|병합|변경상장|무상증자|구주권|액면")
        for nm, e in (("거래정지 해제(사건성)", ev(x[~routine])), ("거래정지 해제(일상 — 분할·병합 등)", ev(x[routine])),
                      ("관리종목 해제", ev(D[D.t.str.contains(r"^관리종목해제|관리종목지정사유일부해제|관리종목지정해제", regex=True)]))):
            log("4 %s %d건" % (nm, len(e)))
            for k in (0, 5, 10, 21):
                for h in (20, 60):
                    L.cell("4 정지·관리 해제", nm, e, k, h)
    if "5" in pick:
        import features as FT
        ld = FT.listing_dates()
        first = L.A.groupby("ticker").date.min()
        spin = set(pd.read_csv(ROOT / "cache" / "kr_spinoff_list.csv", dtype=str).new)
        ipo = []
        for t, f in first.items():
            d = ld.get(t)
            if d and f > "20050301" and t not in spin and t[-1] == "0":
                i0 = np.searchsorted(L.cal, d); i1 = np.searchsorted(L.cal, f)
                if abs(int(i1) - int(i0)) <= 3:
                    ipo.append((t, f))
        log("5 공모 상장 %d건" % len(ipo))
        for lab, lag in (("1개월", 21), ("3개월", 63), ("6개월", 126), ("12개월", 250)):
            e = [(t, L.shift(f, lag)) for t, f in ipo]
            e = [(t, d) for t, d in e if d]
            for k in (-10, 0, 5, 10):
                for h in (20, 60):
                    L.cell("5 보호예수 해제", "상장 %s(해제일 %+d일)" % (lab, k), [(t, L.shift(d, k) if k < 0 else d) for t, d in e], max(k, 0), h)
    if "6" in pick:
        import disc_scan as DS
        for nm, rx in DS.TYPES:
            e = ev(D[D.t.str.contains(rx, regex=True)])
            for k in (5, 10, 21, 40):
                for h in (20, 60):
                    L.cell("6 공시 지연 진입", nm, e, k, h)
        log("6 끝")
    if "8" in pick:
        B = D[D.t.str.contains("주식등의대량보유상황보고서")].sort_values("rcept_dt")
        B = B.drop_duplicates(["flr_nm", "stock_code"], keep="first")              # 그 보고자의 그 종목 첫 보고
        B = B[B.flr_nm != B.corp_name]
        act = r"얼라인|케이씨지아이|KCGI|트러스톤|안다자산|플래쉬라이트|차파트너스|머스트자산|라이프자산|밸류파트너스|시티오브런던|City of London|브이아이피자산|VIP자산|돌핀|에셋플러스"
        groups = (("행동주의·가치 운용사", B[B.flr_nm.str.contains(act, regex=True)]),
                  ("국민연금", B[B.flr_nm.str.contains("국민연금")]),
                  ("모든 보고자(기준)", B))
        for nm, x in groups:
            e = ev(x); log("8 %s %d건" % (nm, len(e)))
            for k in (0, 5, 21):
                for h in (60, 120, 250):
                    L.cell("8 대량보유 신규", nm, e, k, h)
    G, zc = L.judge()
    G.to_pickle(ROOT / "cache" / "event_lab.pkl")
    P("# 사건 실험실 · %s" % time.strftime("%Y-%m-%d")); P("")
    P("칸 %d개 · 통과 문턱 t ≥ %.2f(본페로니) · 통과 %d칸 · 근접(t≥2·학습·검증 플러스) %d칸" % (len(G), zc, G["pass"].sum(), G.near.sum())); P("")
    for grp, g in G.groupby("group", sort=False):
        P("## %s" % grp); P("")
        P("| 사건 | 진입 | 보유 | 건수(옛·학·검) | 옛날 중앙·초과 | 학습 중앙·초과·승률 | 검증 중앙·초과·승률 | t | 양수 해 | 판정 |"); P("|---|---|---|---|---|---|---|---|---|---|")
        g = g.sort_values("t", ascending=False)
        show = pd.concat([g[g["pass"] | g.near], g.head(6)]).drop_duplicates(subset=["name", "k", "h"]).head(14)
        f = lambda v: "%+.2f" % v if v == v else "-"
        for _, x in show.iterrows():
            P("| %s | +%d일 | %d일 | %d·%d·%d | %s · %s | %s · %s · %s | %s · %s · %s | %s | %d/%d | %s |" % (
                x["name"], x.k, x.h, x.n0, x.n1, x.n2, f(x.med0), f(x.ex0), f(x.med1), f(x.ex1), ("%.0f%%" % x.win1) if x.win1 == x.win1 else "-",
                f(x.med2), f(x.ex2), ("%.0f%%" % x.win2) if x.win2 == x.win2 else "-", ("%.1f" % x.t) if x.t == x.t else "-", x.ypos, x.ny,
                "✅ 통과" if x["pass"] else ("△ 근접" if x.near else "")))
        P("")
    P("(%.0f분)" % ((time.time() - t0) / 60))
    log_trials("event_lab_%s" % time.strftime("%Y%m%d"), len(G))
    (ROOT / "reports" / ("event_lab_%s.md" % time.strftime("%Y%m%d"))).write_text("\n".join(OUT) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1:])
