# -*- coding: utf-8 -*-
"""연구 패널 매일 잇기 (2026-11-10 사용자 "11월까지 늘려주고, 매일 알아서 수집되게").

kr_scan.pkl · panel_kp.pkl · panel_kq.pkl 을 서버에 이미 모이는 재료(KRX 공매도 잔고·KIS·1분봉·월별 CSV·토스·DART)로 어제까지 잇는다.
네트워크 호출 없음. 실제 일은 research/panel_refresh_1031.py 의 단계들이 한다(10-31 감사 통과한 방식 그대로):
    raw → kr_lite → patch_kr → verify2(앞부분이 옛 판과 같은지) → audit_kr2(오염 14항목)
전부 통과해야만 본이름 파일을 새 판으로 바꿔 끼운다. 하나라도 걸리면 옛 파일 그대로 두고 텔레그램.
바탕은 늘 2026-08-28 까지인 옛 판(*_0828.pkl — 처음 바꿔 끼울 때 본이름을 그렇게 옮겨 둔다)이라 날마다 08-29~어제를 통째로 다시 만든다(오류가 쌓이지 않는다).

⚠ 무겁다: 단계 하나가 패널을 통째로 읽어 RAM 약 8GB 를 쓴다. 남은 RAM 이 MIN_FREE_GB 아래면 그날은 건너뛴다. 단계는 하나씩 따로 띄운다.
    python research/panel_daily.py            # 새 날이 있을 때만
    python research/panel_daily.py --force    # 새 날이 없어도
    python research/panel_daily.py --noswap   # 만들고 검사만(바꿔 끼우지 않음)
기록 data/panel_daily/run.log · 단계 출력 data/panel_daily/steps_YYYYMMDD.log · 상태 data/panel_daily/state.json
"""
import ctypes, json, os, re, sqlite3, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent; DATA = BASE / "data"
OUT = DATA / "panel_daily"; OUT.mkdir(parents=True, exist_ok=True)
WORK = ROOT / "cache" / "panel_refresh_1031"
FILES = ("kr_scan.pkl", "panel_kp.pkl", "panel_kq.pkl")
STEPS = ("raw", "kr_lite", "patch_kr", "verify2", "audit_kr2")
MIN_FREE_GB = 12.0
LOCK = OUT / "lock"
if sys.stdout is not None:
    try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass


def log(*a):
    s = time.strftime("%Y-%m-%d %H:%M:%S ") + " ".join(str(x) for x in a)
    with open(OUT / "run.log", "a", encoding="utf-8") as f: f.write(s + "\n")
    if sys.stdout is not None:
        try: print(s, flush=True)
        except Exception: pass


def free_gb():
    class MS(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong), ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong), ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong), ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
    m = MS(); m.dwLength = ctypes.sizeof(MS); ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return m.ullAvailPhys / 2 ** 30


def tell(msg):
    log("알림:", msg)
    try:
        sys.path.insert(0, str(BASE))
        import day_alert as D
        D.telegram("⚠ 연구 패널 잇기: " + msg)
    except Exception as ex:
        log("텔레그램 못 보냄", repr(ex)[:120])


def fetch_csv():
    """월별 CSV(코스피 시가·고저·수급의 재료)는 GitHub 수집이 저장소에 올린다 — 서버 작업본은 누가 pull 해야 새로워지므로 origin/main 것을 사본으로 받아 둔다.
    작업 폴더 파일은 안 건드린다(git fetch + git show). 실패해도 작업본 CSV 로 그냥 간다."""
    try:
        r = subprocess.run(["git", "fetch", "-q", "origin", "main"], cwd=str(BASE), capture_output=True, text=True, timeout=180, creationflags=0x08000000)
        if r.returncode != 0: log("git fetch 실패:", (r.stderr or "")[:150]); return
        now = time.localtime(); ms = {time.strftime("%Y-%m", now), time.strftime("%Y-%m", time.localtime(time.time() - 35 * 86400))}
        WORK.mkdir(parents=True, exist_ok=True)
        for m in sorted(ms):
            r = subprocess.run(["git", "show", "origin/main:data/%s.csv" % m], cwd=str(BASE), capture_output=True, timeout=120, creationflags=0x08000000)
            if r.returncode == 0 and len(r.stdout) > 1000: (WORK / ("csv_%s.csv" % m)).write_bytes(r.stdout)
        log("월별 CSV 사본 받음", sorted(ms))
    except Exception as ex:
        log("월별 CSV 사본 받기 실패", repr(ex)[:150])


def last_material_day():
    c = sqlite3.connect(f"file:{DATA / 'kis' / 'market.db'}?mode=ro", uri=True, timeout=60)
    d = c.execute("SELECT max(date) FROM short_sale").fetchone()[0]; c.close()
    return d


