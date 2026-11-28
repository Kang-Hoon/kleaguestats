import os, re, json, time, urllib.request, urllib.parse
UA = {'User-Agent': 'Mozilla/5.0 (compatible; football-records-probe)', 'Accept-Language': 'ko',
      'X-Requested-With': 'XMLHttpRequest', 'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'}
B = 'https://www.kleague.com'
os.makedirs('out/games', exist_ok=True)
def post(ep, **kw):
    req = urllib.request.Request(B + ep, data=urllib.parse.urlencode(kw).encode(), headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=30) as r: return r.read().decode('utf-8', 'replace')
    except Exception as e: return json.dumps({'error': repr(e)})
def get(path):
    req = urllib.request.Request(B + path, headers={'User-Agent': UA['User-Agent'], 'Accept-Language': 'ko'})
    try:
        with urllib.request.urlopen(req, timeout=30) as r: return r.read().decode('utf-8', 'replace')
    except Exception as e: return repr(e)
rl = post('/api/ddf/match/getRoundList.do', year='2026', meetSeq='1'); open('out/roundList.json', 'w', encoding='utf-8').write(rl)
rounds = json.loads(rl)['data']['roundList']; print('rounds', len(rounds))
games = []
for r in rounds:
    t = post('/api/ddf/match/getRoundGameList.do', year='2026', meetSeq='1', roundId=str(r)); time.sleep(0.2)
    open(f'out/round_{r}.json', 'w', encoding='utf-8').write(t)
    for g in json.loads(t)['data']['roundGameList']: g['_round'] = r; games.append(g)
json.dump(games, open('out/games_index.json', 'w', encoding='utf-8'), ensure_ascii=False)
print('games', len(games), games[0])
daejeon = [g for g in games if '대전' in (g.get('homeTeamName', '') + g.get('awayTeamName', ''))]
print('daejeon', len(daejeon))
for g in daejeon:
    gid = str(g['gameId']); d = f'out/games/{gid}'; os.makedirs(d, exist_ok=True)
    for ep in ('matchInfo', 'matchRecord'):
        open(f'{d}/{ep}.json', 'w', encoding='utf-8').write(post(f'/api/ddf/match/{ep}.do', year='2026', meetSeq='1', gameId=gid)); time.sleep(0.2)
    open(f'{d}/allDetail.json', 'w', encoding='utf-8').write(post('/api/ddf/match/getMatchRecordAllDetail.do', year='2026', yearTst='2026', meetSeq='1', gameId=gid, gameIdTst=gid,
        homeTeam=g.get('homeTeam', g.get('homeTeamId', '')), awayTeam=g.get('awayTeam', g.get('awayTeamId', '')), roundId=str(g['_round']))); time.sleep(0.2)
    open(f'{d}/match.html', 'w', encoding='utf-8').write(get(f"/match.do?year=2026&meetSeq=1&gameId={gid}&leagueId=1&startTabNum=1")); time.sleep(0.2)
