# -*- coding: utf-8 -*-
"""밤 연구 일꾼 — 사용자가 시킨 실측을 밤에 하나씩 돌리고 아침에 한 줄 (2026-11-12 사용자 아이디어 ⑦).

대기 목록 research/nightlab/queue.jsonl — 한 줄에 하나. **사용자가 시킨 것만**(일꾼이 스스로 가설을 짓지 않는다).
  {"id","title","asked"(사용자 원문·날짜),"kind": "script" | "ask",
   "script"(kind=script: research/ 안 파이썬 경로) · "args"[] · "ask"(kind=ask: 무엇을 재라 — 구독 claude -p 가 스크립트를 써 줌),
   "hypothesis"(가설), "pass"[{"key","op","v","label"}](합격선, metrics 키), "not_before"(YYYYMMDD, 이날 밤부터), "mem_gb"(≤6), "max_min",
   "status": queued|done|failed|blocked, ...결과 칸}
사전 등록: `add` 할 때 research/reports/nightlab/<id>_prereg.md 를 쓰고 그 sha 를 목록에 적는다 → 돌리기 전에 다시 대 보고 다르면 안 돌린다
          (결과 보고 합격선 옮기기 차단). 가설·합격선 없는 항목은 안 돌린다.
돌리기(night, 예약 22:35): 22:30~06:30 안에서만 · 06:30 넘기면 죽임(07:30 전 반드시 끝) · 01:20~01:55 공장 밤 작업 시간엔 새로 안 띄움
  · 한 번에 하나 · 띄우기 전 남은 램 8GB↑ · 돌리는 동안 6GB(mem_gb) 넘으면 죽임 · 실전 코드(루트 *.py·index.html·assets·research/factory·
  supabase·.github) 사진 찍어 두고 끝나면 대 보고 바뀌었으면 되돌리고 바로 알림.
  · 결과 계약: 스크립트는 환경변수 NIGHTLAB_OUT(json 경로)에 {"metrics":{..}, "trades": parquet 경로?, "twin":?, "mkt":?, "mode","sel","table"} 를 쓴다.
  · 합격선은 스크립트가 낸 metrics 로만 기계가 판정 → 거래가 있으면 적대적 검토관(research/factory/redteam.py) → **합격 & 검토관 '막음' 아님 = '후보'**.
  · 보고서 research/reports/nightlab/<id>_<날짜>.md · 기록 data/nightlab/runs.jsonl
아침 한 줄(brief, 예약 06:45): 지난밤 돌린 게 있으면 텔레그램 한 줄(없으면 조용).
kind=ask: 구독 claude -p(sonnet)가 정해진 틀로 스크립트를 쓴다 → 금지어 검사(주문·네트워크·지우기·실전 모듈·OUT 밖 쓰기) 통과해야 돈다.
  python research/nightlab/runner.py add 항목.json      대기 목록에 넣기(사전 등록 파일 생성)
  python research/nightlab/runner.py night [--dry]      돌리기(--dry: 시간·날짜 무시, 목록·텔레그램 안 바꿈 — 흐름 확인용)
  python research/nightlab/runner.py brief              아침 한 줄
  python research/nightlab/runner.py list               목록
"""
import ctypes, datetime as dt, hashlib, json, os, re, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent.parent
ST = BASE / "data" / "nightlab"; ST.mkdir(parents=True, exist_ok=True)
LOG = ST / "run.log"
if sys.stdout is None or sys.stderr is None:                             # pythonw(예약 작업)는 stdout 이 없다
    sys.stdout = sys.stderr = open(LOG, "a", encoding="utf-8", buffering=1)
else:
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
for p in (str(BASE / "research" / "factory"), str(BASE / "research"), str(BASE)):
    if p not in sys.path: sys.path.insert(0, p)

