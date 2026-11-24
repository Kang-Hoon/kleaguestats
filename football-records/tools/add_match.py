#!/usr/bin/env python3
"""KFA 경기 기록 페이지를 복사해 붙인 텍스트 → data/*.csv 에 추가.

사용:  python3 tools/add_match.py paste.txt --round 2 [--dry-run]
- 득점·경고·퇴장·교체·선발을 events.csv, 경기 정보를 matches.csv, 처음 보는 선수를 roster.csv(생년월일 빈칸)에 추가
- 스코어(전/후반 포함)와 득점 이벤트가 안 맞거나 구조가 이상하면 아무것도 쓰지 않고 멈춤
"""
import argparse, csv, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, '..', 'data')
SRC_DEFAULT = 'https://www.kfa.or.kr/competition/k3_2026.php'
# 페이지 표기 → (사이트에서 쓰는 이름, match_id/player_id용 코드)
TEAMS = {
    '대전코레일FC': ('대전 코레일 FC', 'DKR'),
    '전북현대모터스': ('전북현대모터스', 'JBN'),
    '춘천시민축구단': ('춘천시민축구단', 'CCN'),
    '부산교통공사축구단': ('부산교통공사축구단', 'BTC'),
    '경주한수원FC': ('경주한수원FC', 'GYJ'),
    '포천시민축구단': ('포천시민축구단', 'PCN'),
    '시흥시민축구단': ('시흥시민축구단', 'SHG'),
    '양평FC': ('양평FC', 'YPG'),
    '창원FC': ('창원FC', 'CWN'),
    '울산시민축구단': ('울산시민축구단', 'ULC'),
    'FC강릉': ('FC강릉', 'GNG'),
    '당진시민축구단': ('당진시민축구단', 'DJN'),
    'FC목포': ('FC목포', 'MKP'),
    '여주FC': ('여주FC', 'YJU'),
}
MIN = re.compile(r'(\d+)(?:\s*\(\+(\d+)\))?(\(P\))?')  # 45(+5) 추가시간, (P) 페널티킥
PLAYER = re.compile(r'^(\d+)\.\s*(.+?)\[(GK|DF|MF|FW)\]$')
SUB = re.compile(r'^[▲▼]\s*(IN|OUT)$')


def die(msg):
    sys.exit('✗ ' + msg)


def minutes(cell):
    return [(int(a), int(b) if b else 0, bool(c)) for a, b, c in MIN.findall(cell or '')]


def parse(text):
    lines = [l.rstrip('\r') for l in text.splitlines()]
    teamlines = [(i, m) for i, l in enumerate(lines) if (m := re.match(r'^(.+?)\1(\d+)$', l.strip()))]
    if len(teamlines) < 2:
        die('팀/점수 줄을 찾지 못했어요 (예: "대전코레일FC대전코레일FC3")')
    (hi, hm), (ai, am) = teamlines[0], teamlines[1]
    home, away = hm.group(1), am.group(1)
    total = (int(hm.group(2)), int(am.group(2)))
    half = {}
    for l in lines[hi:ai]:
        m = re.match(r'^(\d+)(전반전|후반전|연장전반|연장후반|승부차기)(\d+)$', l.strip())
        if m: half[m.group(2)] = (int(m.group(1)), int(m.group(3)))
    foot = next((l for l in lines if l.startswith('대회')), None)
    f = foot and re.search(r'관중(\d+)경기명(.+?) vs (.+?)주심.*?일시(\d{4}-\d{2}-\d{2}).*?장소(.+?)대기심', foot)
    if not f: die('맨 아래 "대회… 관중… 경기명… 일시… 장소…" 줄을 읽지 못했어요')
    attendance, fh, fa, date, venue = int(f.group(1)), f.group(2).strip(), f.group(3).strip(), f.group(4), f.group(5).strip()
    if (fh, fa) != (home, away): die(f'경기명({fh} vs {fa})과 점수 줄({home} vs {away})의 홈/원정이 달라요')

    sides = [dict(name=home, players={}, order=[], goals=[], cards=[], subs=[], bench=set()),
             dict(name=away, players={}, order=[], goals=[], cards=[], subs=[], bench=set())]
    blk, bench, pend = -1, False, {}
    for l in lines[ai + 1:]:
        s = l.strip()
        if s.startswith('대회2026') or re.match(r'^대회\d{4}', s): break  # 맨 아래 경기 정보 줄에서 끝 (그 뒤 메뉴 글자는 무시)
        if s.startswith('선발출전선수'): blk += 1; bench = False; continue
        if s.startswith('후보선수'): bench = True; continue
        if not s or s.startswith('선수명') or s.startswith('대회') or blk < 0: continue
        cols = l.split('\t'); cols += [''] * (4 - len(cols))
        side = sides[min(blk, 1)]
        if cols[0].strip().startswith('상대자책골'):
            if minutes(' '.join(cols[1:])): die('상대자책골이 있어요. 누가 넣었는지 페이지에 없으니 직접 확인해 입력해 주세요')
            continue
        m = SUB.match(cols[0].strip())
        if m:
            mm = re.match(r'^(\d+)\.', cols[1].strip())
            t = minutes(cols[2])
            if not mm or not t: die('교체 줄을 읽지 못했어요: ' + l)
            pend.setdefault((blk, t[0]), {})[m.group(1)] = int(mm.group(1))
            side['subs'].append((m.group(1), int(mm.group(1)), t[0]))
            continue
        m = PLAYER.match(cols[0].strip())
        if not m: die('알 수 없는 줄: ' + repr(l))
        no, name, pos = int(m.group(1)), m.group(2).strip(), m.group(3)
        side['players'][no] = (name, pos)
        side['order'].append(no)
        (side['bench'].add(no) if bench else None)
        for mn in minutes(cols[1]): side['goals'].append((no, mn))
        for mn in minutes(cols[2]): side['cards'].append(('YELLOW', no, mn))
        for mn in minutes(cols[3]): side['cards'].append(('RED', no, mn))
    return dict(home=home, away=away, total=total, half=half, attendance=attendance,
                date=date, venue=venue, sides=sides)


