/* 설치형 앱(PWA) 을 위한 최소 서비스워커.
   ⚠ 캐시하지 않는다 — 자료가 매일 바뀌고, 브라우저 캐시 때문에 옛 화면을 보는 사고가
   이미 있었다(2026-09-11). 여기서 또 캐시하면 그 사고가 되살아난다.
   Chrome 이 '설치 가능' 으로 인정하려면 fetch 핸들러가 있어야 해서 그것만 둔다. */
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()));
self.addEventListener('fetch', (e) => { /* 그대로 네트워크로 보낸다 */ });