Q = HERE / "queue.jsonl"
JOBS = HERE / "jobs"; JOBS.mkdir(exist_ok=True)
RP = BASE / "research" / "reports" / "nightlab"; RP.mkdir(parents=True, exist_ok=True)
RUNS = ST / "runs.jsonl"
BUSY = ST / ".busy"
WIN_START, WIN_END, HARD_END = (22, 30), (6, 30), (7, 30)
FACTORY_GAP = ((1, 20), (1, 55))
FREE_MIN_GB, MEM_MAX_GB = 8.0, 6.0
GUARD = ["*.py", "index.html", "assets/*", "research/factory/*.py", "supabase/functions/*/*.ts", ".github/workflows/*.yml"]
# kind=ask 로 AI 가 쓴 코드에 있으면 안 되는 것 — 주문·돈·네트워크·지우기·실전 모듈·비밀
DENY = [r"\bautotrade\b", r"\bday_alert\b", r"\bnxt_pre\b", r"\bnxt_shadow\b", r"\bday_aerr\b", r"\btoss\b", r"/orders", r"\bsubmit\s*\(",
        r"\brequests\b", r"\burllib\b", r"http\.client", r"\bsocket\b", r"curl_cffi", r"\bpykrx\b", r"\bsubprocess\b", r"os\.system", r"\bPopen\b",
        r"shutil\.(rmtree|move)", r"os\.(remove|unlink|rmdir|rename|replace)", r"\.unlink\s*\(", r"\.rmdir\s*\(", r"\.env\b", r"ANTHROPIC", r"OPENAI",
        r"TELEGRAM", r"\btg\s*\(", r"\beval\s*\(", r"\bexec\s*\(", r"__import__", r"sqlite3\.connect\([^)]*\)\s*\.\s*execute\([^)]*(insert|update|delete|drop)"]
WRITE_CALL = re.compile(r"(to_csv|to_parquet|to_pickle|to_json|write_text|write_bytes|savefig|np\.save)\s*\(|open\s*\([^)]*['\"][wa]")


def log(*a):
    s = "%s %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), " ".join(str(x) for x in a))
    print(s, flush=True)
    try:
        with open(LOG, "a", encoding="utf-8") as f: f.write(s + "\n")
    except Exception: pass


def tg(text):
    try:
        import common as C
        C.tg(text)
    except Exception as ex:
        log("텔레그램 실패", repr(ex)[:200])


# ── 목록 ─────────────────────────────────────────────────────────────
def qload():
    if not Q.exists(): return []
    return [json.loads(l) for l in Q.read_text(encoding="utf-8").splitlines() if l.strip()]


def qsave(L):
    tmp = Q.with_suffix(".tmp"); tmp.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in L), encoding="utf-8"); tmp.replace(Q)


def prereg_text(x):
    L = ["# 밤 연구 사전 등록 %s — %s" % (x["id"], x["title"]), "", "- 등록: %s" % x["created"], "- 시킨 말: %s" % x.get("asked", ""),
         "- 방식: %s · %s %s" % (x["kind"], x.get("script") or "", " ".join(x.get("args") or [])), ""]
    if x["kind"] == "ask": L += ["- 재라는 것: %s" % x["ask"], ""]
    L += ["## 가설", "", x["hypothesis"], "", "## 합격선(보기 전에 정함 · 옮기지 말 것)", ""]
    L += ["- %s %s %s — %s" % (p["key"], p["op"], p["v"], p.get("label", "")) for p in x["pass"]]
    L += ["", "- 이날 밤부터: %s · 램 %sGB · 최대 %s분" % (x.get("not_before") or "바로", x.get("mem_gb"), x.get("max_min"))]
    return "\n".join(L) + "\n"


def add(path):
    x = json.loads(Path(path).read_text(encoding="utf-8"))
    for k in ("title", "asked", "kind", "hypothesis", "pass"):
        if not x.get(k): raise SystemExit("빠진 칸: %s (사전 등록에 가설·합격선 필수)" % k)
    if x["kind"] == "script":
        sp = (BASE / x["script"]).resolve()
        if not sp.exists() or BASE / "research" not in sp.parents: raise SystemExit("script 는 research/ 안 파일이어야 함: %s" % x["script"])
    elif x["kind"] == "ask":
        if not x.get("ask"): raise SystemExit("kind=ask 는 ask(무엇을 재라) 필수")
    else:
        raise SystemExit("kind 는 script | ask")
    L = qload()
    n = max([int(y["id"][1:]) for y in L if re.fullmatch(r"N\d+", y.get("id", ""))] + [0]) + 1
    x.update(id="N%04d" % n, created=time.strftime("%Y-%m-%d %H:%M"), status="queued",
             mem_gb=min(float(x.get("mem_gb") or MEM_MAX_GB), MEM_MAX_GB), max_min=int(x.get("max_min") or 120))
    t = prereg_text(x); f = RP / ("%s_prereg.md" % x["id"]); f.write_text(t, encoding="utf-8")
    x["prereg"] = str(f.relative_to(BASE)).replace("\\", "/"); x["prereg_sha"] = hashlib.sha256(t.encode("utf-8")).hexdigest()
    L.append(x); qsave(L)
    print("넣음", x["id"], x["title"], "→", x["prereg"])
    return x


