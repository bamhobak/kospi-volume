# -*- coding: utf-8 -*-
"""국장 새 데이 규칙 찾기 — 1분봉 장중 단면(m1_panel) (2026-10-06, 사용자 "다른 규칙 찾아봐").
일봉으로는 못 보던 **장중 재료**(그 시각까지 얼마나 빠졌나·거래량 몰림·시가 범위 돌파·VWAP·막판 저가)로 사고,
같은 날 종가 단일가(또는 다음날 시가)에 판다. 무리:
  A 오후 모멘텀/되돌림(14:30 매수) · B 장 초반 투매 되돌림(09:30) · C 첫 5분 거래량 폭발(09:05) · D 시가 범위 돌파(ORB)
  E VWAP 되찾기 · F 오전 상승 뒤 오후 눌림 · G 장중 모양 → 밤 넘기기(종가→다음날 시가) · I 갭 상승 지킴 · J 점심 눌림
비용: 수수료·세금 0.23% + 장중 시장가로 사면 +0.10%(중소형 호가 공백 감안) · 종가·시가 단일가는 미끄러짐 0.
견줄 것: 같은 날 유니버스(거래대금 20일 하위 20% 뺀 것 · 30억↑ · 1천원↑) 아무 종목의 **같은 구간** 평균 → 초과.
판정: 학습(2022-12~2024)·검증(2025~) 둘 다 비용 뒤 평균 > 0 & 초과 > 0 · 일별로 묶은 초과 t ≥ 3(칸 30개 → 다중검정) ·
      해마다 플러스 3/4↑ · 하루 0.3건↑.
⚠ 1분봉 종목은 **지금** 거래대금 상위 1,000 — 그 사이 무너진 종목이 빠진 표본(장중 하루 보유라 영향은 작지만 0 은 아님).
    python research/day3.py
"""
import sys, time
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(BASE))
from verdict import log_trials
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))
FEE, SLIP = 0.23, 0.10
SNAP = ["0905", "0910", "0915", "0930", "1000", "1030", "1100", "1200", "1300", "1400", "1430", "1500", "1519"]


def load():
    A = pd.read_pickle(ROOT / "cache" / "m1_panel_KR.pkl")
    A = A[A.pc.notna() & (A.pc > 0)]
    A["gap"] = (A.o / A.pc - 1) * 100
    A = A[A.gap.abs() < 30]                                        # 이음새(분할 전후) — 가격제한폭 밖은 버린다
    A = A[((A.c / A.pc - 1).abs() < 0.31)]
    A["rk"] = A.groupby("date").amt20.rank(pct=True)
    A["uni"] = (A.rk >= 0.2) & (A.amt20 >= 3e9) & (A.pc >= 1000)
    return A[A.uni].copy()


def bench(A):
    """같은 날 유니버스 평균 — 시작 시각(o·p0905…p1519·c) → 끝(c·no)."""
    B = {}
    for s in ["o"] + ["p" + h for h in SNAP]:
        B[(s, "c")] = ((A.c / A[s] - 1) * 100).groupby(A.date).mean()
    B[("c", "no")] = ((A.no / A.c - 1) * 100).groupby(A.date).mean()
    return B


def snap_of(hm):
    for h in SNAP:
        if h >= hm: return "p" + h
    return "p1519"


