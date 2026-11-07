# -*- coding: utf-8 -*-
"""지금 쓰는 스윙 규칙 전부를 '누적 시도 횟수'로 다시 매긴다 — Deflated Sharpe (2026-11-08 사용자 "1번 바로 해보고").

run_spec.py 는 그 가설 안에서 돌린 칸 수로만, 공장 lab.py 는 공장 누적으로만 깎는다.
09-19 이전에 채택된 규칙은 그 문턱을 안 거쳤다 → 지금 data/trials.json 전체(64,827)까지 놓고 다시 본다.
시도들은 서로 비슷한 변형이 많아(이웃 칸) 진짜 독립 시도 수는 훨씬 적다 → N 을 1·100·1천·1만·전체로 바꿔 가며 민감도를 본다.

    python research/dsr_live_1108.py kr     # 국장 거래 목록 → C:/temp/kp/dsr/kr.pkl
    python research/dsr_live_1108.py us     # 미장 거래 목록 → C:/temp/kp/dsr/us.pkl
    python research/dsr_live_1108.py rep    # 표 → research/reports/dsr_live_1108.md
"""
import io, os, sys, math, pickle, warnings, contextlib
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
os.chdir(BASE); sys.path.insert(0, str(BASE)); sys.path.insert(0, str(ROOT))
OUTD = Path("C:/temp/kp/dsr"); OUTD.mkdir(parents=True, exist_ok=True)
cmd = sys.argv[1] if len(sys.argv) > 1 else "rep"


def kr():
    src = (BASE / "stats_2016.py").read_text(encoding="utf-8").split("OUT = {}")[0]
    ns = {"__file__": str(BASE / "stats_2016.py"), "__name__": "x"}
    real = sys.stdout
    sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
    exec(compile(src, "stats_2016.py", "exec"), ns)
    sys.stdout = real; sys.stdout.reconfigure(encoding="utf-8")
    out = {}
    for rid in ns["ORDER"]:
        Z, hold, stop = ns["take"](rid)
        out[rid] = dict(name=ns["NAME"][rid], disp=ns["DISP"][rid], hold=hold,
                        T=pd.DataFrame({"date": Z.date.values, "ret": Z._r.values.astype(float)}))
        print(rid, len(Z), flush=True)
    pickle.dump(out, open(OUTD / "kr.pkl", "wb"))


def us():
    p = ROOT / "us_rules_recheck.py"
    src = p.read_text(encoding="utf-8").split("PER = (")[0]
    ns = {"__file__": str(p), "__name__": "x"}
    exec(compile(src, str(p), "exec"), ns)
    sys.stdout.reconfigure(encoding="utf-8")
    out = {}
    for rid, nm in ns["NAME"].items():
        h = ns["HOLD"][rid]
        Tr = ns["trades"](np.asarray(pd.Series(ns["C"][rid]).fillna(False).values, bool), h).dropna(subset=["ret"])
        out[rid] = dict(name=nm, disp=rid, hold=h, T=Tr[["date", "ret"]].reset_index(drop=True))
        print(rid, len(Tr), flush=True)
    pickle.dump(out, open(OUTD / "us.pkl", "wb"))


def rep():
    from verdict import deflated_sharpe, trial_count, _load
    NT = trial_count()
    NTOP = len(_load()["by_topic"])
    NS = [1, 100, NTOP, 1000, NT]
    PER = (("홀드아웃 05~15", "20050101", "20151231"), ("학습 16~22", "20160101", "20221231"),
           ("검증 23~", "20230101", "20991231"), ("전체 16~", "20160101", "20991231"))
    L = ["# 지금 규칙 다중검정 재판정 — Deflated Sharpe · 2026-11-08", "",
         "- 월별 수익 = 그달 신호 난 거래 평균(run_spec 과 같은 잣대) · 신호 없는 달은 빠짐 · 비용 뒤",
         "- DSR = '시도를 N번 했을 때 운으로 나올 최고 샤프'보다 이 규칙 샤프가 높을 확률. N=1 이면 그냥 '샤프 > 0 일 확률'",
         "- 누적 시도 %s번(data/trials.json) — 이웃 변형이 많아 독립 시도는 훨씬 적다" % format(NT, ","), ""]
    rows = []
    for mk in ("kr", "us"):
        f = OUTD / ("%s.pkl" % mk)
        if not f.exists(): continue
        D = pickle.load(open(f, "rb"))
        D["ALL"] = dict(name="%s 규칙 전부 합침" % ("국장" if mk == "kr" else "미장"), disp="합", hold=0,
                        T=pd.concat([R["T"] for R in D.values()], ignore_index=True))
        for rid, R in D.items():
            T = R["T"].copy(); T["ym"] = T.date.astype(str).str[:6]
            for pn, a, b in PER:
                z = T[(T.date >= a) & (T.date <= b)]
                m = z.groupby("ym").ret.mean()
                t = m.mean() / m.std(ddof=1) * math.sqrt(len(m)) if len(m) >= 3 and m.std(ddof=1) > 0 else None
                if len(m) < 12:
                    rows.append((mk, rid, R, pn, len(z), len(m), m.mean() if len(m) else None, t, [None] * len(NS))); continue
                ds = [deflated_sharpe(m, n) for n in NS]
                rows.append((mk, rid, R, pn, len(z), len(m), m.mean(), t, [d["dsr"] if d else None for d in ds]))
    hd = "| 시장 | 규칙 | 기간 | 거래 | 달 | 월평균 | t값 | " + " | ".join("N=%s" % format(n, ",") for n in NS) + " |"
    L += [hd, "|" + "---|" * (7 + len(NS))]
    for mk, rid, R, pn, n, nm, mu, t, ds in rows:
        cell = ["" if d is None else ("**%.2f**" % d if d >= 0.90 else "%.2f" % d) for d in ds]
        L.append("| %s | [%s](%s) | %s | %d | %d | %s | %s | %s |" % (
            "국장" if mk == "kr" else "미장", R["name"], R["disp"], pn, n, nm,
            "" if mu is None else "%+.2f%%" % mu, "" if t is None else "%.1f" % t, " | ".join(cell)))
    s = "\n".join(L)
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports" / "dsr_live_1108.md").write_text(s, encoding="utf-8")
    pickle.dump(rows, open(OUTD / "rows.pkl", "wb"))
    print(s)


{"kr": kr, "us": us, "rep": rep}[cmd]()