# ── 지키기 ───────────────────────────────────────────────────────────
class _MS(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong), ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong), ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong), ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]


class _PMC(ctypes.Structure):
    _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong), ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t), ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]


def free_gb():
    m = _MS(); m.dwLength = ctypes.sizeof(_MS)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return m.ullAvailPhys / 1e9


def proc_gb(pid):
    h = ctypes.windll.kernel32.OpenProcess(0x1000 | 0x0010, False, pid)       # QUERY_LIMITED_INFORMATION | VM_READ
    if not h: return 0.0
    try:
        c = _PMC(); c.cb = ctypes.sizeof(_PMC)
        ok = ctypes.windll.psapi.GetProcessMemoryInfo(h, ctypes.byref(c), c.cb)
        return (c.PagefileUsage / 1e9) if ok else 0.0                           # 커밋 메모리(작업 집합보다 보수적)
    finally:
        ctypes.windll.kernel32.CloseHandle(h)


def snap():
    out = {}
    for g in GUARD:
        for f in BASE.glob(g):
            if f.is_file() and f.stat().st_size < 20e6: out[str(f)] = f.read_bytes()
    return out


def restore(before):
    """바뀐 실전 코드를 되돌린다 → 바뀐 파일 목록."""
    bad = []
    now = snap()
    for f, b in before.items():
        if now.get(f) != b:
            Path(f).write_bytes(b); bad.append(Path(f).name)
    for f in set(now) - set(before):                                            # 새로 생긴 실전 자리 파일은 이름만 알림(지우지 않음)
        bad.append(Path(f).name + "(새 파일)")
    return bad


def static_check(code):
    """AI 가 쓴 코드 금지어 · OUT 밖 쓰기 검사 → 문제 목록."""
    bad = [p for p in DENY if re.search(p, code, re.I)]
    ok = {"NIGHTLAB_OUT", "NIGHTLAB_DIR", "OUT_DIR", "OUT_JSON"}               # OUT 에서 나온 변수(한 줄 대입 사슬)만 쓰기 허용
    for _ in range(4):
        for m in re.finditer(r"^\s*([A-Za-z_]\w*)\s*=\s*(.+)$", code, re.M):
            if any(re.search(r"\b%s\b" % re.escape(k), m.group(2)) for k in ok): ok.add(m.group(1))
    pat = re.compile(r"\b(%s)\b" % "|".join(map(re.escape, sorted(ok))))
    for i, ln in enumerate(code.splitlines(), 1):
        if WRITE_CALL.search(ln) and not pat.search(ln):
            bad.append("%d줄 OUT 밖 쓰기: %s" % (i, ln.strip()[:80]))
    return bad


# ── 시간 ─────────────────────────────────────────────────────────────
def _t(h, m, base=None):
    b = base or dt.datetime.now()
    return b.replace(hour=h, minute=m, second=0, microsecond=0)


def deadline(now=None):
    now = now or dt.datetime.now()
    d = _t(*WIN_END, now)
    return d if now <= d else d + dt.timedelta(days=1)


def in_window(now=None):
    now = now or dt.datetime.now()
    return now >= _t(*WIN_START, now) or now < _t(*WIN_END, now)


def night_of(now=None):
    """이 밤의 날짜(YYYYMMDD) — 22:30 뒤면 오늘, 자정 뒤면 어제."""
    now = now or dt.datetime.now()
    return (now if now.hour >= 12 else now - dt.timedelta(days=1)).strftime("%Y%m%d")


