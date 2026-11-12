# -*- coding: utf-8 -*-
"""H0413 후속 — 담보 계약·유상증자(용도별)를 지금 스윙·데이 규칙 거래 안에서 회피 거르개로 (전 종목 회피 신호가 규칙 안에서도 듣나).
신호 날 기준 앞 60거래일(변형 20·120) 안에 공시가 있었으면 '걸림'. 스윙 = C:/temp/kp/kind/swing.pkl, 데이 T1 = t1.pkl.
    python research/disc2_1112.py → research/reports/disc2_1112.md
"""
import os, sys, pickle, sqlite3, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
os.chdir(BASE); sys.path[:0] = [str(ROOT), str(ROOT / "factory"), str(BASE)]
sys.stdout.reconfigure(encoding="utf-8")
from verdict import log_trials
KD = Path("C:/temp/kp/kind")
c = sqlite3.connect(BASE / "data" / "dart" / "kind_time.db")
K = pd.read_sql("select day, kcode, title from kind where market in ('유가증권','코스닥') and (title like '%담보제공%계약%' or title like '%유상증자%결정%')", c); c.close()
K = K[~K.title.str.contains("정정")]
K["ticker"] = K.kcode.astype(str) + "0"
K["kind"] = np.where(K.title.str.contains("담보"), "담보", "유증")
Z = pd.read_pickle("C:/temp/kp/disc/piic.pkl").drop_duplicates("rcept_no") if Path("C:/temp/kp/disc/piic.pkl").exists() else None
EV = {k: g.groupby("ticker").day.apply(lambda s: np.array(sorted(s))).to_dict() for k, g in K.groupby("kind")}
cal = pickle.load(open(KD / "t1.pkl", "rb"))["cal"]; cal = np.array(cal)


def flag(T, kind, win):
    D = EV[kind]; out = np.zeros(len(T), bool)
    for i, (t, d) in enumerate(zip(T.ticker.values, T.date.values)):
        a = D.get(str(t).zfill(6))
        if a is None: continue
        j = np.searchsorted(cal, d); lo = cal[max(j - win, 0)]
        k = np.searchsorted(a, d, side="right")
        out[i] = k > 0 and a[k - 1] >= lo
    return out


def cell(z):
    if len(z) < 8: return "%d건" % len(z)
    return "%d건 **%+.2f** (중앙 %+.2f)" % (len(z), z.r.mean(), z.r.median())


OUT = []; P = lambda s="": (OUT.append(s), print(s, flush=True)); n = 0
P("# 담보 계약·유상증자 공시 — 지금 규칙 거래 안 회피 거르개 (H0413 후속) · 2026-11-12"); P("")
P("신호 날 앞 N거래일 안에 KIND 공시(2016~)가 있으면 '걸림'. 칸 = 건수 **건당**(중앙). 학습 2016~22 / 검증 2023~"); P("")
sw = pickle.load(open(KD / "swing.pkl", "rb"))
T1 = pickle.load(open(KD / "t1.pkl", "rb"))["T"]
sets = [(v["disp"] + " " + v["name"], v["T"]) for v in sw.values()] + [("T1 [갭 하락 조용주](데이)", T1)]
P("| 규칙 | 공시 | 창 | 걸림 학습 | 안 걸림 학습 | 걸림 검증 | 안 걸림 검증 |"); P("|---|---|---|---|---|---|---|")
for nm, T in sets:
    T = T[T.date >= "20160101"].copy(); T["ticker"] = T.ticker.astype(str).str.zfill(6)
    if len(T) < 30: continue
    for kind in ("담보", "유증"):
        for win in (20, 60, 120):
            if win != 60 and kind == "유증": continue
            f = flag(T, kind, win)
            tr, te = T.date < "20230101", T.date >= "20230101"
            P("| %s | %s | %d일 | %s | %s | %s | %s |" % (nm, kind, win, cell(T[tr & f]), cell(T[tr & ~f]), cell(T[te & f]), cell(T[te & ~f]))); n += 4
(ROOT / "reports" / "disc2_1112.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
log_trials("disc2_1112", n)
