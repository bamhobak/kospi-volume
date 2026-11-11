# -*- coding: utf-8 -*-
"""밤 과거 자료 받기 줄 (2026-11-12 사용자 아이디어 ⑤ "나중에 못 사는·연구에 쓸 과거 자료를 밤에 조금씩").

일감 목록 = research/backfill/jobs.json (위에서부터 차례로, enabled 만). 진행·남은 시간 = data/backfill/state.json · 기록 data/backfill/run.log
  nxt_pre  NXT 장전 1분봉(08:01~08:51) 2025-03-04~어제 · NXT 거래 종목 전부 → research/cache/bf_nxt_pre/(bars_*·done_*.parquet)
           이미 받은 표본(C:/temp/kp/pm_parts·pm_parts2 done)은 건너뜀
  nxt_ah   NXT 장후 1분봉(16:41~20:00) 같은 기간·같은 종목 → research/cache/bf_nxt_ah/ · research/cache/ah_m1.parquet 에 있는 (종목, 날)은 건너뜀
  m1_gap   data/m1/KR/day 빈 거래일(첫 파일 뒤·어제까지) 메우기 → 같은 폴더(빠진 날만, 있는 파일은 안 건드림)
지키는 것:
  · 받는 시간 20:10~07:30 만 — 07:30 이 되면 묶음 단위로 저장하고 멈춤(다음 밤 이어받기 = done 파일).
  · 초당 4회(이 프로세스) — collect_m1 의 _throttle(초당 14)은 프로세스 안에서만 지켜져서 따로 더 느리게.
  · 양보: data/m1/.busy·.busy_* 있거나 \\BamhobakM1·Nxt·Day·AutoTrade 작업이 도는 중이면 30초씩 쉼.
  · 텔레그램: 오류 때와 일감 하나 다 끝났을 때 한 줄만.
    python research/backfill/night_fill.py run      (예약 작업 \\BamhobakM1\\NightFill 20:10)
    python research/backfill/night_fill.py status
    python research/backfill/night_fill.py test     (아주 작은 시험 — 받는 시간 밖에서도 몇 건만)
"""
import datetime as dt, glob, json, os, random, subprocess, sys, threading, time
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
OUTD = BASE / "data" / "backfill"; OUTD.mkdir(parents=True, exist_ok=True)
LOGF = OUTD / "run.log"
if sys.stdout is None or sys.stderr is None:                             # pythonw(예약 작업)는 stdout 이 없다
    sys.stdout = sys.stderr = open(LOGF, "a", encoding="utf-8", buffering=1)
else:
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
sys.path.insert(0, str(BASE)); sys.path.insert(0, str(BASE / "research" / "factory"))
import pandas as pd
import collect_m1 as M

CACHE = BASE / "research" / "cache"
JOBS = Path(__file__).with_name("jobs.json")
STATE = OUTD / "state.json"
RATE = 4.0                     # 초당 호출(이 프로세스)
CHUNK = 200                    # 묶음(저장·양보·시간 확인 단위)
START, STOP = dt.time(20, 10), dt.time(7, 30)
FIRST = "20250304"             # NXT 개장
YIELD_PATHS = ("\\BamhobakM1\\", "\\BamhobakNxt\\", "\\BamhobakDay\\", "\\BamhobakAutoTrade\\")
SELF = "NightFill"

_lock = threading.Lock(); _last = [0.0]


def log(*a):
    print("%s %s" % (dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), " ".join(str(x) for x in a)), flush=True)


def tg(s):
    try:
        import common as C
        C.tg(s)
    except Exception as ex:
        log("텔레그램 실패", repr(ex)[:200])


def pace():
    with _lock:
        w = _last[0] + 1.0 / RATE - time.time()
        if w > 0: time.sleep(w)
        _last[0] = time.time()


def in_window(now=None):
    t = (now or dt.datetime.now()).time()
    return t >= START or t < STOP