def rules(A):
    r = lambda a, b: (A[a] / A[b] - 1) * 100
    R = {}
    o14 = r("p1430", "o"); q14 = o14.groupby(A.date).rank(pct=True)
    R["A1 14:30까지 강한 10%(시가 대비) → 종가"] = (q14 >= 0.9, "p1430", "c", SLIP)
    R["A2 14:30까지 약한 10% → 종가"] = (q14 <= 0.1, "p1430", "c", SLIP)
    R["A3 14:30 전일비 상위10% & 고가 근처 → 종가"] = ((r("p1430", "pc").groupby(A.date).rank(pct=True) >= 0.9) & (A.p1430 >= A.hi1430 * 0.99), "p1430", "c", SLIP)
    f30 = r("p0930", "o")
    R["B1 09:30 시가 대비 -3%↓ → 종가"] = (f30 <= -3, "p0930", "c", SLIP)
    R["B2 09:30 시가 대비 -5%↓ → 종가"] = (f30 <= -5, "p0930", "c", SLIP)
    R["B3 갭 하락 & 09:30 -3%↓ 더 → 종가"] = ((A.gap <= 0) & (f30 <= -3), "p0930", "c", SLIP)
    R["B4 갭 +2%↑ & 09:30 -3%↓ → 종가"] = ((A.gap >= 2) & (f30 <= -3), "p0930", "c", SLIP)
    R["B5 09:30 전일비 -5%↓ & 저가 근처 → 종가"] = ((r("p0930", "pc") <= -5) & (A.p0930 <= A.lo0930 * 1.005), "p0930", "c", SLIP)
    vs = A.v0905 / A.v5_20.replace(0, np.nan)
    R["C1 첫 5분 거래량 5배↑ & 오름 → 종가"] = ((vs >= 5) & (A.p0905 > A.o), "p0905", "c", SLIP)
    R["C2 첫 5분 거래량 5배↑ & 내림 → 종가"] = ((vs >= 5) & (A.p0905 < A.o), "p0905", "c", SLIP)
    R["C3 첫 5분 거래량 하위(0.5배↓) & 내림 → 종가"] = ((vs <= 0.5) & (A.p0905 < A.o), "p0905", "c", SLIP)
    R["D1 시가 15분 범위 돌파 → 종가"] = (A.orb15_px.notna(), "orb15_px", "c", SLIP)
    R["D2 시가 30분 범위 돌파 → 종가"] = (A.orb30_px.notna(), "orb30_px", "c", SLIP)
    R["D3 갭 +2%↑ & 15분 범위 돌파 → 종가"] = (A.orb15_px.notna() & (A.gap >= 2), "orb15_px", "c", SLIP)
    R["D4 갭 -2%↓ & 15분 범위 돌파 → 종가"] = (A.orb15_px.notna() & (A.gap <= -2), "orb15_px", "c", SLIP)
    R["E1 10시 VWAP 아래 → 13시 전 되찾음 → 종가"] = (A.vwr_px.notna(), "vwr_px", "c", SLIP)
    R["E2 갭 -2%↓ & VWAP 되찾음 → 종가"] = (A.vwr_px.notna() & (A.gap <= -2), "vwr_px", "c", SLIP)
    R["F1 11시 +3%↑ 뒤 14:30 까지 -3%↓ → 종가"] = ((r("p1100", "o") >= 3) & (r("p1430", "p1100") <= -3), "p1430", "c", SLIP)
    R["J1 11시 보합↑ 뒤 13시 -2%↓ → 종가"] = ((r("p1100", "o") >= 0) & (r("p1300", "p1100") <= -2), "p1300", "c", SLIP)
    R["I1 갭 +5%↑ & 09:30 시가 위 → 종가"] = ((A.gap >= 5) & (A.p0930 > A.o), "p0930", "c", SLIP)
    R["I2 갭 +3%↑ & 10시 VWAP 위 → 종가"] = ((A.gap >= 3) & (A.p1000 > A.vw1000), "p1000", "c", SLIP)
    oc = r("c", "o"); pcc = r("c", "pc")
    R["G1 장중 -5%↓(시가→종가) → 밤 넘겨 다음날 시가"] = (oc <= -5, "c", "no", 0.0)
    R["G2 14시 뒤 새 저가 & 전일비 -5%↓ → 다음날 시가"] = ((A.lo14 < A.lo_am) & (pcc <= -5), "c", "no", 0.0)
    R["G3 고가 마감 & 전일비 +5%↑ → 다음날 시가"] = ((A.c >= A.hi * 0.995) & (pcc >= 5), "c", "no", 0.0)
    R["G4 저가가 15시 뒤 & 저가 마감 → 다음날 시가"] = ((A.lo_t >= "1500") & (A.c <= A.lo * 1.01), "c", "no", 0.0)
    R["G5 장중 +5%↑ & 고가 마감 → 다음날 시가"] = ((oc >= 5) & (A.c >= A.hi * 0.995), "c", "no", 0.0)
    return R


