# -*- coding: utf-8 -*-
"""연구 스크립트를 메모리 감시 안에서 돌린다(2026-11-14 · 사용자 '10gb 허용' — 원격 강제 종료가 막혀 있어 스스로 멈추게).
    python research/memguard.py [--gb 10] 스크립트.py 인자...
WorkingSet 이 한도를 넘으면 메시지를 남기고 즉시 끝낸다(종료 코드 3). 끝날 때 최대 메모리를 알려 준다."""
import ctypes, ctypes.wintypes as W, os, runpy, sys, threading, time


class PMC(ctypes.Structure):
    _fields_ = [("cb", W.DWORD), ("PageFaultCount", W.DWORD)] + [(n, ctypes.c_size_t) for n in (
        "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
        "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]


ps = ctypes.WinDLL("psapi")                                    # 공유 함수 객체에 argtypes 를 안 건다(돌리는 스크립트가 따로 걸면 부딪힘 — 11-14 mix_swing)
HPROC = ctypes.c_void_p(-1)                                      # 현재 프로세스 가짜 핸들


def rss():
    c = PMC(); c.cb = ctypes.sizeof(c); ps.GetProcessMemoryInfo(HPROC, ctypes.byref(c), c.cb)
    return c.WorkingSetSize, c.PeakWorkingSetSize


args = sys.argv[1:]
lim = 10.0
if args[:1] == ["--gb"]: lim = float(args[1]); args = args[2:]
t0 = time.time()


def guard():
    while True:
        r, _ = rss()
        if r > lim * 1e9:
            sys.__stdout__.write("[memguard] 메모리 %.1fGB > %.0fGB — 스스로 멈춤 (%.1f분)\n" % (r / 1e9, lim, (time.time() - t0) / 60)); sys.__stdout__.flush()
            os._exit(3)
        time.sleep(0.5)


threading.Thread(target=guard, daemon=True).start()
sys.argv = args
code = 0
try:
    runpy.run_path(args[0], run_name="__main__")
except SystemExit as ex:                                          # 스크립트의 sys.exit(n) 은 그 코드 그대로
    code = ex.code if isinstance(ex.code, int) else (0 if ex.code is None else 1)
finally:
    sys.__stdout__.write("[memguard] 최대 메모리 %.1fGB · %.1f분\n" % (rss()[1] / 1e9, (time.time() - t0) / 60)); sys.__stdout__.flush()
sys.exit(code)
