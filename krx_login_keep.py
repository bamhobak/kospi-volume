# -*- coding: utf-8 -*-
"""KRX 로그인 확인 — 비밀번호 90일 알림이 뜨면 '90일 뒤에 다시 알림'을 대신 누른다 (2026-11-28 신설).

왜 필요한가: KRX(data.krx.co.kr)는 비밀번호를 바꾼 지 90일이 지나면 로그인 응답을
`_error_code: CD010`(패스워드 변경 필요)로 준다. pykrx 는 이걸 로그인 실패로 처리해서
그 뒤 KRX 요청이 전부 빈 응답이 된다 — 2026-11-27 저녁부터 수급 11분할·밸류에이션·공매도가
통째로 빠졌고, 사람이 브라우저에서 버튼을 눌러 줄 때까지 안 풀렸다.

무엇을 하나: 로그인해 보고
  · CD001(정상)          → 아무것도 안 한다
  · CD010(90일 알림)     → 로그인 화면의 '90일 뒤에 다시 알림' 버튼이 보내는 요청
                           (postponePasswordChange.cmd)을 같은 세션으로 보내고 다시 로그인해 확인
  · 그 밖               → 못 고친다. 알리기만 한다

비밀번호는 바꾸지 않는다(.env 의 KRX_ID·KRX_PW 그대로). 알림은 같은 내용이면 하루 한 번.
`run_daily_research.py` 가 KRX 단계 앞에서 부른다.

사용: python krx_login_keep.py
종료코드: 0 로그인 됨(미룬 뒤 된 것 포함) · 1 로그인 안 됨
"""
import io, json, os, sys, time
from pathlib import Path

BASE = Path(__file__).parent
HOST = "https://data.krx.co.kr"
PAGE = HOST + "/contents/MDC/COMS/client/MDCCOMS001.cmd"
JSP = HOST + "/contents/MDC/COMS/client/view/login.jsp?site=mdc"
LOGIN = HOST + "/contents/MDC/COMS/client/MDCCOMS001D1.cmd"
POSTPONE = HOST + "/contents/MDC/COMS/client/postponePasswordChange.cmd"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/131.0.0.0 Safari/537.36")
STATE = BASE / "data" / "krx_login_keep.json"


def env():
    out = {}
    f = BASE / ".env"
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1); out[k.strip()] = v.strip()
    return {**out, **{k: v for k, v in os.environ.items() if k in ("KRX_ID", "KRX_PW")}}


def new_session():
    import requests
    s = requests.Session()
    s.get(PAGE, headers={"User-Agent": UA}, timeout=15)
    s.get(JSP, headers={"User-Agent": UA, "Referer": PAGE}, timeout=15)
    return s


def login(s, uid, pw):
    """(코드, 메시지). CD011(중복 로그인)은 화면처럼 한 번 더 보낸다."""
    pay = {"mbrNm": "", "telNo": "", "di": "", "certType": "", "mbrId": uid, "pw": pw}
    h = {"User-Agent": UA, "Referer": PAGE}
    d = s.post(LOGIN, data=pay, headers=h, timeout=15).json()
    if d.get("_error_code") == "CD011":
        pay["skipDup"] = "Y"
        d = s.post(LOGIN, data=pay, headers=h, timeout=15).json()
    return d.get("_error_code", ""), d.get("_error_message", "")


def keep(uid, pw, session=new_session):
    """→ ("ok" | "postponed" | "stuck" | "fail", 설명)"""
    s = session()
    code, msg = login(s, uid, pw)
    if code == "CD001": return "ok", ""
    if code != "CD010": return "fail", ("%s %s" % (code, msg)).strip()
    # 버튼은 CD010 을 받은 그 세션에서 눌린다 — 같은 세션으로 보낸다
    try:
        r = s.post(POSTPONE, headers={"User-Agent": UA, "Referer": JSP, "X-Requested-With": "XMLHttpRequest"}, timeout=15)
        ans = "HTTP %s %s" % (r.status_code, (r.text or "")[:120].replace("\n", " "))
    except Exception as ex:
        ans = "요청 실패 %r" % (ex,)
    code2, msg2 = login(session(), uid, pw)          # 새 세션으로 다시 — 정말 풀렸는지
    if code2 == "CD001": return "postponed", ""
    return "stuck", ("미루기 응답 %s · 다시 로그인 %s %s" % (ans, code2, msg2)).strip()


def tell(state, detail):
    """같은 내용은 하루 한 번만 보낸다."""
    text = {"postponed": "🔑 KRX 비밀번호 90일 알림 — 자동으로 미룸",
            "stuck": "⚠ <b>KRX 로그인 막힘</b> — 90일 알림 못 미룸\nKRX 로그인해서 '90일 뒤에 다시 알림' 누르기",
            "fail": "⚠ <b>KRX 로그인 실패</b> — %s" % detail[:120]}.get(state)
    if not text: return
    day = time.strftime("%Y%m%d")
    try: last = json.loads(STATE.read_text(encoding="utf-8"))
    except Exception: last = {}
    if last.get("day") == day and last.get("state") == state: return
    try:
        import research_health as RH
        RH.telegram(text)
    except Exception as ex:
        print("알림 실패: %r" % (ex,))
    try: STATE.write_text(json.dumps({"day": day, "state": state, "detail": detail[:300]}, ensure_ascii=False), encoding="utf-8")
    except Exception: pass


def main():
    E = env()
    if not (E.get("KRX_ID") and E.get("KRX_PW")):
        print("KRX_ID·KRX_PW 없음 — 건너뜀"); return 0
    try:
        state, detail = keep(E["KRX_ID"], E["KRX_PW"])
    except Exception as ex:                          # 네트워크 문제는 로그인 문제가 아니다 — 알리지 않고 다음 단계에 맡긴다
        print("KRX 로그인 확인 못 함: %r" % (ex,)); return 0
    print({"ok": "KRX 로그인 정상", "postponed": "KRX 비밀번호 90일 알림 — 미룸 · 로그인 정상",
           "stuck": "KRX 90일 알림 못 미룸 — " + detail, "fail": "KRX 로그인 실패 — " + detail}[state])
    tell(state, detail)
    return 0 if state in ("ok", "postponed") else 1


if __name__ == "__main__":
    for _n in ("stdout", "stderr"):                  # pythonw 로 뜨면 None — 그대로 쓰면 첫 줄에서 죽는다
        _f = getattr(sys, _n, None)
        if _f is None: setattr(sys, _n, io.open(os.devnull, "w", encoding="utf-8"))
        else:
            try: _f.reconfigure(encoding="utf-8", errors="replace")
            except Exception: pass
    sys.exit(main())
