#!/usr/bin/env python3
"""roster.csv 의 shirt_no 를 '경기 당시 배번'(경기장 그림 pitch 의 선발 배번)으로 바로잡는다.

배경: K리그 사이트의 선수 목록 표·이벤트 배번은 경기 당시 번호가 아니라 선수의 가장 최근 등록 번호다
(예: 2016 서울 데얀 표 27번, 실제 9번). 경기장 그림(선발 11명)의 번호는 경기 당시 번호와 맞다.
선발로 한 번이라도 나온 (kleague_id, 팀, 시즌)만 고칠 수 있고, 교체로만 나온 선수는 확인할 수 없어 그대로 둔다.
player_id 는 바꾸지 않는다 (이벤트 연결 유지).

사용: python3 tools/fix_shirts.py [--apply] LG:YEAR=RAW_DIR ...   (LG = 1 또는 2)
"""
import csv, json, os, sys, re
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, '..', 'data')
sys.path.insert(0, HERE)
from import_kleague import SHORT  # noqa: E402


def main():
    apply = '--apply' in sys.argv
    specs = [a for a in sys.argv[1:] if '=' in a]
    tname = {r['team_code']: r['name'] for r in csv.DictReader(open(os.path.join(D, 'teams.csv'), encoding='utf-8'))}
    shirts = defaultdict(Counter)   # (kleague_id, season YY, 팀 이름) -> 배번 Counter
    for sp in specs:
        key, path = sp.split('=', 1)
        lg, y = key.split(':'); yy = y[2:]
        idx = json.load(open(os.path.join(path, 'games_index.json'), encoding='utf-8'))
        tid = {}
        for g in idx:
            tid[g['homeTeam']] = tname[SHORT[g['homeTeamName']]]; tid[g['awayTeam']] = tname[SHORT[g['awayTeamName']]]
        for g in idx:
            f = os.path.join(path, 'games', str(g['gameId']), 'lineup.json')
            if not os.path.exists(f): continue
            for t, q, n, nm in json.load(open(f, encoding='utf-8')).get('pitch') or []:
                shirts[(q, yy, tid[t])][int(n)] += 1
    rows = list(csv.DictReader(open(os.path.join(D, 'roster.csv'), encoding='utf-8')))
    hdr = list(rows[0].keys())
    changed = same = unknown = multi = 0
    byseason = Counter()
    for r in rows:
        if not r['kleague_id']: continue
        yy = re.search(r'-(\d{2})-', r['player_id']).group(1)
        c = shirts.get((r['kleague_id'], yy, r['team']))
        if not c: unknown += 1; continue
        if len(c) > 1: multi += 1; continue
        n = next(iter(c))
        if int(r['shirt_no']) == n: same += 1
        else:
            changed += 1; byseason[yy] += 1
            if apply: r['shirt_no'] = str(n)
    print(f'바로잡음 {changed} · 이미 맞음 {same} · 선발 기록 없어 확인 불가 {unknown} · 한 시즌에 배번이 여러 개라 보류 {multi}')
    print('시즌별 바로잡음', dict(sorted(byseason.items())))
    if apply:
        w = csv.DictWriter(open(os.path.join(D, 'roster.csv'), 'w', encoding='utf-8', newline=''), fieldnames=hdr)
        w.writeheader(); w.writerows(rows)
        print('✓ 저장')
    else:
        print('(dry-run)')


if __name__ == '__main__':
    main()
