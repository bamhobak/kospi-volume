# -*- coding: utf-8 -*-
"""매일 수집 파이프라인 시뮬레이션 — 장 마감 후 워크플로가 제대로 도는지 점검한다.

selftest.py 가 '지금 사이트·규칙이 맞나' 를 본다면, 이쪽은 '내일 저녁 수집이
정상적으로 돌 것인가' 를 본다. 워크플로 단계를 순서대로 훑으며
  · 스크립트가 존재하고 문법이 맞는가
  · 필요한 자격증명이 있는가 (로컬 .env / Actions Secrets)
  · 실제로 돌려볼 수 있는 것은 돌려 본다
을 확인한다. KRX·토스처럼 지금 백필이 점유 중이거나 외부에 부담을 주는 단계는
실행하지 않고 '점검만' 으로 표시한다 — 같은 API 를 동시에 때리면 막히기 때문이다.

사용: python simulate_daily.py
"""
import io, os, re, sys, ast, json, sqlite3, subprocess, datetime as dt
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
BASE = Path(__file__).parent
import yaml
FAIL, WARN = [], []
def ok(m):  print(f"    ✅ {m}")
def ng(m):  FAIL.append(m); print(f"    ❌ {m}")
def wn(m):  WARN.append(m); print(f"    ⚠  {m}")

WF = yaml.safe_load((BASE/".github"/"workflows"/"collect.yml").read_text(encoding="utf-8"))
steps = WF["jobs"]["build"]["steps"]
on = WF[True] if True in WF else WF["on"]

print("\n## 1) 트리거 — 언제 도는가")
cr = [c["cron"] for c in on.get("schedule", [])]
for c in cr:
    m, h = c.split()[0], c.split()[1]
    print(f"    예약 {c}  → KST {(int(h)+9)%24:02d}:{int(m):02d}")
ok(f"외부 스케줄러 입구 repository_dispatch: {list(on['repository_dispatch']['types'])}")
tmo = WF["jobs"]["build"].get("timeout-minutes")
(ok if tmo and tmo >= 240 else ng)(f"잡 타임아웃 {tmo}분 — 21:00 대기 마감까지 버틸 수 있는가")
cc = WF.get("concurrency", {})
(ok if "push" in str(cc.get("cancel-in-progress")) else wn)(
    f"동시성: 코드 푸시가 진행 중인 수집을 취소하지 않는가 ({cc.get('cancel-in-progress')})")

print("\n## 2) 단계별 스크립트·자격증명")
need = {}   # 단계 → 필요한 secret
for s in steps:
    nm = s.get("name")
    if not nm: continue
    run = s.get("run", "")
    for m in re.finditer(r"python\s+([a-zA-Z0-9_]+\.py)", run):
        f = BASE/m.group(1)
        if not f.exists(): ng(f"[{nm}] {m.group(1)} 없음"); continue
        try: ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError as e: ng(f"[{nm}] {m.group(1)} 문법오류 {e.lineno}행"); continue
    need[nm] = sorted(set(re.findall(r"secrets\.([A-Z_]+)", json.dumps(s.get("env", {})))))
env_local = {}
if (BASE/".env").exists():
    for ln in (BASE/".env").read_text(encoding="utf-8").splitlines():
        if "=" in ln and not ln.strip().startswith("#"):
            k, v = ln.split("=", 1); env_local[k.strip()] = v.strip()
allsec = sorted({x for v in need.values() for x in v})
missing = [k for k in allsec if k not in env_local and not os.environ.get(k)]
ok(f"단계 {len([s for s in steps if s.get('name')])}개 · 스크립트 문법 정상")
print(f"    필요한 Secrets: {', '.join(allsec)}")
(ok if not missing else wn)("로컬에 모든 키가 있다" if not missing
    else f"로컬에 없는 키 {missing} — Actions Secrets 에만 있으면 정상")

print("\n## 3) 수집 필요 판정 (is_trading_day)")
try:
    r = subprocess.run([sys.executable, "is_trading_day.py"], cwd=str(BASE),
                       capture_output=True, timeout=180, text=True)
    v = (r.stdout or "").strip().splitlines()[-1] if r.stdout else "?"
    ok(f"판정 = {v}  (true 면 못 받은 거래일이 있다는 뜻)")
