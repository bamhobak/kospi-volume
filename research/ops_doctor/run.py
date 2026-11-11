# -*- coding: utf-8 -*-
"""점검 의사 실행기 — 2026-11-12 사용자 "점검 현황을 매일 보고 잘 안 돌아가거나 문제 있는 거 체크하고 문제 찾아서 수정하게 해줘".

매일 10:20·17:40(예약 \\BamhobakFactory\\OpsDoctor): 점검 현황 자료를 만들어 넘기고 구독 클로드(claude -p, 1년 토큰)를 이 폴더에서 깨운다.
클로드는 research/ops_doctor/PROMPT.md 대로 문제를 찾고, 안전한 범위(연구·점검·수집 코드, 매매 아닌 작업 다시 돌리기)만 고치고, data/ops_doctor/last.json 에 남긴다.
안전장치(실행기가 한다 — 클로드 말을 믿지 않는다):
  · 실전 시간대(08:00~09:10 · 15:10~15:40 · 19:40~20:10)엔 시작 안 함 · 한 번에 하나(잠금) · 45분 넘으면 끔
  · 매매·사이트·비밀·원장 파일을 돌리기 전에 찍어 두고, 바뀌었으면 **되돌리고** 텔레그램
  · 끝나고 selftest — 실패면 텔레그램
  · last.json 을 읽어 문제·고침·사용자 결정이 있을 때만 텔레그램 한 줄 · 점검 현황 다시 올림
    python research/ops_doctor/run.py [--now]  (--now = 시간대 검사 건너뜀, 손으로 돌릴 때)
"""
import datetime as dt, glob, hashlib, json, os, subprocess, sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parent; RES = HERE.parent; BASE = RES.parent
sys.path.insert(0, str(BASE)); sys.path.insert(0, str(RES)); sys.path.insert(0, str(RES / "factory"))
OUT = BASE / "data" / "ops_doctor"; OUT.mkdir(parents=True, exist_ok=True)
LOG = OUT / "run.log"
if sys.stdout is None or sys.stderr is None:
    sys.stdout = sys.stderr = open(LOG, "a", encoding="utf-8", buffering=1)

PY = r"C:\Users\bamhobak\AppData\Local\Python\pythoncore-3.14-64\python.exe"
BUSY = [((8, 0), (9, 10)), ((15, 10), (15, 40)), ((19, 40), (20, 10))]
LIMIT = 45 * 60
# 쓸 수 있는 도구만 적는다(모든 권한 모드는 안 씀 — 2026-11-12 자동 모드 안전장치 판단). 읽기·찾기·고치기 + 파이썬 실행·git 올리기·예약 작업 '다시 시작'·상태 보기.
ALLOW = ["Read", "Grep", "Glob", "Edit", "Write",
         "Bash(C:/Users/bamhobak/AppData/Local/Python/pythoncore-3.14-64/python.exe:*)", "Bash(python:*)", "Bash(PYTHONIOENCODING=utf-8 *)",
         "Bash(git status:*)", "Bash(git diff:*)", "Bash(git log:*)", "Bash(git add:*)", "Bash(git commit:*)", "Bash(git pull:*)", "Bash(git push origin main:*)",
         "Bash(tail:*)", "Bash(head:*)", "Bash(ls:*)", "Bash(wc:*)", "Bash(grep:*)", "Bash(cat:*)",
         "Bash(powershell -NoProfile -Command Get-ScheduledTask*)", "Bash(powershell -NoProfile -Command Start-ScheduledTask*)"]
# 기본은 '보고만' — 읽기·찾기·상태 보기와 결과 파일 쓰기만. 고치기(위 ALLOW)는 사용자가 켤 때만: data/ops_doctor/FIX_ON 파일이 있으면.
#   (2026-11-12 자동 모드 안전장치가 '사람 확인 없이 실전 서버를 고치는 에이전트'를 막음 → 사용자가 정하게 함)
ALLOW_RO = ["Read", "Grep", "Glob", "Write(data/ops_doctor/**)", "Edit(data/ops_doctor/**)",
            "Bash(git status:*)", "Bash(git diff:*)", "Bash(git log:*)", "Bash(tail:*)", "Bash(head:*)", "Bash(ls:*)", "Bash(wc:*)", "Bash(grep:*)", "Bash(cat:*)",
            "Bash(powershell -NoProfile -Command Get-ScheduledTask*)"]
