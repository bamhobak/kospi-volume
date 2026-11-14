# -*- coding: utf-8 -*-
"""2026-11-14 사용자 "자본금 1억·2억일 때 가장 많이 버는 규칙 활용법 비교" — 1단계: 국장 스윙(portfolio.py 9규칙) 계좌를 원 단위로.
portfolio.py 규칙·비중·자리·우선순위 그대로 + 금액 체결 손해(0.143 + 1.321√p, p = 금액 ÷ 20일 거래대금 %, 한 번) · 매일 종가 평가.
배율 m = 규칙 비중 전체 × m (0.5·1·1.5·2). 결과 C:/temp/kp/mix_swing.pkl (날마다 nav·묶인 돈) + 2016~ 참고 줄.
    python research/mix_swing_1114.py"""
import io, os, sys, time, math, pickle, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd
BASE = Path(__file__).resolve().parent.parent
os.chdir(BASE); sys.path.insert(0, str(BASE))
t0 = time.time()
import threading
def _rss():
    import ctypes, ctypes.wintypes as W
    class PMC(ctypes.Structure):
        _fields_ = [("cb", W.DWORD), ("PageFaultCount", W.DWORD)] + [(n, ctypes.c_size_t) for n in (
            "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
            "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]
    ps = ctypes.WinDLL("psapi")                                 # 공유 객체에 argtypes 안 걸기(memguard 와 부딪힘 11-14)
    c = PMC(); c.cb = ctypes.sizeof(c); ps.GetProcessMemoryInfo(ctypes.c_void_p(-1), ctypes.byref(c), c.cb)
    return c.WorkingSetSize
PEAK = [0]
MEMLIM = float(os.environ.get("MIX_MEM_GB", "10")) * 1e9               # 11-14 사용자 "10gb 허용"(전 6GB)
def _guard():                                                          # RAM 규칙(하나당 6GB) — 넘으면 스스로 멈춘다(밖에서 강제 종료가 막혀 있음)
    while True:
        r = _rss(); PEAK[0] = max(PEAK[0], r)
        if r > MEMLIM:
            sys.__stdout__.write("메모리 %.1fGB — 규칙 넘어 스스로 멈춤 (%.1f분)\n" % (r / 1e9, (time.time() - t0) / 60)); sys.__stdout__.flush(); os._exit(3)
        time.sleep(0.5)
threading.Thread(target=_guard, daemon=True).start()
if (BASE / "data" / "slim" / "panel_kq.pkl").exists():               # 11-14 가는 패널(research/slim_panels.py) — 통째 패널은 16.8GB
    os.environ.setdefault("PANEL_KP", "slim/panel_kp.pkl"); os.environ.setdefault("PANEL_KQ", "slim/panel_kq.pkl")
CAPS = [float(x) * 1e8 for x in sys.argv[1:]] or [1e8, 2e8]
TAG = "" if CAPS == [1e8, 2e8] else "_" + "_".join("%g" % (c / 1e8) for c in CAPS)
sys.argv = sys.argv[:1]                                               # portfolio.py 가 인자를 자기 옵션으로 읽고 조용히 끝남(11-14)
src = (BASE / "portfolio.py").read_text(encoding="utf-8").split("# @@ANALYSIS")[0]
_OLD_CR = '''    _M = _K.merge(_CR[["date","ticker","cr_chg20"]], on=["ticker","date"], how="left")
    assert len(_M) == _n
    _K["cr_chg20"] = _M.cr_chg20.values'''
_NEW_CR = '''    _M = None                                                    # (mix_swing 11-14) merge 는 패널 통째 복사 → 메모리 두 배. 같은 값을 색인으로
    _K["cr_chg20"] = _CR.drop_duplicates(["ticker","date"]).set_index(["ticker","date"]).cr_chg20.reindex(pd.MultiIndex.from_arrays([_K.ticker.values, _K.date.values])).values'''
assert src.count(_OLD_CR) == 1, "portfolio.py 신용 병합 줄이 바뀜 — mix_swing 고칠 것"
src = src.replace(_OLD_CR, _NEW_CR)
ns ={"__file__": str(BASE / "portfolio.py"), "__name__": "x"}
_real = sys.stdout; sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
exec(compile(src, "portfolio.py", "exec"), ns)
sys.stdout = _real; sys.stdout.reconfigure(encoding="utf-8")
S, dates, KP, KQ = ns["S"], ns["dates"], ns["KP"], ns["KQ"]
ND = len(dates); DI = {d: i for i, d in enumerate(dates)}
print("재료 %.1f분 · 신호 %d · amt20 중앙 %.2f" % ((time.time() - t0) / 60, len(S), S.amt20.median()), flush=True)
pickle.dump(dict(S=S[["date", "ticker", "rid", "hold", "pct", "mx", "buy", "exit", "cost", "amt20", "di"]].copy(), dates=list(dates)),
            open(r"C:\temp\kp\port_sig.pkl", "wb"))                  # 11-14 스윙 손익 해부(anatomy_swing_1114)용 신호표 — 다음엔 portfolio 안 돌려도 됨
if os.environ.get("MIX_DUMP_ONLY"): sys.exit(0)
KB =pd.concat([KP[["ticker", "date", "close"]], KQ[["ticker", "date", "close"]]], ignore_index=True).drop_duplicates(["ticker", "date"])
del ns
TK = np.array(sorted(KB.ticker.unique())); TI = {t: i for i, t in enumerate(TK)}
di_ = KB.date.map(DI).values; ti_ = KB.ticker.map(TI).values; okm = ~pd.isna(di_)
CL = np.full((ND, len(TK)), np.nan, np.float32); CL[di_[okm].astype(int), ti_[okm]] = KB.close.values[okm]
CLf = pd.DataFrame(CL).ffill().values; del CL, KB
S = S.copy(); S["ti"] = S.ticker.map(TI)
UNIT = 1e8 if S.amt20.median() < 1e5 else 1.0          # amt20 단위(억 → 원)
TOD = {i: g for i, g in S.groupby("di")}
imp = lambda p: max(0.0, 0.143 + 1.321 * math.sqrt(p))


def sim(C, m, d0, d1):
    i0, i1 = DI[min(d for d in dates if d >= d0)], DI[max(d for d in dates if d <= d1)]
    eq = C; pos = []; nav = []; inv_ = []; nb = 0; impw = 0.0
    for i in range(i0, i1 + 1):
        still = []
        for p in pos:
            if p["x"] <= i: eq += p["amt"] * ((p["exit"] / p["buy"] - 1) * 100 - p["cost"] - p["imp"]) / 100
            else: still.append(p)
        pos = still
        T = TOD.get(i)
        if T is not None:
            inv = sum(p["amt"] for p in pos)
            for t in T.itertuples():
                w = eq * t.pct / 100 * m
                if sum(1 for p in pos if p["rid"] == t.rid) >= t.mx or inv + w > eq or any(p["tk"] == t.ticker for p in pos): continue
                pi = w / (t.amt20 * UNIT) * 100 if t.amt20 and t.amt20 > 0 else 50
                pos.append(dict(rid=t.rid, tk=t.ticker, ti=t.ti, buy=t.buy, exit=t.exit, cost=t.cost, imp=imp(pi), amt=w, x=i + t.hold, d0=i))
                inv += w; nb += 1; impw += imp(pi) * w
        inv = sum(p["amt"] for p in pos); un = 0.0
        for p in pos:
            if i > p["d0"]:
                c = CLf[i, p["ti"]]
                if c == c: un += p["amt"] * (c / p["buy"] - 1)
        nav.append(eq + un); inv_.append(inv)
    return dict(d=list(dates[i0:i1 + 1]), nav=np.array(nav), inv=np.array(inv_), nb=nb, imp=impw / max(1, sum([1])), )


D0, D1 = "20250401", "20261008"
OUT = {}
for C in CAPS:
    for m in (0.5, 1.0, 1.5, 2.0):
        r = sim(C, m, D0, D1); OUT[(C, m)] = r
        x = r["nav"]; print("%d억 ×%.1f: 끝 %.0f만(%+.1f%%) · 낙폭 %.1f%% · 묶인 돈 평균 %.0f만 · 최대 %.0f만 · %d건 · %.1f분" % (
            C / 1e8, m, x[-1] / 1e4, (x[-1] / C - 1) * 100, (x / np.maximum.accumulate(x) - 1).min() * 100, r["inv"].mean() / 1e4, r["inv"].max() / 1e4, r["nb"], (time.time() - t0) / 60), flush=True)
LONG = {}
for C in CAPS:
    for m in (1.0, 1.5, 2.0):
        r = sim(C, m, "20160101", D1); LONG[(C, m)] = r
        print("2016~ %d억 ×%.1f 끝 %.1f배 %.1f분" % (C / 1e8, m, r["nav"][-1] / C, (time.time() - t0) / 60), flush=True)
# 0배(스윙 없음) 참고용 = 묶인 돈 0
pickle.dump(dict(win=OUT, long=LONG), open(r"C:\temp\kp\mix_swing%s.pkl" % TAG, "wb"))
print("끝 %.1f분 · 최대 메모리 %.1fGB" % ((time.time() - t0) / 60, PEAK[0] / 1e9))
