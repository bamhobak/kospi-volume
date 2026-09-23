# -*- coding: utf-8 -*-
"""연구용 데이터 매일 갱신 — 신용잔고·공매도·밸류에이션·공매도잔고·투자자 11분할.

왜 이 PC 에서 도는가: 이 자료들은 0.6~1.2GB 짜리 로컬 DB 에 쌓인다. GitHub Actions 에는
그 DB 가 없고, 매번 2.5GB 를 캐시로 오르내리게 하면 수집 워크플로가 너무 무거워진다.
**사이트·텔레그램 알림이 쓰는 실전 데이터는 이미 CI 가 매일 받는다.** 여기서 채우는 건
백테스트·연구용 이력이라 하루이틀 밀려도 실전에 지장이 없고, 전부 재개 가능해서
PC 가 꺼져 있던 날은 다음 실행 때 알아서 따라잡는다.

순서(전부 순차 — KRX 는 동시 실행하면 차단된다):
  1) KIS 신용잔고   최근 N일 · 코스피/코스닥      → data/kis/market.db · credit
  2) KIS 공매도     최근 N일 · 코스피/코스닥      → data/kis/market.db · short_sale
  3) KRX 밸류에이션  못 받은 날짜                 → data/krx_daily.db · fundamental
  4) KRX 공매도잔고  못 받은 날짜                 → data/krx_daily.db · short_balance
  5) KRX 11분할     최근 N일 · 날짜별            → data/investor.db · flow11

사용: python run_daily_research.py [--days 10] [--only 1,3]
등록: schtasks 로 매일 20:30 실행(아래 '자동 등록' 참조)
"""
import io, os, subprocess, sys, time
from pathlib import Path
# 자식 출력에 깨진 글자가 섞여도 죽지 않게 UTF-8 로 맞춘다.
# ⚠ 작업 스케줄러가 pythonw.exe 로 띄우면 콘솔 핸들이 없어 sys.stdout/stderr 가 **None** 이다.
#    예전엔 여기서 그냥 sys.stdout.reconfigure(...) 를 불러 AttributeError 로 첫 줄에서 즉사했고,
#    로그 한 줄도 못 남겨 16일치(2026-09-06~21) 갱신이 조용히 통째로 빠졌다.
for _name in ("stdout", "stderr"):
    _f = getattr(sys, _name, None)
    if _f is None:
        setattr(sys, _name, io.open(os.devnull, "w", encoding="utf-8"))
    else:
        try:
            _f.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

BASE = Path(__file__).parent
arg = lambda k, d: sys.argv[sys.argv.index(k)+1] if k in sys.argv else d
DAYS = arg("--days", "10")
ONLY = {int(x) for x in arg("--only", "").split(",") if x.strip().isdigit()}
LOG = BASE / "daily_research.log"
PY = sys.executable

import datetime as _dt
SINCE180 = (_dt.date.today() - _dt.timedelta(days=180)).strftime("%Y%m%d")
STEPS = [
    (1, "신용잔고 코스피",   ["collect_kis.py", "credit", "--days", DAYS, "--market", "KOSPI",  "--workers", "4"]),
    (1, "신용잔고 코스닥",   ["collect_kis.py", "credit", "--days", DAYS, "--market", "KOSDAQ", "--workers", "4"]),
    (2, "공매도 코스피",     ["collect_kis.py", "short",  "--days", DAYS, "--market", "KOSPI",  "--workers", "4"]),
    (2, "공매도 코스닥",     ["collect_kis.py", "short",  "--days", DAYS, "--market", "KOSDAQ", "--workers", "4"]),
    (3, "밸류에이션",        ["collect_krx_daily.py", "fund", "--gap", "1.6"]),
    (4, "공매도잔고",        ["collect_krx_daily.py", "shortbal", "--gap", "1.6"]),
    # 4b) 공매도 거래량. 백필로 2005~ 를 만들어 놓고 **일일 갱신에는 넣지 않아** 2026-09-04 에
    #     멈춰 있었다(17일). shortbal 과 같은 도구라 빠질 이유가 없었다.
    (4, "공매도거래량",      ["collect_krx_daily.py", "shortvol", "--gap", "1.6"]),
    (5, "투자자 11분할",     ["collect_investor_daily.py", "--days", DAYS, "--gap", "1.8"]),
    # 6) DB 이력은 수정주가로 백필됐고 매일은 원주가로 붙는다. 액면변경이 있으면 경계에서
    #    가짜 점프가 생긴다(2026-06-04 코스닥 88종목이 1/5~1/10 로 기록됐던 사고).
    #    최근 반년 점프 종목만 네이버 수정주가와 대조해 어긋나면 그 종목을 통째로 덮어쓴다.
    (6, "주가 기준 이음새 점검", ["find_seams.py", "--since", SINCE180, "--fix"]),
    # 7) 토스(투자자 11분할·프로그램매매·대차잔고 등). CI 에도 같은 단계가 있지만
    #    러너에서는 2026-09-05 부터 전 종목 403 이 떨어져 17일치가 통째로 빠져 있었다
    #    (continue-on-error 라 초록불이었다). 로컬에서는 같은 시각에 멀쩡히 받아진다.
    #    KRX 가 아니라 토스 서버라 위 단계들과 서비스가 겹치지 않는다.
    (7, "토스 수급·프로그램매매", ["collect_toss.py", "--days", "3"]),
    # 8) 지수 편입(월초 스냅샷). 지금까지 매달 돌리는 주체가 아무도 없었고 backfill_aux.py 안에만
    #    들어 있었다 — 2026-09-01 이후로 멈춰 있었다. done(지수,날짜) 단위라 받을 게 없으면
    #    즉시 끝나므로 매일 걸어 두면 매달 1일이 저절로 채워진다.
    (8, "지수 편입 월초 스냅샷", ["collect_index_members.py"]),
    # 9) DB 백업 — D:\kospi_backup 에 최근 2일치. 2026-09-20~22 PC 가 7번 죽어 toss.db 가 통째로
    #    깨졌는데 백업이 없었다. SQLite 백업 API 라 원본이 깨져 있으면 여기서 실패로 드러난다.
    (9, "DB 백업", ["backup_dbs.py"]),
]

