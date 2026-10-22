# -*- coding: utf-8 -*-
"""클로드 구독 호출(claude -p) — 공장 전용 (2026-10-23 사용자 "블로그봇이랑은 상관없는데 왜 연동돼 있어?").

10-14 번역을 구독 방식으로 바꿀 때 블로그봇 폴더의 claude_relay.run_claude 를 경로째 빌려 썼다 → 주식 공장이 블로그봇 폴더에 묶였다.
공장에 필요한 건 'claude -p 를 불러 답 받기' 하나라 여기 따로 둔다(블로그봇 쪽 서버·모델 탐색 기능은 안 가져옴).
모델은 별칭(sonnet·opus·haiku)을 그대로 넘긴다 — claude 가 그 계열 최신으로 바꿔 부른다.
"""
import os, re, subprocess, tempfile, threading
from pathlib import Path
from shutil import which

_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
_LOCK = threading.Lock()                     # 한 번에 하나만(구독 동시 호출은 느려지기만 한다)
_PICK = {"path": None}


def _ver(p):
    try:
        r = subprocess.run([p, "--version"], capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=20, creationflags=_NO_WINDOW)
        m = re.search(r"(\d+)\.(\d+)\.(\d+)", r.stdout or "")
        return tuple(int(x) for x in m.groups()) if m else (0, 0, 0)
    except Exception:
        return (0, 0, 0)


def find_cli():
    """claude 실행 파일 — 여러 벌이면 **가장 새 버전**(따로 깐 claude.exe 는 낡기 쉽고 새 모델을 거부한다)."""
    p = _PICK["path"]
    if p is not None and (p == "" or Path(p).exists()):
        return p
    home = Path(os.environ.get("USERPROFILE", ""))
    cands = [home / ".local" / "bin" / "claude.exe", Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "claude" / "claude.exe",
             Path(os.environ.get("APPDATA", "")) / "npm" / "claude.cmd"]
    if which("claude"): cands.append(Path(which("claude")))
    try: cands += list((home / ".vscode" / "extensions").glob("anthropic.claude-code-*/resources/native-binary/claude.exe"))
    except Exception: pass
    found = sorted({str(c) for c in cands if c.exists()}, key=_ver, reverse=True)
    _PICK["path"] = found[0] if found else ""
    return _PICK["path"]


def run(prompt, model="sonnet", timeout=600, effort="low"):
    """claude -p 로 묻고 (성공?, 답 또는 오류) — 설정·MCP 없이 빈 임시 폴더에서(빠르고 어느 PC 든 같다)."""
    cli = find_cli()
    if not cli:
        return False, "claude 실행 파일을 못 찾음(이 PC 에 Claude Code 설치·로그인 필요)"
    args = [cli, "-p", "--output-format", "text", "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
            "--setting-sources", "", "--effort", effort or "low"]
    if model: args += ["--model", model]
    wd = tempfile.mkdtemp(prefix="factory_claude_")
    with _LOCK:
        try:
            r = subprocess.run(args, input=prompt, capture_output=True, text=True, encoding="utf-8", errors="replace",
                               timeout=timeout, creationflags=_NO_WINDOW, cwd=wd)
        except subprocess.TimeoutExpired:
            return False, "시간 초과(%d초)" % timeout
        except Exception as e:
            return False, "%s: %s" % (type(e).__name__, e)
    out = (r.stdout or "").strip()
    if r.returncode != 0 and not out:
        return False, (r.stderr or "").strip()[:500] or "종료코드 %d" % r.returncode
    return (True, out) if out else (False, "빈 응답")
