"""K리그 공식 사이트에서 한 시즌 전 경기를 받아 축소 저장.
사용: python3 kleague_fetch.py YEAR OUTDIR [meetSeq=1]
저장: games_index.json, games/<id>/{matchInfo.json, allDetail.json(필수 값만), lineup.json(라인업만)}
"""
import os, re, sys, json, time, urllib.request, urllib.parse
from bs4 import BeautifulSoup
YEAR, OUT = sys.argv[1], sys.argv[2]; MEET = sys.argv[3] if len(sys.argv) > 3 else '1'
UA = {'User-Agent': 'Mozilla/5.0 (compatible; football-records)', 'Accept-Language': 'ko', 'X-Requested-With': 'XMLHttpRequest',
      'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'}
B = 'https://www.kleague.com'
def call(req, tries=4):
    for i in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=40) as r: return r.read().decode('utf-8', 'replace')
        except Exception as e:
            err = repr(e); time.sleep(2 * (i + 1))
    raise RuntimeError(err)
def post(ep, **kw): return json.loads(call(urllib.request.Request(B + ep, data=urllib.parse.urlencode(kw).encode(), headers=UA)))
def html(gid): return call(urllib.request.Request(f'{B}/match.do?year={YEAR}&meetSeq={MEET}&gameId={gid}&leagueId={MEET}&startTabNum=1', headers={'User-Agent': UA['User-Agent']}))
def lineup(h):
    rows = {}
    for tid, pid, no, pos, name in re.findall(r"playerDetailPop\('(K\d+)', '(\d+)'\)\"[^>]*>\s*<td>(\d+)</td>\s*<td>(\w+)</td>\s*<td>\s*([^<]+?)</td>", h):
        rows[pid] = [tid, int(no), pos, name.strip()]
    s = BeautifulSoup(h, 'html.parser'); starters = []
    for p in s.find_all('p'):
        if p.get_text(strip=True) == '선발 명단':
            cur = []
            for tr in p.find_next('table').find('tbody').find_all('tr'):
                td = [x.get_text(' ', strip=True) for x in tr.find_all('td')]
                cur.append([int(td[0]), td[2]])
            starters.append(cur)
    # 경기장 그림(선발 11명씩): playerDetailPop('팀','선수번호') 다음의 <p>배번.이름</p>
    flat = re.sub(r'\s+', ' ', h); pitch = []
    for tid, pid, no, nm in re.findall(r"playerDetailPop\('(K\d+)', '(\d+)'\)\" style=\"cursor:pointer[^>]*>(?:(?!playerDetailPop).)*?<p>(\d+)\.([^<]+)</p>", flat):
        pitch.append([tid, pid, int(no), nm.strip()])
    return {'rows': rows, 'starters': starters, 'pitch': pitch}
os.makedirs(f'{OUT}/games', exist_ok=True)
rounds = post('/api/ddf/match/getRoundList.do', year=YEAR, meetSeq=MEET)['data']['roundList']
games = []
for r in rounds:
    for g in post('/api/ddf/match/getRoundGameList.do', year=YEAR, meetSeq=MEET, roundId=str(r))['data']['roundGameList']:
        g['_round'] = r; games.append(g)
    time.sleep(0.2)
json.dump(games, open(f'{OUT}/games_index.json', 'w', encoding='utf-8'), ensure_ascii=False)
print('rounds', len(rounds), 'games', len(games), flush=True)
for i, g in enumerate(games):
    gid = str(g['gameId']); d = f'{OUT}/games/{gid}'; os.makedirs(d, exist_ok=True)
    info = post('/api/ddf/match/matchInfo.do', year=YEAR, meetSeq=MEET, gameId=gid); time.sleep(0.15)
    json.dump(info, open(f'{d}/matchInfo.json', 'w', encoding='utf-8'), ensure_ascii=False)
    if (info.get('data') or {}).get('gameStatus') != 'FE': continue
    det = post('/api/ddf/match/getMatchRecordAllDetail.do', year=YEAR, yearTst=YEAR, meetSeq=MEET, gameId=gid, gameIdTst=gid,
               homeTeam=g['homeTeam'], awayTeam=g['awayTeam'], roundId=str(g['_round'])); time.sleep(0.15)
    keep = lambda L: [{k: p.get(k) for k in ('playerId', 'playerName', 'playerPos', 'minutePlay', 'backNo', 'teamName')} for p in (L or [])]
    json.dump({'data': {'listH': keep(det['data'].get('listH')), 'listA': keep(det['data'].get('listA'))}}, open(f'{d}/allDetail.json', 'w', encoding='utf-8'), ensure_ascii=False)
    json.dump(lineup(html(gid)), open(f'{d}/lineup.json', 'w', encoding='utf-8'), ensure_ascii=False); time.sleep(0.15)
    if i % 20 == 0: print(i, gid, flush=True)
print('done')
