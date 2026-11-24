#!/usr/bin/env python3
"""ID 체계 변경(1회성): 팀 코드 2자리 → 3자리, 선수 Sub ID를 `팀코드-시즌-등번호`(예: DKR-26-07)로.
- 옛 ID → 새 ID 대응표를 data/id_map.csv 에 남김
- data/matches.csv, events.csv, roster.csv(, roster_draft_2026.csv)를 제자리에서 바꿈
"""
import csv, os, re, sys
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')
OLD2NEW = {'DK': 'DKR', 'JB': 'JBN', 'SH': 'SHG', 'PC': 'PCN', 'GJ': 'GYJ', 'YP': 'YPG', 'CW': 'CWN',
           'US': 'ULC', 'GN': 'GNG', 'MP': 'MKP', 'DJ': 'DJN', 'CC': 'CCN', 'BT': 'BTC', 'YJ': 'YJU'}
PID = re.compile(r'^([A-Z]{2})(\d{2})-(\d+)([b-j]?)$')
MID = re.compile(r'^(K3-\d{4}-\d{4})-([A-Z]{2})-([A-Z]{2})$')

def pid_new(x):
    m = PID.match(x)
    if not m: sys.exit('✗ 알 수 없는 player_id: ' + x)
    return f'{OLD2NEW[m[1]]}-{m[2]}-{int(m[3]):02d}{m[4]}'

def mid_new(x):
    m = MID.match(x)
    if not m: sys.exit('✗ 알 수 없는 match_id: ' + x)
    return f'{m[1]}-{OLD2NEW[m[2]]}-{OLD2NEW[m[3]]}'

def load(n):
    with open(os.path.join(D, n + '.csv'), encoding='utf-8', newline='') as f:
        r = csv.DictReader(f); return r.fieldnames, list(r)

def save(n, h, rows):
    with open(os.path.join(D, n + '.csv'), 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=h); w.writeheader(); w.writerows(rows)

idmap = []
for name, cols in (('matches', {'match_id': mid_new}), ('roster', {'player_id': pid_new}),
                   ('events', {'match_id': mid_new, 'player_id': pid_new, 'related_player_id': pid_new}),
                   ('roster_draft_2026', {'player_id': pid_new})):
    h, rows = load(name)
    for r in rows:
        for c, fn in cols.items():
            if r.get(c):
                new = fn(r[c])
                if name in ('matches', 'roster'): idmap.append(('match' if c == 'match_id' else 'player', r[c], new))
                r[c] = new
    save(name, h, rows)
news = [n for _, _, n in idmap]
assert len(news) == len(set(news)), '새 ID 중복'
save('id_map', ['kind', 'old_id', 'new_id'], [dict(kind=k, old_id=o, new_id=n) for k, o, n in idmap])
print(f'✓ 경기 {sum(1 for k,_,_ in idmap if k=="match")} · 선수 {sum(1 for k,_,_ in idmap if k=="player")} 건 변환, data/id_map.csv 저장')
