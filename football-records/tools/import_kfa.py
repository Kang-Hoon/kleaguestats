#!/usr/bin/env python3
"""KFA 경기 상세 HTML(raw 폴더) → data/*.csv 일괄 반영.

사용:  python3 tools/import_kfa.py RAW_DIR [--dry-run]
- RAW_DIR 에는 index.json 과 m_<s_idx>.html 이 있어야 함 (GitHub Actions 'kfa-fetch-raw' 가 만듦)
- 득점·도움·자책골·경고·퇴장·교체·선발을 events.csv 로, 처음 보는 선수는 roster.csv(생년월일 빈칸)에 추가
- 이미 이벤트가 있는 경기는 기존 내용과 대조해 같으면 도움만 채우고, 다르면 멈춤
- KFA가 득점자 기록을 비워 둔 경기(득점 수 ≠ 점수)는 이벤트 없이 스코어만 둠
"""
import argparse, csv, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kfa_html import parse_html
from add_match import TEAMS

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')
SRC = 'https://www.kfa.or.kr/competition/k3_2026.php'
# KFA 표기 → 사이트 등록명 (사용자 지정: 이름이 다르면 등록명 사용)
ALIAS = {('부산교통공사축구단', 'rabens jan'): '얀 라벤스', ('여주FC', 'ISHII KAISEI'): '이시이'}
ORD = {'START': 0, 'SUB_OUT': 1, 'SUB_IN': 2}


def rd(d, n):
    with open(os.path.join(d, n + '.csv'), encoding='utf-8', newline='') as f:
        r = csv.DictReader(f); return r.fieldnames, list(r)