def evaluate(A, B, name, sig, ent, ext, slip):
    S = A[sig.fillna(False).astype(bool)].copy()
    if ext == "no": S = S[S.no.notna()]
    S = S[S[ent].notna() & (S[ent] > 0)]
    if len(S) < 50: return None
    S["ret"] = (S[ext] / S[ent] - 1) * 100 - FEE - slip
    if ent in ("orb15_px", "orb30_px", "vwr_px"):
        k = ent.replace("_px", "_t"); bs = S[k].map(snap_of)
        S["bm"] = [B[(b, "c")].get(d, np.nan) for b, d in zip(bs, S.date)]
    else:
        S["bm"] = S.date.map(B[(ent, ext)])
    S["ex"] = S.ret + FEE + slip - S.bm                              # 같은 구간 유니버스 평균 대비(비용 전 기준으로 맞춘다)
    S = S[S.ex.notna() & S.ret.abs().lt(40)]
    out = {"name": name, "n": len(S), "days": S.date.nunique(), "perday": len(S) / A.date.nunique()}
    for k, (a, b) in {"tr": ("20221201", "20241231"), "va": ("20250101", "20991231")}.items():
        z = S[(S.date >= a) & (S.date <= b)]
        out[k] = (len(z), z.ret.mean(), (z.ret > 0).mean() * 100, z.ex.mean()) if len(z) >= 20 else None
    d = S.groupby("date").ex.mean()
    out["t"] = d.mean() / (d.std() / np.sqrt(len(d))) if len(d) > 5 else np.nan
    yr = S.groupby(S.date.str[:4]).ret.mean(); yr = yr[yr.index >= "2023"]
    out["yp"], out["ny"] = int((yr > 0).sum()), len(yr)
    out["mean"], out["win"] = S.ret.mean(), (S.ret > 0).mean() * 100
    tr, va = out["tr"], out["va"]
    out["ok"] = bool(tr and va and tr[1] > 0 and va[1] > 0 and tr[3] > 0 and va[3] > 0 and out["t"] >= 3 and out["yp"] >= out["ny"] - 1 and out["perday"] >= 0.3)
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    t0 = time.time()
    A = load(); B = bench(A)
    P("# 국장 새 데이 규칙 — 1분봉 장중 재료 · %s" % time.strftime("%Y-%m-%d")); P("")
    P("- 유니버스 %s 종목-일 · 종목 %d · %d일(%s~%s) · 학습 2022-12~2024 / 검증 2025~" % (f"{len(A):,}", A.ticker.nunique(), A.date.nunique(), A.date.min(), A.date.max()))
    P("- 비용 수수료·세금 %.2f%% + 장중 시장가 매수 %.2f%% · 초과 = 같은 날 유니버스 같은 구간 평균 대비 · 통과 = 둘 다 플러스·초과 플러스·t≥3·해마다·하루 0.3건↑" % (FEE, SLIP)); P("")
    P("| 규칙 | 건수(하루) | 학습: 평균·승률·초과 | 검증: 평균·승률·초과 | 초과 t | 플러스 해 | 판정 |"); P("|---|---|---|---|---|---|---|")
    res = []
    for name, (sig, ent, ext, slip) in rules(A).items():
        o = evaluate(A, B, name, sig, ent, ext, slip)
        if o is None: P("| %s | 50건 미만 | | | | | |" % name); continue
        res.append(o)
        c = lambda z: "-" if not z else "%d건 %+.2f%% · %.0f%% · %+.2f" % z
        P("| %s | %d (%.1f) | %s | %s | %.1f | %d/%d | %s |" % (name, o["n"], o["perday"], c(o["tr"]), c(o["va"]), o["t"], o["yp"], o["ny"], "✅ 통과" if o["ok"] else "—"))
    P(""); P("(칸 %d · 통과 %d · %.1f분)" % (len(res), sum(o["ok"] for o in res), (time.time() - t0) / 60))
    log_trials("day3_%s" % time.strftime("%Y%m%d"), len(res))
    pd.to_pickle(res, ROOT / "cache" / "day3.pkl")
    (ROOT / "reports" / ("day3_%s.md" % time.strftime("%Y%m%d"))).write_text("\n".join(OUT) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
