# -*- coding: utf-8 -*-
"""사전 등록 자동 판정기 — 2026-11-12 사용자 "① 해줘"(확인을 사람 기억 없이 기계가).

research/prereg/registry.json 의 열린(open·extended) 항목마다 날 수가 찼는지 보고, 차면 미리 정한 합격선으로 판정한다.
  판정: pass(합격) · fail(기각) · extend(연장 — extend 날 수까지) · wait(아직)
  기록: registry.json 의 status·verdict·judged · research/reports/prereg_status.md(한눈 표) · 텔레그램은 판정 났을 때만 한 줄
매일 21:10 예약 작업 \\BamhobakFactory\\Prereg.  python research/prereg/judge.py [dry]
"""
import io, contextlib, glob, json, math, sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parent; RES = HERE.parent; BASE = RES.parent
sys.path.insert(0, str(BASE)); sys.path.insert(0, str(RES)); sys.path.insert(0, str(RES / "factory"))
LOG = HERE / "judge.log"
if sys.stdout is None or sys.stderr is None:
    sys.stdout = sys.stderr = open(LOG, "a", encoding="utf-8", buffering=1)
import numpy as np, pandas as pd

REG = HERE / "registry.json"
M1 = BASE / "data" / "m1" / "KR" / "day"


def m1_days(start):
    return sorted(p.stem for p in M1.glob("*.parquet") if p.stem >= start)


def nxt_ah(it):
    """H0366 — data/nxt/log.csv picks: 고른 날 바구니 r_ask · 플러스 날 · 계좌 크기별 벽 부족."""
    L = pd.read_csv(BASE / "data" / "nxt" / "log.csv", dtype={"pick_day": str, "sell_day": str})
    L = L[(L.grp == "picks") & (L.pick_day >= it["start"])]
    L["r"] = pd.to_numeric(L.r_ask, errors="coerce")
    done = L[L.r.notna()]
    d = done.groupby("pick_day").r.mean()
    n = len(d)
    if n < it["need"]: return "wait", "고른 날 %d/%d" % (n, it["need"]), {}
    d = d.iloc[:it["need"]]
    sizes = [c[7:] for c in L.columns if c.startswith("r_wall_")]
    use = done[done.pick_day.isin(d.index)]
    wall = {sz: float(pd.to_numeric(use["r_wall_" + sz], errors="coerce").isna().mean() * 100) for sz in sizes}
    ok_sz = [sz for sz, w in wall.items() if w <= 10]
    m, pos = float(d.mean()), float((d > 0).mean() * 100)
    num = dict(days=n, mean=round(m, 3), pos=round(pos, 1), wall=wall)
    txt = "날 바구니 %+.2f%% · 플러스 날 %.0f%% · 벽 부족 ≤10%% 크기 %s" % (m, pos, ",".join(ok_sz) or "없음")
    if m >= 0.2 and pos >= 50 and ok_sz: return "pass", txt + " → 합격(소액 실전 가능)", num
    return "fail", txt + " → 기각", num


def a5_tight(it):
    """A5T — 조인 판 새 날만: 100만·체결 손해 뒤 하루 손익 > 0 & t ≥ 2."""
    days = sorted(Path(p).name[3:11] for p in glob.glob(str(BASE / "data" / "factory" / "auction" / "KR_*_am.parquet")))
    new = [d for d in days if d >= it["start"] and (M1 / ("%s.parquet" % d)).exists()]
    lim = it.get("need") if it.get("status") == "open" else it.get("extend")
    if len(new) < lim: return "wait", "새 날 %d/%d" % (len(new), lim), {}
    import a5_tighten_1112 as T5, t1_size_liq_1021 as SL
    with contextlib.redirect_stdout(io.StringIO()):
        A = T5.build()
        ab, cf = SL.fit(SL.liq_of_exec())
    A = A[A.date.isin(new[:lim])]
    Z = A[(A.aerr >= 3) & (A.gap <= -2)]
    p = 100e4 / Z.a20.fillna(Z.a20.median()) * 100
    loss = np.maximum(0, ab[0] + ab[1] * np.sqrt(p)); fill = 1 / (1 + cf * p)
    dp = (100e4 * fill * (Z.ret - loss) / 100).groupby(Z.date).sum().reindex(new[:lim]).fillna(0)
    t = dp.mean() / dp.std(ddof=1) * math.sqrt(len(dp)) if dp.std(ddof=1) > 0 else 0.0
    num = dict(days=len(dp), n=int(len(Z)), pnl=round(float(dp.mean()), 0), t=round(float(t), 2))
    txt = "새 %d일 %d건 · 100만·체결 손해 뒤 하루 %+.1f만 (t %.1f)" % (len(dp), len(Z), dp.mean() / 1e4, t)
    if dp.mean() > 0 and t >= 2: return "pass", txt + " → 합격(실금액 50~100만 조인 판 제안)", num
    if it.get("status") == "open" and it.get("extend"): return "extend", txt + " → %d일까지 연장" % it["extend"], num
    return "fail", txt + " → 기각(실금액 안 함, 그림자 F1659 기록만)", num


