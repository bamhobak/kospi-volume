# 내부자 공시 본문 수집 — 매일 DART 한도까지 받고 종료.
# 파이썬이 insider_collect.log 를 직접 쓰므로 여기서는 건드리지 않는다
# (같은 파일을 양쪽에서 열면 PermissionError 가 난다). 작업 자체 기록만 남긴다.
Set-Location "G:\vscode\kospi-volume"
$log = "G:\vscode\kospi-volume\insider_task.log"
Add-Content $log ("=== 시작 " + (Get-Date -Format "yyyy-MM-dd HH:mm:ss") + " ===")
& python.exe collect_insider.py | Out-Null
Add-Content $log ("=== 종료 exit=" + $LASTEXITCODE + " " + (Get-Date -Format "HH:mm:ss") + " ===")
