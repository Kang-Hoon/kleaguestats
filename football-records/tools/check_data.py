#!/usr/bin/env python3
"""실데이터(data/) 무결성 검사. 사용: python3 tools/check_data.py  (문제가 있으면 종료코드 1)
- teams.csv 코드 중복 / 모든 ID의 팀 코드가 teams.csv에 있는지 / ID 형식
- 이벤트의 match_id·player_id(related 포함) 참조, 선수의 소속 팀이 경기 팀과 일치
- 이벤트가 있는 경기는 (득점+자책)이 점수와 일치, 선발 11명
- 생년월일 형식, id_map.csv의 새 ID가 실제로 존재
"""
import csv, os, re, sys
from collections import Counter, defaultdict
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')
rd = lambda n: list(csv.DictReader(open(os.path.join(D, n + '.csv'), encoding='utf-8')))
T, M, P, E, IDM = rd('teams'), rd('matches'), rd('roster'), rd('events'), rd('id_map')
errs = []
codes = [t['team_code'] for t in T]
errs += [f'teams.csv 코드 중복: {c}' for c, n in Counter(codes).items() if n > 1]
for t in T:
    if t.get('emblem') and not os.path.exists(os.path.join(D, '..', 'emblems', t['emblem'])): errs.append(f"엠블럼 파일 없음: {t['emblem']}")
byname = {t['name']: t['team_code'] for t in T if t['league'] == 'K3리그'}
pids = {p['player_id']: p for p in P}
if len(pids) != len(P): errs.append('player_id 중복')
mids = {m['match_id']: m for m in M}
if len(mids) != len(M): errs.append('match_id 중복')
for p in P:
    m = re.match(r'^([A-Z]{3})-(\d{2})-(\d+)([b-j]?)$', p['player_id'])
    if not m or m[1] not in codes: errs.append(f"player_id 형식/팀코드: {p['player_id']}")
    elif byname.get(p['team']) != m[1]: errs.append(f"{p['player_id']}: 소속 팀 {p['team']} 와 코드 불일치")
    elif int(m[3]) != int(p['shirt_no']): errs.append(f"{p['player_id']}: 등번호 {p['shirt_no']} 와 ID 불일치")
    if p['birth_date'] and not re.match(r'^\d{4}-\d{2}-\d{2}$', p['birth_date']): errs.append(f"생년월일 형식: {p['player_id']}")
for m in M:
    x = re.match(r'^K3-\d{4}-\d{4}-([A-Z]{3})-([A-Z]{3})$', m['match_id'])
    if not x or x[1] not in codes or x[2] not in codes: errs.append(f"match_id 형식/팀코드: {m['match_id']}"); continue
    if byname.get(m['home_team']) != x[1] or byname.get(m['away_team']) != x[2]: errs.append(f"{m['match_id']}: 팀 이름과 ID 불일치")
ev = defaultdict(list)
for e in E:
    if e['match_id'] not in mids: errs.append(f"{e['event_id']}: 없는 경기 {e['match_id']}"); continue
    for c in ('player_id', 'related_player_id'):
        if e[c] and e[c] not in pids: errs.append(f"{e['event_id']}: 없는 선수 {e[c]}")
    ev[e['match_id']].append(e)
for mid, es in ev.items():
    m = mids[mid]
    for k, side in (('home', m['home_team']), ('away', m['away_team'])):
        g = sum(1 for e in es if e['team'] == side and e['type'] in ('GOAL', 'OWN_GOAL'))
        if g != int(m[k + '_score']): errs.append(f'{mid}: {side} 득점 이벤트 {g} ≠ 점수 {m[k+"_score"]}')
        st = sum(1 for e in es if e['team'] == side and e['type'] == 'START')
        if st != 11: errs.append(f'{mid}: {side} 선발 {st}명')
for r in IDM:
    if r['new_id'] not in (mids if r['kind'] == 'match' else pids): errs.append(f"id_map: {r['new_id']} 가 데이터에 없음")
print(f'팀 {len(T)} · 경기 {len(M)}(이벤트 있음 {len(ev)}) · 선수 {len(P)} · 이벤트 {len(E)}')
print('✗ 문제 %d건' % len(errs) if errs else '✓ 문제 없음')
for e in errs[:30]: print('  -', e)
sys.exit(1 if errs else 0)
