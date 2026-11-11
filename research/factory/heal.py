# -*- coding: utf-8 -*-
"""스스로 고치는 점검기 — 2026-11-12 사용자 "⑩ 해줘". health.check() 가 찾은 문제 중 처방이 알려진 것을 알리기 전에 먼저 해 본다.

되돌릴 수 있는 것만 자동으로 한다(지우기·덮어쓰기·실전 주문 없음):
  일봉 부족(매일 일봉에 전 거래일 종목 수 모자람)  → live.update()(1분봉 매일 파일을 일봉에 다시 넣기, 이 PC 안에서만) → 다시 점검
  전 거래일 1분봉 매일 파일 없음                  → 15:40 한 번짜리 예약 작업으로 collect_m1 daily kr(장중엔 토스 API 를 실전과 나눠 쓰니 마감 뒤)
  투자자 수급(flow11) 묵음                         → \\kospi-volume-research-daily 작업 다시 시작(KRX 저속·순차라 장중에도 괜찮음)
고친 것은 점검 보고서에 '🔧' 로 남기고, 전부 고쳐졌으면 텔레그램은 안 보낸다(월요일 주간 한 줄에 고친 횟수).
"""
import datetime as dt, os, re, subprocess
import common as C

PS = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
PYW = r"C:\Users\bamhobak\AppData\Local\Python\pythoncore-3.14-64\pythonw.exe"


def _ps(cmd, timeout=60):
    r = subprocess.run([PS, "-NoProfile", "-Command", cmd], capture_output=True, timeout=timeout, creationflags=0x08000000)
    return r.returncode, (r.stdout + r.stderr).decode("utf-8", "replace").strip()


def fix_daily():
    import live
    live.update()
    return "매일 일봉 다시 넣음(live.update)"


def fix_m1():
    now = C.now()
    at = now.replace(hour=15, minute=40, second=0, microsecond=0)
    if now >= at: at = now + dt.timedelta(minutes=2)
    xml_src = "\\BamhobakM1\\DailyKR"
    cmd = ("$x = Export-ScheduledTask -TaskPath '\\BamhobakM1\\' -TaskName 'DailyKR'; "
           "$x = $x -replace '<StartBoundary>[^<]+</StartBoundary>', '<StartBoundary>%s</StartBoundary>'; "
           "$x = $x -replace '(?s)<Triggers>.*</Triggers>', '<Triggers><TimeTrigger><StartBoundary>%s</StartBoundary><Enabled>true</Enabled></TimeTrigger></Triggers>'; "
           "Register-ScheduledTask -TaskPath '\\BamhobakFactory\\' -TaskName 'HealM1' -Xml $x -Force | Out-Null; 'ok'") % (
        at.strftime("%Y-%m-%dT%H:%M:%S"), at.strftime("%Y-%m-%dT%H:%M:%S"))
    rc, out = _ps(cmd)
    if rc != 0 or "ok" not in out: raise RuntimeError("HealM1 예약 실패: " + out[:150])
    return "1분봉 다시 받기 %s 예약(\\BamhobakFactory\\HealM1, %s 복제)" % (at.strftime("%H:%M"), xml_src)


def fix_flow():
    rc, out = _ps("Start-ScheduledTask -TaskName 'kospi-volume-research-daily'; 'ok'")
    if rc != 0 or "ok" not in out: raise RuntimeError(out[:150])
    return "수급 수집 작업 다시 시작"


# (문제 글 패턴, 처방, 바로 다시 점검하면 풀리나)
RULES = [
    (re.compile(r"매일 일봉에 \d+ 종목 \d+개"), fix_daily, True),
    (re.compile(r"전 거래일 1분봉 매일 파일 없음"), fix_m1, False),
    (re.compile(r"투자자 수급\(flow11\) 마지막"), fix_flow, False),
]


def heal(P):
    """P = [(등급, 글)] → (해 본 것 [(글, 결과)], 다시 점검이 필요한가)."""
    done, recheck = [], False
    for lv, s in P:
        for pat, fn, again in RULES:
            if pat.search(s):
                try:
                    done.append((s, "🔧 " + fn())); recheck |= again
                except Exception as ex:
                    done.append((s, "🔧 실패: %s" % str(ex)[:150]))
                break
    return done, recheck