def build(p, rrows, rnd, log):
    """한 경기의 (match_id, 이벤트 목록). 새 선수는 rrows에 추가."""
    (hn, hc), (an, ac) = TEAMS[p['home']], TEAMS[p['away']]
    mid = f"K3-2026-{p['date'][5:7]}{p['date'][8:10]}-{hc}-{ac}"
    pid = {}
    for (site, code), s in zip(((hn, hc), (an, ac)), p['sides']):
        byname = {}
        for r in rrows:
            if r['team'] == site: byname.setdefault(r['name'], []).append(r)
        used = {r['player_id'] for r in rrows}; taken = set()
        for no in s['order']:
            name, pos = s['players'][no]
            name = ALIAS.get((site, name), name)
            cands = [r for r in byname.get(name, []) if r['player_id'] not in taken]
            hit = None
            if len(cands) == 1 and len(byname.get(name, [])) == 1: hit = cands[0]
            elif cands:
                same = [r for r in cands if r['shirt_no'] == str(no)]
                hit = same[0] if same else (cands[0] if len(cands) == 1 else None)
            if hit: pid[(s['name'], no)] = hit['player_id']; taken.add(hit['player_id']); continue
            i = f"{code}-26-{no:02d}"; base, suf = i, iter('bcdefghij')
            while i in used: i = base + next(suf)
            used.add(i); taken.add(i); pid[(s['name'], no)] = i
            row = dict(player_id=i, name=name, birth_date='', position=pos, team=site, shirt_no=str(no), source=SRC)
            rrows.append(row); byname.setdefault(name, []).append(row)
            log.append(f"새 선수 {site} {no}번 {name}")
    ev = []
    def add(m, t, si, no, rel=None, team=None, pk=False):
        s = p['sides'][si]
        ev.append(dict(minute=m[0], extra_minute=m[1] or '', type=t, player_id=pid[(s['name'], no)], team=team or TEAMS[s['name']][0],
                       related_player_id=pid[(s['name'], rel)] if rel else '', note='PK' if (pk and t == 'GOAL') else ''))
    for si, s in enumerate(p['sides']):
        o = p['sides'][1 - si]
        for no in s['order']:
            if no not in s['bench']: add((0, 0), 'START', si, no)
        asst = list(s['assists'])
        for no, mn in s['goals']:
            j = next((k for k, (a, am) in enumerate(asst) if am[:2] == mn[:2] and a != no), None)
            rel = asst.pop(j)[0] if j is not None else None
            add(mn[:2], 'GOAL', si, no, rel, pk=mn[2])
        if asst: raise ValueError(f"{mid} {s['name']}: 짝 없는 도움 {asst}")
        for no, name, mn in s['own']:   # 상대 선수의 자책골 → 선수는 상대편, team은 점수를 얻은 쪽
            if o['players'].get(no, (None,))[0] != name: raise ValueError(f"{mid}: 자책골 선수 {no}.{name} 가 상대 명단에 없음")
            add(mn[:2], 'OWN_GOAL', 1 - si, no, team=TEAMS[s['name']][0])
        for t, no, mn in s['cards']: add(mn[:2], t, si, no)
        ins = {}
        for kind, no, mn in s['subs']: ins.setdefault(mn[:2], {}).setdefault(kind, []).append(no)
        for mn, d in ins.items():
            if len(d.get('IN', [])) != len(d.get('OUT', [])): raise ValueError(f"{mid} {s['name']}: {mn} 교체 IN/OUT 짝 불일치")
            for i_no, o_no in zip(d['IN'], d['OUT']):
                add(mn, 'SUB_OUT', si, o_no, i_no); add(mn, 'SUB_IN', si, i_no, o_no)
    ev.sort(key=lambda e: (e['minute'], e['extra_minute'] or 0, ORD.get(e['type'], 3)))
    return mid, ev


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('raw'); ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--data', default=DATA); a = ap.parse_args()
    ix = json.load(open(os.path.join(a.raw, 'index.json')))
    mh, mrows = rd(a.data, 'matches'); rh, rrows = rd(a.data, 'roster'); eh, erows = rd(a.data, 'events')
    if 'note' not in eh: eh = eh + ['note']
    have = {}
    for e in erows: have.setdefault(e['match_id'], []).append(e)
    mby = {m['match_id']: m for m in mrows}
    n0 = max(int(re.sub(r'\D', '', e['event_id']) or 0) for e in erows)
    added = filled = skipped = 0; log = []; problems = []
    for e in sorted(ix, key=lambda x: (x['round'], x['order'])):
        p = parse_html(open(os.path.join(a.raw, f"m_{e['s_idx']}.html"), encoding='utf-8').read())
        for k, s in enumerate(p['sides']):
            if len(s['goals']) + len(s['own']) != p['total'][k] and not (not s['goals'] and not s['own'] and not p['sides'][1 - k]['goals']):
                problems.append(f"{e['s_idx']} {s['name']}: 득점 {len(s['goals'])}+자책 {len(s['own'])} ≠ 점수 {p['total'][k]}")
        if sum(len(s['goals']) + len(s['own']) for s in p['sides']) != sum(p['total']):
            skipped += 1; log.append(f"스코어만 유지: {e['s_idx']} R{e['round']} {p['home']} {p['total'][0]}-{p['total'][1]} {p['away']} (KFA에 득점 기록 없음)"); continue
        r_before = len(rrows)
        mid, ev = build(p, rrows, e['round'], log)
        m = mby.get(mid)
        if not m: problems.append(f'{mid}: matches.csv에 없음'); continue
        if (m['home_score'], m['away_score']) != tuple(map(str, p['total'])): problems.append(f"{mid}: 점수 불일치"); continue
        if mid in have:
            key = lambda x: (str(x['minute']), str(x['extra_minute'] or ''), x['type'], x['player_id'], x['team'])
            old = have[mid]
            if sorted(map(key, old)) != sorted(map(key, ev)): problems.append(f'{mid}: 기존 이벤트와 다름'); continue
            for g in [x for x in ev if x['related_player_id'] and x['type'] == 'GOAL']:
                t = next(o for o in old if o['type'] == 'GOAL' and o['player_id'] == g['player_id'] and str(o['minute']) == str(g['minute']))
                t['related_player_id'] = g['related_player_id']; filled += 1
            continue
        for x in ev:
            n0 += 1; x.update(event_id=f'E{n0:05d}', match_id=mid, source=SRC); erows.append(x)
        added += 1
    print(f'새로 이벤트 넣은 경기 {added} · 기존 경기 도움 채움 {filled}건 · 스코어만 {skipped}')
    print(f'이벤트 총 {len(erows)} · 선수 총 {len(rrows)}')
    for l in log: print('  ·', l)
    if problems: sys.exit('✗ 문제:\n  - ' + '\n  - '.join(problems))
    if a.dry_run: print('(dry-run)'); return
    for name, h, rows in (('matches', mh, mrows), ('roster', rh, rrows), ('events', eh, erows)):
        with open(os.path.join(a.data, name + '.csv'), 'w', encoding='utf-8', newline='') as f:
            w = csv.DictWriter(f, fieldnames=h, extrasaction='ignore'); w.writeheader(); w.writerows(rows)
    print('✓ 저장')

if __name__ == '__main__':
    main()