RO_NOTE = """

## 지금은 '보고만' 모드
고치지 마라(코드 수정·작업 다시 돌리기·커밋 전부 안 됨 — 도구도 막혀 있다). 대신 문제마다 원인과 **고칠 방법을 구체적으로**(어느 파일 몇째 줄을 어떻게, 어느 작업을 언제 다시 돌릴지) 'user' 칸에 적어라 — 사용자가 클로드 창에서 '고쳐줘' 하면 그대로 고친다. 결과 파일(data/ops_doctor/)만 써라."""
DENY = ["Bash(git push --force*)", "Bash(git push -f*)", "Bash(git reset*)", "Bash(git rebase -i*)", "Bash(rm -rf*)",
        "Bash(powershell -NoProfile -Command Unregister-ScheduledTask*)", "Bash(powershell -NoProfile -Command Disable-ScheduledTask*)",
        "WebFetch", "WebSearch"]
PROTECT = ["autotrade.py", "day_alert.py", "nxt_pre.py", "nxt_shadow.py", "day_aerr.py", "day_exec.py", "collect_m1.py", "toss.py", "collect_toss.py",
           "index.html", "assets/*.html", "assets/*.js", "supabase/functions/*/index.ts", ".github/workflows/*.yml", ".env", ".env.*",
           "research/ops_doctor/run.py", "research/ops_doctor/PROMPT.md"]
# 원장·계좌 자료(ledger 등)는 실전 작업이 같은 때 정상으로 쓸 수 있어 되돌리지 않는다(PROMPT 로 금지만) — 코드·사이트·비밀만 찍어 둔다


def log(*a):
    print(dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), *a, flush=True)


def tg(msg):
    try:
        import day_alert as D
        D.telegram(msg)
    except Exception as ex:
        log("텔레그램 실패", repr(ex)[:200])


def busy_now():
    n = dt.datetime.now(); hm = (n.hour, n.minute)
    return any(a <= hm < b for a, b in BUSY)


def snap():
    S = {}
    for pat in PROTECT:
        for f in glob.glob(str(BASE / pat)):
            p = Path(f)
            if p.is_file(): S[str(p)] = p.read_bytes()
    return S


def restore(S, stamp):
    """바뀐 보호 파일을 되돌린다 — 그 사이 사람이 고친 것일 수도 있어 바뀐 내용은 data/ops_doctor/reverted_<시각>/ 에 남긴다."""
    bad = []
    for f, b in S.items():
        p = Path(f)
        if not p.exists() or p.read_bytes() != b:
            rel = str(p.relative_to(BASE))
            if p.exists():
                keep = OUT / ("reverted_%s" % stamp) / rel; keep.parent.mkdir(parents=True, exist_ok=True); keep.write_bytes(p.read_bytes())
            p.write_bytes(b); bad.append(rel)
    return bad


