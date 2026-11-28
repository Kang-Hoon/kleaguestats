#!/usr/bin/env python3
"""K리그 공식 사이트 raw(JSON+HTML) → data/*.csv 반영.

사용:  python3 tools/import_kleague.py RAW_DIR --year 2025 --team all [--dry-run]
- RAW_DIR: games_index.json, games/<gameId>/{matchInfo.json, allDetail.json, match.html}
  (GitHub Actions 'kleague-probe'가 kleague-raw 브랜치에 만듦)
- --team: 팀 약칭(대전 등). 그 팀 경기만 반영 (상대 팀 선수도 출전 기록이 있으면 명단에 추가)
- 경기 시간: 전반 timeMin 그대로(45 초과는 추가시간), 후반은 45+timeMin(90 초과는 추가시간) = 사이트 득점자 표기와 같은 방식
- 선수 고유번호(playerId)는 roster.csv 의 kleague_id 열에 저장 (팀을 옮겨도 같은 사람이면 같은 번호)
"""
import argparse, csv, json, os, re, sys
from collections import Counter, defaultdict
from bs4 import BeautifulSoup

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')
SHORT = {'강원': 'GAN', '광주': 'GWA', '김천': 'GIM', '대전': 'DAE', '부천': 'BUC', '서울': 'SEO',
         '안양': 'ANY', '대구': 'DAG', '수원FC': 'SFC', '울산': 'ULS', '인천': 'INC', '전북': 'JEO', '제주': 'JEJ', '포항': 'POH'}
POS = {'GK': 'GK', 'LB': 'DF', 'RB': 'DF', 'CB': 'DF', 'LWB': 'DF', 'RWB': 'DF', 'SW': 'DF', 'DF': 'DF',
       'DM': 'MF', 'CM': 'MF', 'CAM': 'MF', 'AM': 'MF', 'LM': 'MF', 'RM': 'MF', 'MF': 'MF',
       'CF': 'FW', 'ST': 'FW', 'SS': 'FW', 'LW': 'FW', 'RW': 'FW', 'FW': 'FW'}
URL = 'https://www.kleague.com/match.do?year=%s&meetSeq=1&gameId=%s&leagueId=1&startTabNum=1'
ORD = {'START': 0, 'SUB_OUT': 1, 'SUB_IN': 2}


def rd(n):
    with open(os.path.join(D, n + '.csv'), encoding='utf-8', newline='') as f:
        r = csv.DictReader(f); return r.fieldnames, list(r)


def minute(half, t):
    m = t if half == 1 else 45 + t
    cap = 45 if half == 1 else 90
    return (cap, m - cap) if m > cap else (m, 0)


def parse_html(h):
    rows = {}   # playerId -> (teamId, backNo, pos, name)
    for tid, pid, no, pos, name in re.findall(r"playerDetailPop\('(K\d+)', '(\d+)'\)\"[^>]*>\s*<td>(\d+)</td>\s*<td>(\w+)</td>\s*<td>\s*([^<]+?)</td>", h):
        rows[pid] = (tid, int(no), pos, re.sub(r'\s*\([^)]*\)\s*$', '', name.strip()))
    s = BeautifulSoup(h, 'html.parser')
    starters = []   # [(backNo, name)] 표별
    for p in s.find_all('p'):
        if p.get_text(strip=True) == '선발 명단':
            tb = p.find_next('table'); cur = []
            for tr in tb.find('tbody').find_all('tr'):
                td = [x.get_text(' ', strip=True) for x in tr.find_all('td')]
                cur.append((int(td[0]), re.match(r'^(.+?)\(\d{2}\)', td[2]).group(1).strip(), re.search(r'\((\d{2})\)', td[2]).group(1)))
            starters.append(cur)
    return rows, starters


def load_lineup(d):
    """lineup.json(축소 raw) 또는 match.html(전체 raw) → parse_html 과 같은 형태"""
    lp = os.path.join(d, 'lineup.json')
    if not os.path.exists(lp): return parse_html(open(f'{d}/match.html', encoding='utf-8').read())
    j = json.load(open(lp, encoding='utf-8'))
    rows = {pid: (t, n, p, re.sub(r'\s*\([^)]*\)\s*$', '', nm.strip())) for pid, (t, n, p, nm) in j['rows'].items()}
    starters = [[(no, re.match(r'^(.+?)\(\d{2}\)', nm).group(1).strip(), re.search(r'\((\d{2})\)', nm).group(1)) for no, nm in tbl] for tbl in j['starters']]
    return rows, starters