except Exception as e: ng(f"실행 실패: {e}")

print("\n## 4) 토스 인증 (Actions 는 .env 없이 환경변수만 쓴다)")
try:
    envc = dict(os.environ)
    envc.update({k: env_local[k] for k in ("TOSS_CLIENT_KEY","TOSS_SECRET_KEY") if k in env_local})
    code = ("import sys,os,pathlib;"
            "os.environ.pop('_',None);"
            "sys.path.insert(0,r'%s');" % BASE +
            "import toss;t=toss.token();print('TOKEN_OK' if t else 'TOKEN_FAIL')")
    r = subprocess.run([sys.executable, "-c", code], cwd=str(BASE), env=envc,
                       capture_output=True, timeout=120, text=True)
    (ok if "TOKEN_OK" in (r.stdout or "") else ng)(
        "환경변수만으로 토큰 발급 성공" if "TOKEN_OK" in (r.stdout or "")
        else f"토큰 발급 실패: {(r.stderr or r.stdout)[-200:]}")
except Exception as e: ng(f"토스 인증 확인 실패: {e}")

print("\n## 5) 빈 파일 가드 (수집 실패가 배포로 새지 않는가)")
guard = next((s for s in steps if s.get("name","").startswith("수집 결과 점검")), None)
if not guard: ng("빈 파일 점검 단계가 없다")
else:
    files = re.findall(r"data/[a-z_]+\.csv", guard["run"])
    bi = [i for i,s in enumerate(steps) if s.get("name")==guard["name"]][0]
    bj = [i for i,s in enumerate(steps) if s.get("name","").startswith("build site")]
    (ok if bj and bi < bj[0] else ng)(f"가드가 빌드보다 앞에 있다 (가드 {bi+1}번 · 빌드 {bj[0]+1 if bj else '?'}번)")
    bad = []
    for f in files:
        p = BASE/f
        n = sum(1 for _ in p.open(encoding="utf-8")) if p.exists() else 0
        if n <= 1: bad.append(f"{f}({n}줄)")
    (ok if not bad else ng)(f"감시 대상 {len(files)}개 파일 모두 정상" if not bad else f"지금 비어 있는 파일: {bad}")

print("\n## 6) 알림 경로")
ts = (BASE/"supabase"/"functions"/"prices"/"index.ts").read_text(encoding="utf-8")
ok(f"텔레그램 알림 종류: {'손절' if '손절선 이탈' in ts else '?'}·"
   f"{'매도일' if '매도일' in ts else '?'}·{'추가매수' if '추가매수' in ts else '-'}")
nstep = next((s for s in steps if s.get("name")=="notify new picks"), None)
(ok if nstep and nstep.get("continue-on-error") else ng)(
    "알림 실패가 데이터 커밋을 막지 않는다" if nstep and nstep.get("continue-on-error")
    else "알림이 실패하면 그날 데이터가 커밋되지 않는다")

print("\n## 7) 커밋 대상")
cm = next((s for s in steps if s.get("name","").startswith("commit")), None)
if cm:
    fs = re.findall(r"data/[a-zA-Z0-9_*.-]+", cm["run"])
    print(f"    {', '.join(fs)}")
    gi = (BASE/".gitignore").read_text(encoding="utf-8")
    ignored = [f for f in fs if f.rstrip("*") and any(
        l.strip() and not l.startswith("#") and l.strip().rstrip("/") in f for l in gi.splitlines())]
    (wn if ignored else ok)(f"gitignore 와 겹치는 대상: {ignored}" if ignored else "커밋 대상이 gitignore 와 겹치지 않는다")
print(f"\n{'='*60}")
if FAIL:
    print(f"❌ 문제 {len(FAIL)}건"); [print(f"   · {m}") for m in FAIL]
elif WARN:
    print(f"✅ 통과 (확인할 점 {len(WARN)}건)"); [print(f"   · {m}") for m in WARN]
else: print("✅ 전체 통과")
sys.exit(1 if FAIL else 0)
