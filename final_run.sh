#!/bin/sh
cd /g/vscode/kospi-volume
# 패널 재생성이 끝날 때까지 기다린다(코스닥 파일이 갱신되고 로그에 완료가 찍힐 때까지)
while ! grep -q "panel_kq.pkl" panel_rebuild.log 2>/dev/null; do sleep 20; done
sleep 15
export IX_FROM=2004-06-01 DART_FROM=20040101 PANEL_KP=panel_kp.pkl PANEL_KQ=panel_kq.pkl PYTHONIOENCODING=utf-8
echo "===== 1) [외인 매집] 21년 재측정 (시총 채운 뒤) ====="
HIST_PER="2005~07:20050101-20071231,2008~09:20080101-20091231,2010~12:20100101-20121231,2013~17:20130101-20171231,2018~22:20180101-20221231,2023~26:20230101-20991231" HIST_YEAR=1 python measure_hist.py 2>&1 | tail -40
echo
echo "===== 2) [조용한 신고가] 존치 판단 (최종 패널) ====="
python p1_keep.py 2>&1 | tail -10
