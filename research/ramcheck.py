# -*- coding: utf-8 -*-
"""남은 RAM 확인 — 모자라면 종료 코드 1(묶음 작업이 무거운 단계를 건너뛰게). 2026-11-14 · 규칙: 띄우기 전 남은 램 8GB↑.
    python research/ramcheck.py [GB=8]"""
import ctypes, sys


class MS(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong), ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong), ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong), ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]


m = MS(); m.dwLength = ctypes.sizeof(m); ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
need = float(sys.argv[1]) if len(sys.argv) > 1 else 8.0
free = m.ullAvailPhys / 1e9
print("남은 램 %.1fGB (필요 %.0fGB)" % (free, need))
sys.exit(0 if free >= need else 1)