def clean(t):
    """자식 프로세스 출력에 섞인 복원 불가 문자를 지운다(예전에 여기서 죽었다)."""
    return "".join(ch for ch in (t or "") if ch != "�")

def say(m):
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {clean(m)}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f: f.write(line + "\n")

# 과거 백필이 돌고 있으면 비켜준다 — KRX 를 동시에 두드리면 차단된다.
LOCK = BASE / "data" / ".backfill_lock"
if LOCK.exists() and time.time() - LOCK.stat().st_mtime < 36*3600:
    say(f"과거 백필 진행 중({LOCK.name}) — 오늘 갱신은 건너뛴다. 백필이 같은 자료를 더 넓게 받는다.")
    sys.exit(0)

# 이미 한 벌이 돌고 있으면 비켜준다(밀린 날을 손으로 따라잡는 중에 20:30 예약이 겹치는 경우).
# 작업 스케줄러의 MultipleInstances 설정은 '예약 실행끼리' 만 막아 준다 — 손으로 띄운 것은 못 막는다.
# 판정은 mtime 이 아니라 **파일 핸들**로 한다: 돌고 있는 쪽이 락 파일을 열어 쥐고 있으면
# 윈도우에서는 지울 수 없다(PermissionError). 죽은 프로세스가 남긴 락은 지워지므로 그냥 이어받는다.
RUN_LOCK = BASE / "data" / ".research_running"
def hold_run_lock():
    try:
        if RUN_LOCK.exists():
            try:
                RUN_LOCK.unlink()
            except PermissionError:
                return None                      # 살아 있는 인스턴스가 쥐고 있다
    except Exception:
        return None
    try:
        f = io.open(RUN_LOCK, "w", encoding="utf-8")
        f.write("%s %s" % (os.getpid(), time.strftime("%Y-%m-%d %H:%M:%S"))); f.flush()
        return f
    except Exception:
        return None

_run_lock = hold_run_lock()
if _run_lock is None and RUN_LOCK.exists():
    try: who = RUN_LOCK.read_text(encoding="utf-8").strip()
    except Exception: who = "?"
    say(f"이미 실행 중({who}) — 이번 실행은 건너뛴다. KRX 를 동시에 두드리면 차단된다.")
    sys.exit(0)

def release_run_lock():
    if _run_lock is None: return
    try: _run_lock.close()
    except Exception: pass
    try: RUN_LOCK.unlink()
    except Exception: pass
import atexit; atexit.register(release_run_lock)

say(f"=== 연구용 일일 갱신 시작 (최근 {DAYS}일) ===")
t0 = time.time(); fail = []
for no, name, cmd in STEPS:
    if ONLY and no not in ONLY: continue
    say(f"[{no}] {name} 시작")
    t = time.time()
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    r = subprocess.run([PY, "-u", *cmd], cwd=str(BASE), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env)
    tail = "\n".join((r.stdout or "").strip().splitlines()[-2:])
    if r.returncode == 0:
        say(f"[{no}] {name} 완료 ({(time.time()-t)/60:.1f}분) {tail[:200]}")
    else:
        fail.append(name)
        err = "\n".join((r.stderr or "").strip().splitlines()[-3:])
        say(f"[{no}] {name} 실패 rc={r.returncode} ({(time.time()-t)/60:.1f}분)\n{err[:400]}")
say(f"=== 끝 ({(time.time()-t0)/60:.1f}분) · 실패 {len(fail)}건 " + (", ".join(fail) if fail else "없음") + " ===")

# 결과 요약
import sqlite3
for db, tabs in (("data/kis/market.db", ("credit", "short_sale")),
                 ("data/krx_daily.db", ("fundamental", "short_balance")),
                 ("data/investor.db", ("flow11",))):
    p = BASE / db
    if not p.exists(): continue
    c = sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=60)
    for t in tabs:
        try:
            n, a, b = c.execute(f"select count(*),min(date),max(date) from {t}").fetchone()
            say(f"  {t:<14} {n:>10,}행  {a}~{b}")
        except Exception as e: say(f"  {t}: {str(e)[:60]}")
    c.close()

# 끝에 신선도를 스스로 점검한다 — 단계가 rc=0 으로 끝나도 '받을 게 없어서' 였을 수 있다.
# 내부자 쪽 작업도 같은 점검을 부르므로, 이 작업이 통째로 죽어도 그쪽이 알아챈다(서로 감시).
try:
    h = subprocess.run([PY, "-u", "research_health.py"], cwd=str(BASE), capture_output=True,
                       text=True, encoding="utf-8", errors="replace",
                       env={**os.environ, "PYTHONIOENCODING": "utf-8"}, timeout=600)
    for ln in (h.stdout or "").strip().splitlines():
        say(clean(ln))
except Exception as e:
    say("신선도 점검 실패: %r" % (e,))

sys.exit(1 if fail else 0)