def main():
    now_ok = "--now" in sys.argv
    if busy_now() and not now_ok:
        log("실전 시간대 — 안 함"); return
    lock = OUT / ".lock"
    if lock.exists() and time.time() - lock.stat().st_mtime < LIMIT + 600:
        log("이미 도는 중 — 안 함"); return
    lock.write_text(str(os.getpid()), encoding="utf-8")
    try:
        import ops_status
        ctx = ops_status.build()
        stamp = dt.datetime.now().strftime("%Y%m%d_%H%M")
        cf = OUT / ("ctx_%s.json" % stamp)
        cf.write_text(json.dumps(ctx, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        for old in sorted(OUT.glob("ctx_*.json"))[:-14]: old.unlink()
        lastf = OUT / "last.json"
        prev = lastf.read_bytes() if lastf.exists() else None
        FIX = (OUT / "FIX_ON").exists()
        prompt = (HERE / "PROMPT.md").read_text(encoding="utf-8") + ("" if FIX else RO_NOTE) + (
            "\n\n## 오늘 자료\n지금 %s. 점검 현황 자료: %s (예약 작업 %d개). 직전 점검 결과: data/ops_doctor/last.json(있으면 — 어제 고친 게 다시 고장 났는지 봐라).\n"
            "다 끝나면 data/ops_doctor/last.json 과 md 를 꼭 써라." % (dt.datetime.now().strftime("%Y-%m-%d %H:%M"), cf, len(ctx.get("tasks") or [])))
        import claude_sub
        cli = claude_sub.find_cli()
        if not cli:
            tg("⚠ 점검 의사: claude 실행 파일 없음"); return
        S = snap()
        args = [cli, "-p", "--output-format", "text", "--model", "opus", "--effort", "high",
                "--allowedTools", ",".join(ALLOW if FIX else ALLOW_RO), "--disallowedTools", ",".join(DENY)]
        t0 = time.time()
        try:
            r = subprocess.run(args, input=prompt, capture_output=True, text=True, encoding="utf-8", errors="replace",
                               timeout=LIMIT, cwd=str(BASE), creationflags=0x08000000)
            out, rc = (r.stdout or "") + (r.stderr or ""), r.returncode
        except subprocess.TimeoutExpired:
            out, rc = "시간 초과", -1
        (OUT / ("out_%s.txt" % stamp)).write_text(out, encoding="utf-8")
        for old in sorted(OUT.glob("out_*.txt"))[:-14]: old.unlink()
        log("클로드 끝 rc=%s %.0f분" % (rc, (time.time() - t0) / 60))
        bad = restore(S, stamp)
        if bad:
            tg("⚠ 점검 의사가 손대면 안 되는 파일을 바꿔서 되돌림: %s (바뀐 내용은 data/ops_doctor/reverted_%s)" % (", ".join(bad[:6]), stamp))
        st = subprocess.run([PY, str(BASE / "selftest.py")], capture_output=True, text=True, encoding="utf-8", errors="replace",
                            cwd=str(BASE), env=dict(os.environ, PYTHONIOENCODING="utf-8"), timeout=900, creationflags=0x08000000)
        st_ok = "전체 통과" in (st.stdout or "")
        if not st_ok: tg("⚠ 점검 의사 뒤 selftest 실패 — 확인 필요")
        J = None
        if lastf.exists() and lastf.read_bytes() != prev:
            try: J = json.loads(lastf.read_text(encoding="utf-8"))
            except Exception as ex: log("last.json 못 읽음", repr(ex)[:200])
        if J is None:
            tg("⚠ 점검 의사: 결과를 안 남김(rc=%s) — data/ops_doctor/out_%s.txt" % (rc, stamp)); return
        J["selftest"] = st_ok; J["reverted"] = bad; J["rc"] = rc; J["mode"] = "fix" if FIX else "report"
        lastf.write_text(json.dumps(J, ensure_ascii=False, indent=1), encoding="utf-8")
        nf, nx, nu = len(J.get("found") or []), len(J.get("fixed") or []), len(J.get("user") or [])
        if nf or nx or nu:
            lines = ["🩻 <b>점검 의사</b>%s 문제 %d · 고침 %d · 결정 %d" % ("" if FIX else "(보고만)", nf, nx, nu), J.get("summary", "")]
            lines += ["🔧 " + (x.get("what") or "") for x in (J.get("fixed") or [])[:4]]
            lines += ["❓ " + (x.get("what") or "") for x in (J.get("user") or [])[:3]]
            tg("\n".join(l for l in lines if l))
        try: ops_status.main()
        except Exception as ex: log("점검 현황 다시 올리기 실패", repr(ex)[:200])
    finally:
        try: lock.unlink()
        except Exception: pass


if __name__ == "__main__":
    try: main()
    except Exception as ex:
        log("실패:", repr(ex)[:400]); tg("⚠ 점검 의사 실행기 오류: %s" % str(ex)[:200]); raise
