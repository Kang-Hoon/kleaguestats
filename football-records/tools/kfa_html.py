#!/usr/bin/env python3
"""KFA 경기 상세 페이지(HTML) → add_match.parse() 와 같은 모양의 dict.

HTML 에는 화면에 안 보이는(주석 처리된) '시간'(출전 시간)과 '도움' 열이 있어서 그것도 함께 읽는다.
  p['sides'][k]['assists'] : [(등번호, (분, 추가시간, False)), ...]
  p['sides'][k]['time']    : {등번호: KFA가 적어 둔 출전 시간(분)}
  p['sides'][k]['own']     : 이 팀이 얻은 상대 자책골 [(상대선수 등번호, 이름, (분, 추가시간, False))]
"""
import re
from bs4 import BeautifulSoup, Comment

MIN = re.compile(r'(\d+)(?:\s*\(\+(\d+)\))?(\(P\))?')
PLAYER = re.compile(r'^(\d+)\.\s*(.+?)\[(GK|DF|MF|FW)\]$')


def minutes(cell):
    return [(int(a), int(b) if b else 0, bool(c)) for a, b, c in MIN.findall(cell or '')]


def _cells(tr):
    """tr 안의 td 와 주석(<!-- <td>..</td> -->)을 나온 순서대로 텍스트로."""
    out = []
    for n in tr.children:
        if isinstance(n, Comment):
            s = re.sub(r'<[^>]+>', '', str(n)).strip()
            if str(n).strip().startswith('<td'): out.append(('c', s))
        elif getattr(n, 'name', None) == 'td':
            out.append(('t', n.get_text(' ', strip=True)))
    return out


def parse_html(html):
    soup = BeautifulSoup(html, 'lxml')
    L, R = soup.select_one('.player_left'), soup.select_one('.player_right')
    home, away = [x.select('p')[1].get_text(strip=True) for x in (L, R)]
    total = []
    for x in (L, R):
        ps = [p.get_text(strip=True) for p in x.select('p')]
        total.append(int(ps[-1]))
    half = {}
    for li in soup.select('.result_score li p'):
        sp = li.select('span')
        label = re.sub(r'\d+', '', li.get_text('', strip=True))
        half[label] = (int(sp[0].get_text(strip=True)), int(sp[1].get_text(strip=True)))
    info = {}
    for li in soup.select('.cup_info li'):
        k = li.select_one('span').get_text(strip=True)
        info[k] = li.get_text('', strip=True)[len(k):]
    m = re.match(r'(\d{4}-\d{2}-\d{2})', info.get('일시', ''))
    date = m.group(1)
    sides = []
    for box in (soup.select_one('.left_table'), soup.select_one('.right_table')):
        s = dict(players={}, order=[], goals=[], cards=[], subs=[], bench=set(), assists=[], time={}, own=[])
        for tb in box.find_all('table', recursive=False) if False else box.select('table'):
            cap = tb.find('caption')
            cap = cap.get_text(strip=True) if cap else ''
            if cap in ('선발출전선수', '후보선수'):
                bench = cap == '후보선수'
                for tr in tb.select('tbody tr'):
                    c = _cells(tr)
                    if not c: continue
                    pm = PLAYER.match(c[0][1])
                    if not pm: raise ValueError('선수 줄 형식 이상: ' + c[0][1])
                    no, name, pos = int(pm.group(1)), pm.group(2).strip(), pm.group(3)
                    # 순서: 이름, [시간], 득점, [도움], 경고, 퇴장
                    vals = [v for _, v in c[1:]]
                    if len(vals) != 5: raise ValueError(f'열 수 이상({len(vals)}): {c}')
                    tm, goal, ast, yel, red = vals
                    s['players'][no] = (name, pos); s['order'].append(no)
                    if bench: s['bench'].add(no)
                    if tm != '': s['time'][no] = int(re.match(r'\d+', tm).group(0))
                    for mn in minutes(goal): s['goals'].append((no, mn))
                    for mn in minutes(ast): s['assists'].append((no, mn))
                    for mn in minutes(yel): s['cards'].append(('YELLOW', no, mn))
                    for mn in minutes(red): s['cards'].append(('RED', no, mn))
            elif tb.find(string=re.compile('상대자책골')):
                # 상대 선수의 자책골(이 팀이 득점). 칸: 라벨 / "등번호.이름" / 분
                for tr in tb.select('tr'):
                    tds = [td.get_text(' ', strip=True) for td in tr.select('td')]
                    if len(tds) < 3 or not tds[1]: continue
                    pm = re.match(r'^(\d+)\.\s*(.+)$', tds[1])
                    mn = minutes(tds[2])
                    if not pm or not mn: raise ValueError('자책골 줄 이상: ' + repr(tds))
                    s['own'].append((int(pm.group(1)), pm.group(2).strip(), mn[0]))
        for tr in box.select('.change_list tr'):
            th = tr.find('th'); tds = tr.find_all('td')
            if not th or len(tds) < 2: continue
            kind = 'IN' if 'IN' in th.get_text() else 'OUT'
            nm = re.match(r'^(\d+)\.', tds[0].get_text(strip=True))
            t = minutes(tds[1].get_text(' ', strip=True))
            if not nm or not t: raise ValueError('교체 줄 이상')
            s['subs'].append((kind, int(nm.group(1)), t[0]))
        sides.append(s)
    for s, nm in zip(sides, (home, away)): s['name'] = nm
    return dict(home=home, away=away, total=tuple(total), half=half, attendance=int(info['관중'].replace(',', '')),
                date=date, venue=info['장소'], sides=sides, referee=info.get('주심', ''))
