# -*- coding: utf-8 -*-
"""토스증권 Open API 얇은 클라이언트.

KRX 는 저속(gap 2초)으로만 때릴 수 있는데 토스는 매매동향 그룹이 초당 10회다.
과거를 얼마나 주는지에 따라 KRX 백필을 상당 부분 대체할 수 있다.
토큰은 24시간짜리라 파일에 캐시해 두고 재사용한다.
"""
import io, os, sys, json, time, urllib.request, urllib.parse
from pathlib import Path
BASE = Path(__file__).parent
B = "https://openapi.tossinvest.com"
_TOK = {"v": None, "exp": 0}

def _env():
    """로컬은 .env, GitHub Actions 는 환경변수(secrets)에서 읽는다."""
    e = {}
    f = BASE/".env"
    if f.exists():
        for ln in f.read_text(encoding="utf-8").splitlines():
            if "=" in ln and not ln.strip().startswith("#"):
                k, v = ln.split("=", 1); e[k.strip()] = v.strip()
    for k in ("TOSS_CLIENT_KEY", "TOSS_SECRET_KEY"):
        if os.environ.get(k): e[k] = os.environ[k]
        if k not in e: raise SystemExit(f"{k} 가 없습니다(.env 또는 환경변수)")
    return e

class _IssueLock:
    """토큰 발급 잠금 — 윈도우 서버에서만 건다(GitHub Actions 는 프로세스가 하나라 필요 없다). 프로세스가 죽으면 OS 가 푼다."""

    def __init__(self, c):
        self.p = str(c) + ".lock"; self.fd = None

    def __enter__(self):
        try:
            import msvcrt
            self.fd = os.open(self.p, os.O_CREAT | os.O_RDWR)
            for _ in range(600):
                try:
                    os.lseek(self.fd, 0, 0); msvcrt.locking(self.fd, msvcrt.LK_NBLCK, 1); return self
                except OSError: time.sleep(0.05)
        except Exception: pass
        return self

    def __exit__(self, *a):
        try:
            if self.fd is not None:
                import msvcrt
                os.lseek(self.fd, 0, 0); msvcrt.locking(self.fd, msvcrt.LK_UNLCK, 1); os.close(self.fd)
        except Exception: pass


def token():
    if _TOK["v"] and time.time() < _TOK["exp"] - 60: return _TOK["v"]
    c = BASE/"data"/".toss_token.json"
    if c.exists():
        try:
            j = json.loads(c.read_text())
            if time.time() < j["exp"] - 60:
                _TOK.update(v=j["v"], exp=j["exp"]); return j["v"]
        except Exception: pass
    # 2026-11-01: 토큰은 키당 1개라 두 프로세스가 같이 받으면 서로를 끊는다 → 발급은 프로세스 사이 잠금 안에서, 파일은 통째로 바꿔 쓴다.
    with _IssueLock(c):
        if c.exists():
            try:
                j = json.loads(c.read_text())
                if time.time() < j["exp"] - 60:
                    _TOK.update(v=j["v"], exp=j["exp"]); return j["v"]
            except Exception: pass
        e = _env()
        body = urllib.parse.urlencode({"grant_type": "client_credentials",
            "client_id": e["TOSS_CLIENT_KEY"], "client_secret": e["TOSS_SECRET_KEY"]}).encode()
        r = urllib.request.Request(B+"/oauth2/token", data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"})
        t = json.loads(urllib.request.urlopen(r, timeout=30).read().decode())
        _TOK.update(v=t["access_token"], exp=time.time()+int(t.get("expires_in", 3600)))
        try:
            tmp = c.with_name("%s.%d.tmp" % (c.name, os.getpid()))
            tmp.write_text(json.dumps(_TOK)); os.replace(tmp, c)
        except Exception: pass
    return _TOK["v"]

def get(path, **q):
    """응답은 {'result': ...} 로 한 겹 싸여 온다 — 벗겨서 돌려준다."""
    u = path + ("?" + urllib.parse.urlencode({k: v for k, v in q.items() if v is not None}) if q else "")
    for i in range(4):
        rq = urllib.request.Request(B+u, headers={"Authorization": f"Bearer {token()}"})
        try:
            d = json.loads(urllib.request.urlopen(rq, timeout=12).read().decode())
            return d.get("result", d)
        except Exception as ex:
            code = getattr(ex, "code", None)
            msg = ex.read().decode()[:200] if hasattr(ex, "read") else str(ex)
            # 400·404 는 그 종목에 데이터가 없다는 뜻이라 다시 물어도 같다. 즉시 포기해야
            # 전체 수집이 느려지지 않는다(2,767종목 중 상당수가 여기 해당한다).
            # 401·403(인증·차단)도 다시 물어도 같다. 예전엔 403 을 4번씩 재시도해서
            # 러너에서 전 종목 403 이 나던 날 수집 단계 하나가 몇 시간을 붙잡았다(2026-09-21).
            if code in (400, 401, 403, 404) or i == 3: return {"_err": msg, "_code": code}
            time.sleep(2.0*(i+1) if code == 429 else 0.4*(i+1))