def _audit():
    f = BASE / "data" / "audit" / "live.csv"
    return pd.read_csv(f, dtype={"buy_day": str, "sell_day": str, "t": str}) if f.exists() else None


def t1_cond(it):
    A = _audit()
    if A is None: return "wait", "감사 기록 없음", {}
    z = A[A.rid.isin(["T1", "T2", "T3", "T4"]) & (A.buy_day >= it["start"]) & A.in_cond.notna()]
    ds = sorted(z.buy_day.unique())
    if len(ds) < it["need"]: return "wait", "실전 날 %d/%d (%d건)" % (len(ds), it["need"], len(z)), {}
    z = z[z.buy_day.isin(ds[:it["need"]])]
    oc = float((z.in_cond == 0).mean() * 100)
    num = dict(days=it["need"], n=int(len(z)), out=round(oc, 1))
    txt = "%d일 %d건 중 연구 조건 밖 %.0f%%" % (it["need"], len(z), oc)
    return ("pass", txt + " → 그물 고침 효과 확인", num) if oc <= 20 else ("fail", txt + " → 그물·지정가 다시 보기", num)


def t5_rank(it):
    A = _audit()
    if A is None: return "wait", "감사 기록 없음", {}
    ds = m1_days(it["start"])
    if len(ds) < it["need"]: return "wait", "거래일 %d/%d" % (len(ds), it["need"]), {}
    z = A[(A.rid == "T5") & (A.buy_day >= it["start"]) & (A.buy_day <= ds[it["need"] - 1])]
    num = dict(n=int(len(z)), research=round(float(z.research.mean()), 3) if len(z) else None, live=round(float(z.live.mean()), 3) if len(z) else None)
    if len(z) < 10: return "fail", "%d거래일 실전 왕복 %d건(10건 안 됨) → 표본 부족, 규칙 다시 보기" % (it["need"], len(z)), num
    txt = "%d건 연구 기준 건당 %+.2f%% · 실전 %+.2f%%" % (len(z), z.research.mean(), z.live.mean())
    return ("pass", txt + " → 유지", num) if z.research.mean() > 0 else ("fail", txt + " → 규칙 다시 보기", num)


CHECKS = {"nxt_ah": nxt_ah, "a5_tight": a5_tight, "t1_cond": t1_cond, "t5_rank": t5_rank}


def main(dry=False):
    R = json.loads(REG.read_text(encoding="utf-8"))
    msgs, rows = [], []
    for it in R["items"]:
        st = it.get("status")
        if st in ("open", "extended") and it.get("check") in CHECKS:
            try:
                v, txt, num = CHECKS[it["check"]](it)
            except Exception as ex:
                v, txt, num = "wait", "오류 %s" % repr(ex)[:150], {}
            it["last"] = dict(at=time.strftime("%Y-%m-%d %H:%M"), verdict=v, text=txt)
            if v != "wait":
                it.setdefault("history", []).append(dict(at=time.strftime("%Y-%m-%d"), verdict=v, text=txt, num=num))
                it["status"] = "extended" if v == "extend" else v
                msgs.append("📋 <b>사전 등록 판정</b> %s %s\n%s" % (it["id"], it["name"], txt))
        rows.append("| %s | %s | %s | %s | %s |" % (it["id"], it["name"], it.get("status"), it.get("start"), (it.get("last") or {}).get("text") or it.get("why") or ""))
    md = ["# 사전 등록 판정 현황", "", "(%s · research/prereg/judge.py)" % time.strftime("%Y-%m-%d %H:%M"), "",
          "| id | 이름 | 상태 | 시작 | 지금 |", "|---|---|---|---|---|"] + rows
    print("\n".join(md))
    if dry: return
    REG.write_text(json.dumps(R, ensure_ascii=False, indent=1), encoding="utf-8")
    (RES / "reports" / "prereg_status.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    if msgs:
        import day_alert as D
        for m in msgs: D.telegram(m)


if __name__ == "__main__":
    main(dry=(sys.argv[1:2] == ["dry"]))