def main():
    force, noswap = "--force" in sys.argv, "--noswap" in sys.argv
    st_f = OUT / "state.json"
    st = json.loads(st_f.read_text(encoding="utf-8")) if st_f.exists() else {}
    end = last_material_day()
    if not force and st.get("end") == end:
        log("새 날 없음(재료 끝 %s) — 건너뜀" % end); return 0
    if LOCK.exists() and time.time() - LOCK.stat().st_mtime < 6 * 3600:
        log("이미 도는 중(lock) — 건너뜀"); return 0
    fg = free_gb()
    if fg < MIN_FREE_GB:
        tell("남은 RAM %.1fGB(< %.0f) — 오늘은 건너뜀" % (fg, MIN_FREE_GB)); return 1
    LOCK.write_text(str(os.getpid())); t0 = time.time()
    try:
        fetch_csv()
        steplog = OUT / ("steps_%s.log" % time.strftime("%Y%m%d"))
        py = str(Path(sys.executable).with_name("python.exe"))      # 예약 작업은 pythonw 로 뜬다 — 단계는 출력이 파일로 가야 하니 python.exe 로
        for s in STEPS:
            fg = free_gb()
            if fg < MIN_FREE_GB * 0.75:
                tell("단계 %s 앞에서 남은 RAM %.1fGB — 멈춤(옛 파일 그대로)" % (s, fg)); return 1
            ts = time.time()
            with open(steplog, "a", encoding="utf-8") as f:
                f.write("\n########## %s %s ##########\n" % (s, time.strftime("%H:%M:%S"))); f.flush()
                r = subprocess.run([py, "-X", "utf8", str(ROOT / "panel_refresh_1031.py"), s], stdout=f, stderr=subprocess.STDOUT, cwd=str(BASE), creationflags=0x08000000)
            log("단계 %s 끝 %.1f분 · 코드 %d · 남은 RAM %.1fGB" % (s, (time.time() - ts) / 60, r.returncode, free_gb()))
            if r.returncode != 0:
                tell("단계 %s 실패(코드 %d) — 옛 파일 그대로. %s" % (s, r.returncode, steplog.name)); return 1
        # 검사 ① 앞부분(2026-08-28 까지)이 옛 판과 같은가 — 행 수가 같고, 선행 열(buy·gap·n*) 말고 달라진 열이 없어야 한다
        v = json.loads((WORK / "verify2.json").read_text(encoding="utf-8"))
        FW = re.compile(r"^(n\d+|buy|gap)$")                      # 선행 열은 달라져도 된다 — 미완 거래에 진짜 값이 들어가거나, 정지됐다 재개된 종목의 옛 '끝 종가 청산' 값을 빈칸으로(patch_kr ②)
        bad = {k: [c for c in (x.get("다른열") or []) if not FW.match(c)] for k, x in v.items()}
        bad = {k: c for k, c in bad.items() if c}
        if any(x.get("rows_old") != x.get("rows_new") for x in v.values()): bad["행 수"] = ["옛 구간 행 수가 다름"]
        if set(v) != set(FILES) or bad:
            tell("앞부분 대조 어긋남 %s — 옛 파일 그대로" % (json.dumps(bad, ensure_ascii=False)[:200] or sorted(v))); return 1
        # 검사 ② 오염 감사 — 이번 실행의 audit_kr2 출력에 ❌ 가 없어야 한다
        txt = steplog.read_text(encoding="utf-8", errors="replace"); au = txt[txt.rindex("########## audit_kr2"):]
        nbad, nok = au.count("❌"), au.count("✅")
        if nbad or nok < 5:
            tell("오염 감사 ❌ %d · ✅ %d — 옛 파일 그대로" % (nbad, nok)); return 1
        # 검사 ③ 새 파일이 이번에 만들어졌고 너무 작지 않은가
        for fn in FILES:
            new = DATA / fn.replace(".pkl", "_new.pkl"); live = DATA / fn
            if not new.exists() or new.stat().st_mtime < t0 or new.stat().st_size < live.stat().st_size * 0.97:
                tell("%s 가 이상함(없음·옛것·작음) — 옛 파일 그대로" % new.name); return 1
        m = re.findall(r"새 거래일 (\d+)일 (\d{8})~(\d{8})", txt)
        newend = m[-1][2] if m else end
        if noswap:
            log("검사 통과 · 새 판 끝 %s · --noswap 이라 바꿔 끼우지 않음 · %.0f분" % (newend, (time.time() - t0) / 60)); return 0
        for fn in FILES:
            new = DATA / fn.replace(".pkl", "_new.pkl"); live = DATA / fn; b0 = DATA / fn.replace(".pkl", "_0828.pkl")
            for k in range(10):
                try:
                    if not b0.exists(): os.replace(live, b0)        # 처음 한 번 — 옛 판(08-28)을 바탕으로 남긴다
                    os.replace(new, live); break
                except PermissionError:
                    time.sleep(30)                                  # 누가 읽는 중 — 기다렸다 다시
            else:
                tell("%s 바꿔 끼우기 실패(파일 사용 중) — 일부만 바뀌었을 수 있음, 확인 필요" % fn); return 1
        st.update(end=end, panel_end=newend, at=time.strftime("%Y-%m-%d %H:%M:%S"), minutes=round((time.time() - t0) / 60, 1))
        st_f.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
        log("바꿔 끼움 · 패널 끝 %s · %.0f분" % (newend, (time.time() - t0) / 60)); return 0
    finally:
        try: LOCK.unlink()
        except Exception: pass


if __name__ == "__main__":
    try: sys.exit(main())
    except Exception as ex:
        tell("오류 %s" % repr(ex)[:200]); sys.exit(1)
