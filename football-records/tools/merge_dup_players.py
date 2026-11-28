#!/usr/bin/env python3
"""같은 사람(kleague_id)·같은 팀·같은 시즌인데 선수 행이 둘로 나뉜 경우(배번 표기 차이로 생김)를 한 행으로 합친다.
배번(shirt_no)이 같아진 그룹만 합치고, 이벤트가 더 많은 행의 player_id 를 남긴다. events.csv 의 참조도 함께 바꾼다.
사용: python3 tools/merge_dup_players.py [--apply]"""
import csv, os, sys, collections
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')
apply = '--apply' in sys.argv
R = list(csv.DictReader(open(D + '/roster.csv', encoding='utf-8'))); rh = list(R[0].keys())
er = csv.DictReader(open(D + '/events.csv', encoding='utf-8')); eh = er.fieldnames; E = list(er)
ev = collections.Counter(e['player_id'] for e in E)
g = collections.defaultdict(list)
for r in R:
    if r['kleague_id']: g[(r['kleague_id'], r['team'], r['player_id'].split('-')[1])].append(r)
remap = {}; skipped = 0
for k, v in g.items():
    if len(v) < 2: continue
    if len({r['shirt_no'] for r in v}) != 1: skipped += 1; continue
    v.sort(key=lambda r: -ev[r['player_id']]); keep = v[0]
    for r in v[1:]:
        remap[r['player_id']] = keep['player_id']
        for f in ('birth_date', 'position'):
            if not keep[f] and r[f]: keep[f] = r[f]
for e in E:
    for f in ('player_id', 'related_player_id'):
        if e[f] in remap: e[f] = remap[e[f]]
R2 = [r for r in R if r['player_id'] not in remap]
c = collections.Counter((e['match_id'], e['player_id']) for e in E if e['type'] in ('START', 'SUB_IN'))
bad = [k for k, n in c.items() if n > 1]
print(f'합칠 행 {len(remap)} · 배번이 달라 보류 {skipped} · 합친 뒤 한 경기 중복 출전 {len(bad)} {bad[:3]}')
if apply and not bad:
    w = csv.DictWriter(open(D + '/roster.csv', 'w', encoding='utf-8', newline=''), fieldnames=rh); w.writeheader(); w.writerows(R2)
    w = csv.DictWriter(open(D + '/events.csv', 'w', encoding='utf-8', newline=''), fieldnames=eh); w.writeheader(); w.writerows(E)
    print('✓ 저장')
