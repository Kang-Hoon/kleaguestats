import os, re, json, urllib.request, urllib.parse
UA = {'User-Agent': 'Mozilla/5.0 (compatible; football-records-probe)', 'Accept-Language': 'ko'}
os.makedirs('out', exist_ok=True)
def get(url, data=None, headers=None):
    h = dict(UA); h.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=30) as r: return r.status, r.read().decode('utf-8', 'replace')
    except Exception as e: return 0, repr(e)
B = 'https://www.kleague.com/'
pages = {
 'schedule': 'schedule.do?leagueId=1', 'club': 'club.do?teamId=K10', 'player': 'player.do',
 'match': 'match.do?year=2026&leagueId=1&gameId=1&meetSeq=1&startTabNum=3',
}
ends, scripts = set(), set()
for k, p in pages.items():
    st, t = get(B + p); open(f'out/{k}.html', 'w', encoding='utf-8').write(t); print(k, st, len(t))
    scripts |= set(re.findall(r'<script[^>]+src="([^"]+)"', t))
    ends |= set(re.findall(r'["\'/]([\w/]+\.do)\b', t))
for s in sorted(scripts):
    if s.startswith('//'): u = 'https:' + s
    elif s.startswith('http'): u = s
    else: u = B + s.lstrip('/')
    if 'kleague.com' not in u: continue
    st, t = get(u); name = re.sub(r'\W+', '_', s)[-60:]
    open(f'out/js_{name}', 'w', encoding='utf-8').write(t); print('js', st, len(t), u)
    ends |= set(re.findall(r'["\'/]([\w/]+\.do)\b', t))
open('out/endpoints.txt', 'w').write('\n'.join(sorted(ends)))
# 후보 API 호출 (일정)
JH = {'Content-Type': 'application/json; charset=UTF-8', 'X-Requested-With': 'XMLHttpRequest', 'Referer': B + 'schedule.do'}
for ep in ['getScheduleList.do', 'schedule/getScheduleList.do', 'api/schedule.do']:
    for body in ({'year': '2026', 'month': '03', 'leagueId': '1', 'teamId': 'K10'}, {'selectYear': '2026', 'selectMonth': '03', 'leagueId': '1'}):
        st, t = get(B + ep, json.dumps(body).encode(), JH); name = re.sub(r'\W+', '_', ep + json.dumps(body))[:80]
        open(f'out/api_{name}.txt', 'w', encoding='utf-8').write(t[:20000]); print('api', ep, st, len(t))