def others_running():
    """양보할 작업이 도는 중인가(이름 목록) — 실패하면 빈 목록(막지 않음)."""
    ps = ("Get-ScheduledTask | Where-Object { $_.State -eq 'Running' } | ForEach-Object { $_.TaskPath + $_.TaskName }")
    try:
        r = subprocess.run([r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe", "-NoProfile", "-Command", ps],
                           capture_output=True, text=True, timeout=60)
        names = [l.strip() for l in (r.stdout or "").splitlines() if l.strip()]
    except Exception:
        return []
    return [n for n in names if n.startswith(YIELD_PATHS) and not n.endswith("\\" + SELF)]


def busy():
    m = BASE / "data" / "m1"
    return (m / ".busy").exists() or any(m.glob(".busy_*"))


def gate(test=False):
    """받아도 되나 — 받는 시간 밖이면 False(멈춤), 양보할 게 있으면 기다림."""
    if test: return True
    while True:
        if not in_window(): return False
        b, o = busy(), others_running()
        if not b and not o: return True
        log("양보 중:", ".busy" if b else "", ",".join(o)[:200]); time.sleep(30)


def load_state():
    try: return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception: return {}


def save_state(S):
    tmp = STATE.with_suffix(".tmp"); tmp.write_text(json.dumps(S, ensure_ascii=False, indent=1), encoding="utf-8"); os.replace(tmp, STATE)


# ── 공통 재료 ─────────────────────────────────────────────────────────
def kr_days():
    """2025-03-04~어제 국장 거래일 — 1분봉 요약(m1_daysum) + 매일 1분봉 파일 + 최근 일봉 달력."""
    ds = set(pd.read_parquet(CACHE / "m1_daysum.parquet", columns=["d"]).d.unique())
    ds |= {Path(p).stem for p in glob.glob(str(BASE / "data" / "m1" / "KR" / "day" / "*.parquet"))}
    try: ds |= set(M.trading_days("KR", 60))
    except Exception as ex: log("달력 받기 실패", repr(ex)[:200])
    today = dt.datetime.now().strftime("%Y%m%d")
    return sorted(d for d in ds if FIRST <= d < today)


def nxt_tickers():
    J = json.loads((CACHE / "toss_nxt_kr.json").read_text(encoding="utf-8"))
    return sorted(k for k, v in J.items() if v.get("nxt"))


def done_of(folder):
    s = set()
    for f in glob.glob(str(folder / "done_*.parquet")):
        try:
            z = pd.read_parquet(f, columns=["t", "d"]); s |= set(zip(z.t.astype(str), z.d.astype(str)))
        except Exception as ex: log("done 읽기 실패", f, repr(ex)[:100])
    return s


def candles(sym, before, count):
    pace()
    return (M.get("/api/v1/candles", symbol=sym, interval="1m", count=count, before=before) or {}).get("candles") or []


def bars_between(sym, d, before, count, lo, hi):
    out = []
    for x in candles(sym, before, count):
        ts = x["timestamp"]
        if ts[:10].replace("-", "") != d: continue
        hm = int(ts[11:13]) * 100 + int(ts[14:16])
        if lo <= hm <= hi:
            out.append((sym, d, hm, float(x["openPrice"]), float(x["highPrice"]), float(x["lowPrice"]), float(x["closePrice"]), float(x["volume"])))
    return out


def fetch_pre(t, d):
    return bars_between(t, d, "%s-%s-%sT08:52:00.000+09:00" % (d[:4], d[4:6], d[6:]), 60, 800, 851)


def fetch_ah(t, d):
    return bars_between(t, d, "%s-%s-%sT20:01:00.000+09:00" % (d[:4], d[4:6], d[6:]), 200, 1641, 2000)


# ── 일감: (종목, 날) 묶음 받기 ──────────────────────────────────────────
def pairs_job(job, fetch, skip, test=False):
    out = CACHE / job["out"]; out.mkdir(parents=True, exist_ok=True)
    tick, days = nxt_tickers(), kr_days()
    done = done_of(out) | skip
    todo = [(t, d) for d in days for t in tick if (t, d) not in done]
    rnd = random.Random(7); order = days[:]; rnd.shuffle(order); rk = {d: i for i, d in enumerate(order)}
    todo.sort(key=lambda z: (rk[z[1]], z[0]))                               # 날을 무작위 순서로 — 덜 받아도 고른 표본
    total = len(todo) + len(done_of(out))
    S = load_state(); st = S.setdefault(job["id"], {})
    st.update(total=total, left=len(todo), updated=dt.datetime.now().isoformat(timespec="seconds"))
    save_state(S)
    full = len(todo)
    if test: todo = todo[:3]
    if not todo:
        return "done"
    log(job["id"], "남은 %d / 전체 %d" % (len(todo), total))
    from concurrent.futures import ThreadPoolExecutor
    t0, n0 = time.time(), 0
    with ThreadPoolExecutor(2) as ex:
        for i in range(0, len(todo), CHUNK):
            if not gate(test): log(job["id"], "받는 시간 끝 — 멈춤(다음 밤 이어서)"); return "paused"
            ch = todo[i:i + CHUNK]
            res = list(ex.map(lambda z: fetch(z[0], z[1]), ch))
            rows = [r for rr in res for r in rr]
            k = "%d_%d" % (int(time.time() * 1000), os.getpid())
            if rows:
                pd.DataFrame(rows, columns=["t", "d", "hm", "o", "h", "l", "c", "v"]).to_parquet(out / ("bars_%s.parquet" % k), index=False)
            pd.DataFrame(ch, columns=["t", "d"]).to_parquet(out / ("done_%s.parquet" % k), index=False)
            n0 += len(ch); el = time.time() - t0
            S = load_state(); st = S.setdefault(job["id"], {})
            left = full - (i + len(ch)); rate = n0 / max(el, 1)
            st.update(total=total, left=left, rate_per_s=round(rate, 2), eta_hours=round(left / max(rate, 0.01) / 3600, 1),
                      rows=int(st.get("rows", 0)) + len(rows), updated=dt.datetime.now().isoformat(timespec="seconds"))
            save_state(S)
            if test: log("시험", job["id"], "받은 봉", len(rows), rows[:2])
    return "done" if not test else "test"


def job_nxt_pre(job, test=False):
    skip = set()
    for p in (r"C:\temp\kp\pm_parts", r"C:\temp\kp\pm_parts2"):
        skip |= done_of(Path(p))
    return pairs_job(job, fetch_pre, skip, test)


def job_nxt_ah(job, test=False):
    skip = set()
    f = CACHE / "ah_m1.parquet"
    if f.exists():
        z = pd.read_parquet(f, columns=["t", "d"]).drop_duplicates()
        skip = set(zip(z.t.astype(str), z.d.astype(str)))
    return pairs_job(job, fetch_ah, skip, test)


def job_m1_gap(job, test=False):
    """매일 1분봉 폴더의 빈 거래일 — 첫 파일 뒤 · 어제까지."""
    D = BASE / "data" / "m1" / "KR" / "day"
    have = sorted(Path(p).stem for p in glob.glob(str(D / "*.parquet")))
    if not have: return "done"
    try: cal = set(M.trading_days("KR", 60))
    except Exception as ex: log("달력 실패", repr(ex)[:200]); return "error"
    today = dt.datetime.now().strftime("%Y%m%d")
    gaps = sorted(d for d in cal if have[0] < d < today and d not in set(have))
    S = load_state(); S.setdefault(job["id"], {}).update(gaps=gaps, updated=dt.datetime.now().isoformat(timespec="seconds")); save_state(S)
    log("빈 날", gaps or "없음")
    if test or not gaps: return "done"
    U = M.universe("KR"); filled = []
    for d in gaps:
        rows = []
        for i in range(0, len(U), CHUNK):
            if not gate(): log("받는 시간 끝 — 빈 날 메우기 멈춤"); return "paused"
            for s_ in U[i:i + CHUNK]:
                pace(); rows += M.fetch_day("KR", s_, d)
        if rows and not (D / ("%s.parquet" % d)).exists():
            M.frame(rows).to_parquet(D / ("%s.parquet" % d), index=False, compression="zstd"); filled.append(d)
            log("빈 날 메움", d, "봉", len(rows))
    if filled: tg("📦 1분봉 빈 날 %d일 메움(%s)" % (len(filled), ",".join(filled)))
    return "done"


RUN = {"nxt_pre": job_nxt_pre, "nxt_ah": job_nxt_ah, "m1_gap": job_m1_gap}


def run(test=False):
    jobs = [j for j in json.loads(JOBS.read_text(encoding="utf-8")) if j.get("enabled", True)]
    if not test and not in_window():
        log("받는 시간(20:10~07:30) 밖 — 안 함"); return
    for j in jobs:
        S = load_state()
        if S.get(j["id"], {}).get("finished") and not j.get("recurring"): continue
        log("일감 시작", j["id"], j.get("desc", ""))
        try:
            r = RUN[j["kind"]](j, test)
        except Exception as ex:
            log("일감 오류", j["id"], repr(ex)[:400]); tg("⚠ 과거 자료 받기 오류 %s: %s" % (j["id"], str(ex)[:200])); continue
        log("일감", j["id"], "→", r)
        if r == "paused": return
        if r == "done" and not test and not j.get("recurring"):
            S = load_state(); st = S.setdefault(j["id"], {})
            if not st.get("finished"):
                st["finished"] = dt.datetime.now().isoformat(timespec="seconds"); save_state(S)
                tg("📦 과거 자료 받기 끝: %s · 봉 %s" % (j.get("desc", j["id"]), format(int(st.get("rows", 0)), ",")))


def status():
    S = load_state()
    for k, v in S.items(): print(k, json.dumps(v, ensure_ascii=False)[:400])


if __name__ == "__main__":
    a = sys.argv[1:]
    try:
        if a[:1] == ["run"]: run()
        elif a[:1] == ["test"]: run(test=True)
        elif a[:1] == ["status"]: status()
        else: print(__doc__)
    except Exception as ex:
        log("실패", repr(ex)[:400]); tg("⚠ 과거 자료 받기 실패: %s" % str(ex)[:200]); raise