# ── 돌리기 ───────────────────────────────────────────────────────────
ASK_SYS = """너는 한국 주식 연구 스크립트를 쓰는 일꾼이다. 아래 '재라는 것'을 재는 **파이썬 스크립트 하나만** 출력한다(설명·코드블록 표시 없이 코드만).
틀:
- 맨 위 docstring 에 무엇을 재는지 한국어로. 경로는 BASE = Path(r"%(base)s").
- 자료는 **읽기만**: data/m1/KR/day/YYYYMMDD.parquet(t·ts(UTC초)·o·h·l·c·v, 정규장 1분봉, 2026-10-02~) · research/cache/m1_daysum.parquet(t·d·o·c·val·pc…, 2022-12~2026-10 하루 요약)
  · research/cache/toss_daily_kr.pkl(ticker·date·to·th·tl·tc·tv 통합 일봉) · data/factory/auction/KR_YYYYMMDD_am.parquet(장전 호가 녹화, 2026-10-12~)
  · data/day/snap_YYYYMMDD.json(데이 유니버스 'all') · 그 밖은 쓰지 마라.
- 비용 0.23%%(사고팔기 합) 빼고 %%로. 같은 날 유니버스 평균(시장)도 같이 낸다.
- 결과는 **환경변수 NIGHTLAB_OUT 경로 하나에만** json 으로: {"metrics": {키: 숫자}, "table": "마크다운 표", "mode": "oc" 등,
  "trades": OUT_DIR 안 parquet 경로(칼럼 date·ticker·ret·amt20(억원)), "mkt": OUT_DIR 안 parquet(date·mkt)}.
  맨 위에 OUT_JSON = Path(os.environ["NIGHTLAB_OUT"]); OUT_DIR = Path(os.environ["NIGHTLAB_DIR"]). **파일 쓰기는 OUT_JSON·OUT_DIR(또는 그걸로 만든 변수)로만.**
- metrics 에는 반드시 합격선 키 %(keys)s 를 넣는다.
- 금지: 네트워크·주문·subprocess·파일 지우기·eval/exec·다른 모듈 import(numpy·pandas·json·math·pathlib·glob·os.environ 읽기만 됨). 램 5GB 안.
"""


def gen_script(x):
    import claude_sub as CS
    keys = ", ".join(p["key"] for p in x["pass"])
    prompt = ASK_SYS % dict(base=str(BASE), keys=keys) + "\n---\n재라는 것: %s\n가설: %s\n" % (x["ask"], x["hypothesis"])
    t0 = time.time()
    ok, out = CS.run(prompt, model="sonnet", timeout=900, effort="medium")
    try:
        with open(BASE / "data" / "factory" / "llm_usage.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "model": "구독(claude -p)", "task": "밤 연구(구독) 스크립트", "in": len(prompt),
                                "out": len(out or ""), "cw": 0, "cr": 0, "usd": 0.0, "sec": round(time.time() - t0, 1)}, ensure_ascii=False) + "\n")
    except Exception: pass
    if not ok: raise RuntimeError("구독 호출 실패: %s" % str(out)[:200])
    code = re.sub(r"^```(?:python)?\s*|\s*```\s*$", "", out.strip())
    f = JOBS / ("%s_gen.py" % x["id"]); f.write_text(code, encoding="utf-8")
    return f, code


def _f(v):
    if isinstance(v, bool) or not isinstance(v, (int, float)): return "-" if v is None else str(v)
    return "{:,.0f}".format(v) if abs(v) >= 1000 else ("%d" % v if float(v).is_integer() else "%.3f" % v)


def judge_pass(rules, m):
    ops = {">": lambda a, b: a > b, ">=": lambda a, b: a >= b, "<": lambda a, b: a < b, "<=": lambda a, b: a <= b, "==": lambda a, b: a == b}
    out = []
    for r in rules:
        v = m.get(r["key"])
        ok = isinstance(v, (int, float)) and v == v and ops[r["op"]](float(v), float(r["v"]))
        out.append(dict(r, got=v, ok=bool(ok)))
    return out