def main():
    global D
    ap = argparse.ArgumentParser(); ap.add_argument('raw'); ap.add_argument('--team', default='all'); ap.add_argument('--year', default='2026')
    ap.add_argument('--dry-run', action='store_true'); ap.add_argument('--data', default=D); a = ap.parse_args()
    D = a.data
    th, trows = rd('teams'); tname = {t['team_code']: t['name'] for t in trows}
    mh, mrows = rd('matches'); rh, rrows = rd('roster'); eh, erows = rd('events')
    if 'kleague_id' not in rh: rh = rh + ['kleague_id']
    for r in rrows: r.setdefault('kleague_id', '')
    games = json.load(open(os.path.join(a.raw, 'games_index.json'), encoding='utf-8'))
    mine = games if a.team == 'all' else [g for g in games if a.team in (g['homeTeamName'], g['awayTeamName'])]
    YR = a.year; YY = YR[2:]
    have = {m['match_id'] for m in mrows}; n0 = max(int(re.sub(r'\D', '', e['event_id']) or 0) for e in erows)
    byk = {(r['kleague_id'], r['team'], re.search(r'-(\d{2})-', r['player_id']).group(1), int(r['shirt_no'])): r for r in rrows if r['kleague_id']}
    used = {r['player_id'] for r in rrows}
    posvote = defaultdict(Counter); log = []; errs = []; newm = []; newe = []; mindiff = []; skipped = []
    for g in sorted(mine, key=lambda x: (x['gameDate'], x['gameId'])):
        gid = str(g['gameId']); d = os.path.join(a.raw, 'games', gid)
        info = json.load(open(f'{d}/matchInfo.json', encoding='utf-8'))['data']
        if info.get('gameStatus') != 'FE': skipped.append(f"{g['gameDate']} {g['homeTeamName']}-{g['awayTeamName']} (경기 전/미종료)"); continue
        det = json.load(open(f'{d}/allDetail.json', encoding='utf-8'))['data']
        rows, starters = load_lineup(d)
        hc, ac = SHORT[g['homeTeamName']], SHORT[g['awayTeamName']]
        hid, aid = g['homeTeam'], g['awayTeam']; tid2code = {hid: hc, aid: ac}; tid2name = {hid: tname[hc], aid: tname[ac]}
        mid = f"K1-{YR}-{g['gameDate'][5:7]}{g['gameDate'][8:10]}-{hc}-{ac}"
        if mid in have: skipped.append(mid + ' (이미 있음)'); continue
        # 출전 선수 = 선발 명단 + 교체 투입 (사이트 상세 통계가 비어 있는 경기도 있어 이 방식이 기본, 통계가 있으면 대조)
        start = set()
        for tbl in starters:
            tteams = Counter(rows[c[0]][0] for c in ([pid for pid, (t, n, p, nm) in rows.items() if t in (hid, aid) and n == no and nm == name] for no, name, yy in tbl) if len(c) == 1)
            tt = tteams.most_common(1)[0][0] if tteams else None
            for no, name, yy in tbl:
                c = [pid for pid, (t, n, p, nm) in rows.items() if t in (hid, aid) and n == no and nm == name]
                if len(c) != 1 and tt:   # 이름 표기가 다르면(예: 표에는 별칭) 같은 팀·같은 배번의 선수로 매칭
                    c2 = [pid for pid, (t, n, p, nm) in rows.items() if t == tt and n == no]
                    if len(c2) == 1:
                        log.append(f'{mid}: 선발표 {no}.{name} = 선수 목록 {rows[c2[0]][3]} (같은 팀·배번, 이름 표기 다름 → 선수 목록의 이름 사용)'); c = c2
                if len(c) != 1: errs.append(f'{mid}: 선발 {no}.{name} 선수 매칭 {len(c)}건'); continue
                start.add(c[0])
        name2id = {(t, nm): pid for pid, (t, n, p, nm) in rows.items()}
        subin = set()
        for half, k in ((1, 'firstHalf'), (2, 'secondHalf')):
            for e in info.get(k) or []:
                if e['eventName'] == '교체':
                    pin = name2id.get((e['teamId'], e['playerName2'].strip()))
                    if not pin: errs.append(f"{mid}: 교체 IN {e['playerName2']} 못 찾음")
                    else: subin.add(pin)
        det_by = {p['playerId']: p for p in det['listH'] + det['listA']}
        if det_by and not any(p.get('minutePlay') for p in det_by.values()): det_by = {}   # 통계가 0으로만 채워진 경기
        applist = {pid: det_by.get(pid, {'playerName': rows[pid][3], 'playerPos': rows[pid][2], 'minutePlay': None}) for pid in start | subin}
        if det_by and set(det_by) != set(applist):
            log.append(f"{mid}: 출전 선수가 사이트 통계와 다름 (통계에만 {sorted(set(det_by)-set(applist))}, 명단에만 {sorted(set(applist)-set(det_by))})")
        if not det_by: log.append(f"{mid}: 사이트 선수 통계가 비어 있어 출전시간 대조는 생략")
        info_p = {pid: rows[pid] for pid in applist}
        for t in (hid, aid):
            if len([p for p in start if rows[p][0] == t]) != 11: errs.append(f'{mid}: {tid2name[t]} 선발 {len([p for p in start if rows[p][0]==t])}명')
        sides = defaultdict(list)
        for pid, (t, n, p, nm) in info_p.items(): sides[t].append(pid)
        for t in (hid, aid):
            if len([p for p in start if rows[p][0] == t]) != 11: errs.append(f'{mid}: {tid2name[t]} 선발 {len([p for p in start if rows[p][0]==t])}명')
        # 선수 → player_id
        pidmap = {}
        for pid, (t, n, p, nm) in info_p.items():
            key = (pid, tid2name[t], YY, n); r = byk.get(key)
            if not r:
                code = tid2code[t]; base = f'{code}-{YY}-{n:02d}'; i = base; suf = iter('bcdefghij')
                while i in used: i = base + next(suf)
                used.add(i)
                r = dict(player_id=i, name=nm, birth_date='', position='', team=tid2name[t], shirt_no=str(n),
                         source='https://www.kleague.com/match.do', kleague_id=pid)
                rrows.append(r); byk[key] = r; log.append(f'새 선수 {r["team"]} {n}번 {nm} ({pid})')
            pidmap[pid] = r['player_id']; posvote[r['player_id']][POS.get(applist[pid]['playerPos'], applist[pid]['playerPos'])] += 1
        ev = []
        def add(m, typ, pid, rel=None, team=None, half=1):
            for q in (pid, rel):
                if q and q not in pidmap: raise KeyError(f"{mid}: 이벤트 선수 {q} ({rows.get(q)}) 가 출전 명단에 없음 (선발 {len(start)}, 교체투입 {len(subin)})")
            ev.append(dict(_h=half, minute=m[0], extra_minute=m[1] or '', type=typ, player_id=pidmap[pid], team=team or tid2name[rows[pid][0]],
                           related_player_id=pidmap[rel] if rel else '', note=''))
        for pid in applist:
            if pid in start: add((0, 0), 'START', pid)
        tl = []
        for half, k in ((1, 'firstHalf'), (2, 'secondHalf')):
            for e in info.get(k) or []:
                if e['eventName'] in ('득점', '도움', '자책골', '경고', '퇴장', '교체'): tl.append((half, e))
        used_assist = set()
        for half, e in tl:
            m = minute(half, e['timeMin'])
            if e['eventName'] in ('경고', '퇴장') and e['playerId'] not in pidmap:
                log.append(f"{mid}: 출전하지 않은 벤치 선수 {e['eventName']} {e['timeMin']}분 {e['playerName']}({e['backNo']}) — 출전 기록이 없어 반영 안 함"); continue
            if e['eventName'] in ('경고', '퇴장'):
                add(m, 'YELLOW' if e['eventName'] == '경고' else 'RED', e['playerId'], half=half)
            elif e['eventName'] == '교체':
                pin = name2id.get((e['teamId'], e['playerName2'].strip()))
                if not pin: errs.append(f"{mid}: 교체 IN {e['playerName2']} 못 찾음"); continue
                add(m, 'SUB_OUT', e['playerId'], pin, half=half); add(m, 'SUB_IN', pin, e['playerId'], half=half)
            elif e['eventName'] == '득점':
                cand = [x for x in tl if x[1]['eventName'] == '도움' and x[0] == half and x[1]['timeMin'] == e['timeMin'] and x[1]['teamId'] == e['teamId'] and id(x[1]) not in used_assist]
                rel = None
                if cand: used_assist.add(id(cand[0][1])); rel = cand[0][1]['playerId']
                add(m, 'GOAL', e['playerId'], rel, half=half)
            elif e['eventName'] == '자책골':
                other = aid if rows[e['playerId']][0] == hid else hid
                add(m, 'OWN_GOAL', e['playerId'], team=tid2name[other], half=half)
        if len(used_assist) != sum(1 for h_, e in tl if e['eventName'] == '도움'): errs.append(f'{mid}: 짝 없는 도움')
        ev.sort(key=lambda x: (x['minute'], x['extra_minute'] or 0, ORD.get(x['type'], 3)))
        for t, sc in ((hid, info['homeGoal']), (aid, info['awayGoal'])):
            n = sum(1 for x in ev if x['team'] == tid2name[t] and x['type'] in ('GOAL', 'OWN_GOAL'))
            if n != sc: errs.append(f'{mid}: {tid2name[t]} 득점 이벤트 {n} ≠ 점수 {sc}')
        fh = max((e['timeMin'] for e in info.get('firstHalf') or [] if e['eventName'] == '전반종료'), default=None)
        sh = max((e['timeMin'] for e in info.get('secondHalf') or [] if e['eventName'] == '경기종료'), default=None)
        # 출전시간 대조 (이벤트로 계산 vs 사이트 minutePlay)
        fhl, total = fh or 45, (fh or 45) + (sh or 45)
        el = lambda x: (x['minute'] + (x['extra_minute'] or 0)) if x['_h'] == 1 else fhl + x['minute'] + (x['extra_minute'] or 0) - 45
        for pid, p in applist.items():
            me = [x for x in ev if x['player_id'] == pidmap[pid]]
            t_in = 0 if pid in start else next((el(x) for x in me if x['type'] == 'SUB_IN'), None)
            t_out = next((el(x) for x in me if x['type'] in ('SUB_OUT', 'RED')), total)
            if t_in is None: errs.append(f"{mid}: {p['playerName']} 선발도 교체투입도 아닌데 출전 기록 있음"); continue
            mp = p.get('minutePlay')
            if mp is not None and abs((t_out - t_in) - mp) > 1: mindiff.append(f"{mid} {p['playerName']}: 계산 {t_out - t_in} / 사이트 {mp}")
        newm.append(dict(match_id=mid, season=YR, league='K리그1', round=str(g['_round']), date=g['gameDate'].replace('/', '-'),
                         venue=g.get('fieldNameFull', ''), home_team=tid2name[hid], away_team=tid2name[aid],
                         home_score=str(info['homeGoal']), away_score=str(info['awayGoal']), attendance='', source=URL % (YR, gid),
                         first_half_extra=str(fh - 45) if fh and fh > 45 else '', second_half_extra=str(sh - 45) if sh and sh > 45 else ''))
        for x in ev:
            n0 += 1; x.update(event_id=f'E{n0:05d}', match_id=mid, source=URL % (YR, gid)); newe.append(x)
    for r in rrows:
        v = posvote.get(r['player_id'])
        if v and not r['position']: r['position'] = v.most_common(1)[0][0]
    print(f'신규 경기 {len(newm)} · 이벤트 {len(newe)} · 새 선수 {sum(1 for l in log if l.startswith("새 선수"))}')
    for s_ in skipped: print('  건너뜀:', s_)
    for l_ in log:
        if not l_.startswith('새 선수'): print('  참고:', l_)
    bym = Counter(x.split(' ')[0] for x in mindiff)
    print(f'출전시간 대조: 사이트 통계와 어긋난 선수 {len(mindiff)}명 / 경기 {len(bym)}건 (경기 전체가 같은 값만큼 어긋남)')
    for k_, n_ in sorted(bym.items()):
        diffs = Counter(int(m.group(2)) - int(m.group(1)) for m in (re.search(r'계산 (-?\d+) / 사이트 (-?\d+)', x) for x in mindiff if x.startswith(k_)) if m)
        print('   ', k_, '사이트-계산 차이(분):', dict(diffs))
    if errs: sys.exit('✗ 문제:\n  - ' + '\n  - '.join(errs[:40]))
    if a.dry_run: print('(dry-run)'); return
    mrows += newm; erows += newe
    for name, h, rows_ in (('matches', mh, mrows), ('roster', rh, rrows), ('events', eh, erows)):
        with open(os.path.join(D, name + '.csv'), 'w', encoding='utf-8', newline='') as f:
            w = csv.DictWriter(f, fieldnames=h, extrasaction='ignore'); w.writeheader(); w.writerows(rows_)
    print('✓ 저장')

if __name__ == '__main__':
    main()