def check(p):
    errs = []
    for k, s in enumerate(p['sides']):
        starters = [n for n in s['order'] if n not in s['bench']]
        if len(starters) != 11: errs.append(f"{s['name']}: 선발이 {len(starters)}명이에요")
        if len(s['players']) != len(s['order']): errs.append(f"{s['name']}: 등번호 중복")
        for kind, no, _ in s['subs']:
            if no not in s['players']: errs.append(f"{s['name']}: 교체 등번호 {no} 선수가 명단에 없어요")
        if len([x for x in s['subs'] if x[0] == 'IN']) != len([x for x in s['subs'] if x[0] == 'OUT']): errs.append(f"{s['name']}: IN/OUT 수가 달라요")
        if len(s['goals']) != p['total'][k]: errs.append(f"{s['name']}: 득점 {len(s['goals'])}골인데 점수는 {p['total'][k]}")
        h1 = sum(1 for _, (m, x, _p) in s['goals'] if m <= 45)
        if 'half' in p and '전반전' in p['half'] and p['half']['전반전'][k] != h1:
            errs.append(f"{s['name']}: 전반 득점 {h1}골인데 페이지는 {p['half']['전반전'][k]}")
    return errs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('paste'); ap.add_argument('--round', type=int, required=True)
    ap.add_argument('--season', type=int, default=2026); ap.add_argument('--league', default='K3리그')
    ap.add_argument('--source', default=SRC_DEFAULT); ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--data', default=DATA)
    a = ap.parse_args()
    p = parse(open(a.paste, encoding='utf-8').read())
    for t in (p['home'], p['away']):
        if t not in TEAMS: die(f'모르는 팀 "{t}" — tools/add_match.py의 TEAMS에 (사이트 이름, 코드)를 추가해 주세요')
    errs = check(p)
    if errs: die('검증 실패:\n  - ' + '\n  - '.join(errs))

    def rd(n):
        with open(os.path.join(a.data, n + '.csv'), encoding='utf-8', newline='') as f:
            r = csv.DictReader(f); return r.fieldnames, list(r)
    mh, mrows = rd('matches'); rh, rrows = rd('roster'); eh, erows = rd('events')
    if 'note' not in eh: eh = eh + ['note']  # 선택 컬럼: 페널티킥 등 메모
    (hn, hc), (an, ac) = TEAMS[p['home']], TEAMS[p['away']]
    mid = f"K3-{a.season}-{p['date'][5:7]}{p['date'][8:10]}-{hc}-{ac}"
    old = [r for r in mrows if r['match_id'] == mid]
    if old:
        if any(e['match_id'] == mid for e in erows): die(f'이미 이벤트까지 있는 경기예요: {mid}')
        o = old[0]  # 스코어만 먼저 넣어 둔 경기 → 상세 기록으로 교체
        if (o['home_score'], o['away_score']) != (str(p['total'][0]), str(p['total'][1])):
            die(f"먼저 넣어 둔 스코어({o['home_score']}-{o['away_score']})와 붙여 넣은 스코어({p['total'][0]}-{p['total'][1]})가 달라요")
        mrows = [r for r in mrows if r['match_id'] != mid]

    pid, new_players = {}, []
    for (site, code), s in zip((TEAMS[p['home']], TEAMS[p['away']]), p['sides']):
        byname = {}
        for r in rrows:
            if r['team'] == site: byname.setdefault(r['name'], []).append(r)
        used = {r['player_id'] for r in rrows}
        taken = set()  # 이 경기에서 이미 배정된 player_id (동명이인 구분용)
        for no in s['order']:
            name, pos = s['players'][no]
            cands = [r for r in byname.get(name, []) if r['player_id'] not in taken]
            hit = None
            if len(cands) == 1 and len(byname.get(name, [])) == 1: hit = cands[0]
            elif cands:  # 같은 이름이 여러 명 → 등번호가 같은 사람
                same = [r for r in cands if r['shirt_no'] == str(no)]
                hit = same[0] if same else None
                if not hit and len(cands) == 1: hit = cands[0]
            if hit:
                pid[(s['name'], no)] = hit['player_id']; taken.add(hit['player_id']); continue
            i = f"{code}-{str(a.season)[2:]}-{no:02d}"
            base, suf = i, iter('bcdefghij')
            while i in used: i = base + next(suf)
            used.add(i); taken.add(i); pid[(s['name'], no)] = i
            row = dict(player_id=i, name=name, birth_date='', position=pos, team=site, shirt_no=str(no), source=a.source)
            rrows.append(row); byname.setdefault(name, []).append(row); new_players.append((site, no, name))
            if len(byname[name]) > 1: print(f"  ※ 동명이인: {site} {name} — 등번호 {', '.join(r['shirt_no'] for r in byname[name])}")

    n0 = max([int(re.sub(r'\D', '', r['event_id']) or 0) for r in erows] + [0])
    ev = []
    def add(m, t, side, no, rel=None):
        mn, ex, pk = m[0], m[1], len(m) > 2 and m[2]
        ev.append(dict(minute=mn, extra_minute=ex or '', type=t, player_id=pid[(side['name'], no)], team=TEAMS[side['name']][0],
                       related_player_id=pid[(side['name'], rel)] if rel else '', note='PK' if pk and t == 'GOAL' else ''))
    for s in p['sides']:
        for no in s['order']:
            if no not in s['bench']: add((0, 0, False), 'START', s, no)
        for no, mn in s['goals']: add(mn, 'GOAL', s, no)
        for t, no, mn in s['cards']: add(mn, t, s, no)
        ins = {}
        for kind, no, mn in s['subs']: ins.setdefault(mn, {}).setdefault(kind, []).append(no)
        for mn, d in ins.items():
            if len(d.get('IN', [])) != len(d.get('OUT', [])): die(f"{s['name']}: {mn} 교체 IN/OUT 짝이 안 맞아요")
            for i_no, o_no in zip(d['IN'], d['OUT']):
                add(mn, 'SUB_OUT', s, o_no, i_no); add(mn, 'SUB_IN', s, i_no, o_no)
    key = lambda e: (e['minute'], e['extra_minute'] or 0, {'START': 0, 'SUB_OUT': 1, 'SUB_IN': 2}.get(e['type'], 3))
    ev.sort(key=key)
    for i, e in enumerate(ev, 1):
        e.update(event_id=f'E{n0 + i:05d}', match_id=mid, source=a.source)
        erows.append(e)
    mrows.append(dict(match_id=mid, season=a.season, league=a.league, round=a.round, date=p['date'], venue=p['venue'],
                      home_team=hn, away_team=an, home_score=p['total'][0], away_score=p['total'][1],
                      attendance=p['attendance'], source=a.source, first_half_extra='', second_half_extra=''))

    print(f"{mid}  {hn} {p['total'][0]}-{p['total'][1]} {an}  R{a.round}  {p['date']}  {p['venue']}  관중 {p['attendance']}")
    print(f"이벤트 {len(ev)}건 · 새 선수 {len(new_players)}명 (생년월일 빈칸)")
    if any(t == '대전 코레일 FC' for t, _, _ in new_players):
        print('  ※ 대전 코레일 명단에 없던 선수:', ', '.join(f'{n}번 {x}' for t, n, x in new_players if t == '대전 코레일 FC'))
    if a.dry_run: print('(dry-run: 파일은 바꾸지 않았어요)'); return
    for name, h, rows in (('matches', mh, mrows), ('roster', rh, rrows), ('events', eh, erows)):
        with open(os.path.join(a.data, name + '.csv'), 'w', encoding='utf-8', newline='') as f:
            w = csv.DictWriter(f, fieldnames=h, extrasaction='ignore'); w.writeheader(); w.writerows(rows)
    print('✓ data/ 에 추가했어요')

if __name__ == '__main__':
    main()