def run_one(x, dry=False):
    import pandas as pd
    t0 = time.time(); stamp = time.strftime("%Y%m%d_%H%M")
    res = dict(id=x["id"], title=x["title"], start=time.strftime("%Y-%m-%d %H:%M:%S"), dry=dry)
    t = prereg_text({k: v for k, v in x.items()})
    if hashlib.sha256(t.encode("utf-8")).hexdigest() != x.get("prereg_sha") or not (BASE / x.get("prereg", "-")).exists():
        res.update(status="blocked", why="사전 등록과 목록이 다름(합격선이 바뀜?) — 안 돌림"); return res
    outd = ST / "out" / x["id"]; outd.mkdir(parents=True, exist_ok=True)
    outj = outd / ("result_%s.json" % stamp)
    if x["kind"] == "ask":
        try:
            sp, code = gen_script(x)
        except Exception as ex:
            res.update(status="failed", why="스크립트 못 받음: %s" % str(ex)[:200]); return res
        bad = static_check(code)
        if bad:
            res.update(status="blocked", why="AI 스크립트 금지어: " + " · ".join(bad[:6]), script=str(sp)); return res
        cmd_script = sp
    else:
        cmd_script = BASE / x["script"]
    py = Path(sys.executable); py = py.with_name("python.exe") if py.name.lower() == "pythonw.exe" else py
    env = dict(os.environ, PYTHONIOENCODING="utf-8", NIGHTLAB_OUT=str(outj), NIGHTLAB_DIR=str(outd), NIGHTLAB_DRY="1" if dry else "")
    before = snap()
    lf = open(outd / ("log_%s.txt" % stamp), "w", encoding="utf-8")
    pr = subprocess.Popen([str(py), "-W", "ignore", str(cmd_script)] + list(x.get("args") or []), cwd=str(BASE), env=env, stdout=lf, stderr=subprocess.STDOUT,
                          creationflags=0x08000000 if os.name == "nt" else 0)
    lim = float(x.get("mem_gb") or MEM_MAX_GB); end = min(time.time() + 60 * int(x.get("max_min") or 120),
                                                          (deadline().timestamp() if not dry else time.time() + 3 * 3600))
    peak, why = 0.0, None
    while pr.poll() is None:
        g = proc_gb(pr.pid); peak = max(peak, g)
        if g > lim: why = "램 %.1fGB > %.0fGB — 죽임" % (g, lim)
        elif time.time() > end: why = "시간 넘김 — 죽임"
        if why:
            pr.kill(); pr.wait(30); break
        time.sleep(3)
    lf.close()
    changed = restore(before)
    res.update(peak_gb=round(peak, 2), sec=round(time.time() - t0), rc=pr.returncode, log=str(lf.name))
    if changed:
        res["guard"] = changed
        msg = "⚠ 밤 연구 %s 가 실전 파일을 바꿔 되돌림: %s" % (x["id"], ", ".join(changed[:6]))
        log(msg)
        if not dry: tg(msg)
    if why or pr.returncode != 0 or not outj.exists():
        tail = ""
        try: tail = Path(lf.name).read_text(encoding="utf-8")[-600:]
        except Exception: pass
        res.update(status="failed", why=why or ("종료 %s · 결과 파일 없음" % pr.returncode), tail=tail); return res
    J = json.loads(outj.read_text(encoding="utf-8"))
    m = J.get("metrics") or {}
    P = judge_pass(x["pass"], m)
    ok = all(p["ok"] for p in P)
    rt = None
    if J.get("trades"):
        try:
            import redteam as RT
            T = pd.read_parquet(J["trades"]); TW = pd.read_parquet(J["twin"]) if J.get("twin") else None
            mk = pd.read_parquet(J["mkt"]).set_index("date").mkt if J.get("mkt") else None
            R = RT.review("%s %s" % (x["id"], x["title"][:30]), T, mkt=mk, twin=TW, sel=tuple(J["sel"]) if J.get("sel") else None,
                          mode=J.get("mode", "oc"), conds=J.get("conds"), ai=not dry, tag="nightlab")
            rt = dict(verdict=R["verdict"], md=R["md"], red=[c["name"] for c in R["checks"] if c["level"] == "빨강"])
        except Exception as ex:
            rt = dict(verdict="못 함", why=repr(ex)[:200])
    cand = ok and rt is not None and rt.get("verdict") in ("통과", "주의")
    res.update(status="done", metrics=m, passed=P, ok=ok, redteam=rt, candidate=cand)
    L = ["# 밤 연구 %s — %s (%s%s)" % (x["id"], x["title"], res["start"], " · 마른 실행" if dry else ""), "",
         "**결과: %s**" % ("후보(합격 + 검토관 통과)" if cand else "합격 — 검토관이 막음" if ok else "불합격"), "",
         "- 시킨 말: %s" % x.get("asked", ""), "- 가설: %s" % x["hypothesis"], "- 사전 등록: %s" % x["prereg"], "",
         "## 합격선(사전 등록)", "", "| 키 | 기준 | 나온 값 | 합격 |", "|---|---|---|---|"]
    L += ["| %s | %s %s | %s | %s |" % (p.get("label") or p["key"], p["op"], p["v"], _f(p["got"]), "✅" if p["ok"] else "❌") for p in P]
    L += ["", "## 숫자(스크립트)", "", "| 키 | 값 |", "|---|---|"] + ["| %s | %s |" % (k, _f(v)) for k, v in m.items()]
    if J.get("table"): L += ["", J["table"]]
    if rt: L += ["", "## 적대적 검토관", "", "- 판정 **%s** %s" % (rt.get("verdict"), ("· 🔴 " + "·".join(rt.get("red") or [])) if rt.get("red") else ""), "- 자세히: %s" % rt.get("md", rt.get("why", ""))]
    L += ["", "- 램 최고 %.1fGB · %d초" % (peak, res["sec"])]
    f = RP / ("%s_%s%s.md" % (x["id"], stamp, "_dry" if dry else "")); f.write_text("\n".join(L) + "\n", encoding="utf-8")
    res["report"] = str(f)
    return res


def night(dry=False):
    now = dt.datetime.now()
    if not dry and not in_window(now):
        log("밤 시간(22:30~06:30) 아님 — 안 함"); return []
    if BUSY.exists() and time.time() - BUSY.stat().st_mtime < 9 * 3600 and not dry:
        log("다른 밤 연구가 도는 중(.busy) — 안 함"); return []
    L = qload()
    todo = [x for x in L if x.get("status") == "queued" and (dry or (x.get("not_before") or "0") <= night_of(now))]
    if not todo:
        log("대기 목록 빔(또는 아직 날짜 전) — 안 함"); return []
    out = []
    BUSY.write_text(str(os.getpid()))
    try:
        for x in todo:
            now = dt.datetime.now()
            if not dry:
                if not in_window(now): log("밤 시간 끝 — 남은 것 다음 밤"); break
                if (deadline(now) - now).total_seconds() < 60 * min(int(x.get("max_min") or 120), 30):
                    log("06:30 까지 시간 부족 — %s 다음 밤" % x["id"]); break
                while _t(*FACTORY_GAP[0], now) <= now < _t(*FACTORY_GAP[1], now):
                    time.sleep(60); now = dt.datetime.now()
            fg = free_gb()
            if fg < FREE_MIN_GB:
                log("남은 램 %.1fGB < %.0fGB — %s 미룸" % (fg, FREE_MIN_GB, x["id"])); continue
            log("돌림", x["id"], x["title"], "(마른 실행)" if dry else "")
            r = run_one(x, dry=dry)
            log("끝", x["id"], r.get("status"), r.get("why") or "", r.get("report") or "")
            out.append(r)
            with open(RUNS, "a", encoding="utf-8") as f: f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
            if not dry:
                L = qload()
                for y in L:
                    if y["id"] == x["id"]:
                        y.update(status=r["status"] if r["status"] in ("done", "blocked") else ("failed" if y.get("tries", 0) >= 1 else "queued"),
                                 tries=y.get("tries", 0) + 1, last=r.get("start"), result=dict(ok=r.get("ok"), candidate=r.get("candidate"),
                                 why=r.get("why"), report=r.get("report"), redteam=(r.get("redteam") or {}).get("verdict")))
                qsave(L)
    finally:
        try: BUSY.unlink()
        except Exception: pass
    return out


def brief(since_hours=10):
    """지난밤 결과 텔레그램 한 줄(돌린 게 없으면 조용)."""
    if not RUNS.exists(): return
    cut = (dt.datetime.now() - dt.timedelta(hours=since_hours)).strftime("%Y-%m-%d %H:%M:%S")
    R = [json.loads(l) for l in RUNS.read_text(encoding="utf-8").splitlines() if l.strip()]
    R = [r for r in R if not r.get("dry") and r.get("start", "") >= cut]
    if not R: return
    def one(r):
        if r.get("status") != "done": return "%s %s(%s)" % (r["id"], "막힘" if r.get("status") == "blocked" else "실패", (r.get("why") or "")[:40])
        rt = r.get("redteam") or {}
        s = "후보" if r.get("candidate") else "합격·검토관 막음" if r.get("ok") else "불합격"
        return "%s %s%s" % (r["id"], s, (" 🔴" + "·".join(rt.get("red")[:2])) if rt.get("red") else "")
    tg("🌙 밤 연구 %d건: %s" % (len(R), " / ".join(one(r) for r in R)))


if __name__ == "__main__":
    a = sys.argv[1:]
    try:
        if a[:1] == ["add"] and len(a) > 1: add(a[1])
        elif a[:1] == ["night"]:
            for r in night(dry="--dry" in a):
                print(json.dumps({k: r.get(k) for k in ("id", "status", "why", "ok", "candidate", "redteam", "report", "peak_gb", "sec", "guard")}, ensure_ascii=False, default=str))
        elif a[:1] == ["brief"]: brief()
        elif a[:1] == ["list"]:
            for x in qload(): print(x["id"], x["status"], x.get("not_before", ""), x["title"], (x.get("result") or {}))
        else: print(__doc__)
    except SystemExit: raise
    except Exception as ex:
        log("실패:", repr(ex)[:400])
        if a[:1] == ["night"] and "--dry" not in a: tg("⚠ 밤 연구 오류: %s" % str(ex)[:200])
        raise
