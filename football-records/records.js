/*
 * 기록 계산 모듈 (브라우저와 Node 양쪽에서 동작)
 *
 * 입력: matches / roster / events 세 CSV를 읽은 배열
 * 출력: 구단·리그 단위 기록 목록, 그리고 데이터 점검 결과
 *
 * 원칙
 *  - 값이 없으면 추정하지 않는다. 생년월일이 없는 선수는 나이 기록에서 제외하고 제외 인원을 알려준다.
 *  - 모든 기록 행에 source(출처)를 그대로 달고 나간다.
 *  - 경기 시간은 90분 기준이다. 연장·추가시간은 반영하지 않는다.
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.Records = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  const LEAGUE_ORDER = ['K리그1', 'K리그2', 'K3리그', 'K4리그', 'WK리그'];
  const TOP_N = 5;

  // ---------- CSV ----------
  function parseCSV(text) {
    if (text.charCodeAt(0) === 0xfeff) text = text.slice(1);
    const rows = [];
    let row = [], field = '', inQ = false;
    for (let i = 0; i < text.length; i++) {
      const c = text[i];
      if (inQ) {
        if (c === '"') {
          if (text[i + 1] === '"') { field += '"'; i++; } else inQ = false;
        } else field += c;
      } else if (c === '"') inQ = true;
      else if (c === ',') { row.push(field); field = ''; }
      else if (c === '\n' || c === '\r') {
        if (c === '\r' && text[i + 1] === '\n') i++;
        row.push(field); field = ''; rows.push(row); row = [];
      } else field += c;
    }
    if (field !== '' || row.length) { row.push(field); rows.push(row); }
    const head = (rows.shift() || []).map(h => h.trim());
    return rows
      .filter(r => r.some(x => x.trim() !== ''))
      .map(r => {
        const o = {};
        head.forEach((h, i) => { o[h] = (r[i] === undefined ? '' : r[i]).trim(); });
        return o;
      });
  }

  // ---------- 날짜 · 나이 ----------
  function toInt(v) {
    if (v === '' || v === null || v === undefined) return null;
    const n = Number(v);
    return Number.isInteger(n) ? n : null;
  }
  function parseYMD(s) {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s || '');
    if (!m) return null;
    const y = +m[1], mo = +m[2], d = +m[3];
    const dt = new Date(Date.UTC(y, mo - 1, d));
    if (dt.getUTCFullYear() !== y || dt.getUTCMonth() !== mo - 1 || dt.getUTCDate() !== d) return null;
    return { y, m: mo, d, t: dt.getTime() };
  }
  function isLeap(y) { return (y % 4 === 0 && y % 100 !== 0) || y % 400 === 0; }
  function ageAt(birth, on) {
    const b = parseYMD(birth), o = parseYMD(on);
    if (!b || !o || o.t < b.t) return null;
    let years = o.y - b.y;
    if (o.m < b.m || (o.m === b.m && o.d < b.d)) years--;
    const ly = b.y + years;
    let ld = b.d;
    if (b.m === 2 && b.d === 29 && !isLeap(ly)) ld = 28;
    const last = Date.UTC(ly, b.m - 1, ld);
    return {
      years,
      days: Math.round((o.t - last) / 864e5),
      total: Math.round((o.t - b.t) / 864e5),
    };
  }
  function ageText(a) { return '만 ' + a.years + '세 ' + a.days + '일'; }

  // ---------- 모델 ----------
  function buildModel(raw) {
    const issues = [];
    const addIssue = (level, code, message) => issues.push({ level, code, message });

    const players = new Map();
    raw.roster.forEach(p => {
      if (players.has(p.player_id)) addIssue('error', 'dup_player', 'player_id 중복: ' + p.player_id);
      players.set(p.player_id, p);
    });

    const seenMatch = new Set();
    const matches = raw.matches.map(m => {
      if (seenMatch.has(m.match_id)) addIssue('error', 'dup_match', 'match_id 중복: ' + m.match_id);
      seenMatch.add(m.match_id);
      const out = Object.assign({}, m, {
        season: toInt(m.season),
        home_score: toInt(m.home_score),
        away_score: toInt(m.away_score),
        attendance: toInt(m.attendance),
      });
      if (out.home_score === null || out.away_score === null)
        addIssue('warn', 'no_score', m.match_id + ': 점수가 비어 있어 결과 기록에서 제외돼요');
      if (!parseYMD(m.date)) addIssue('error', 'bad_date', m.match_id + ': 날짜 형식이 YYYY-MM-DD가 아니에요 (' + m.date + ')');
      return out;
    });
    const matchById = new Map(matches.map(m => [m.match_id, m]));

    const eventsByMatch = new Map();
    raw.events.forEach(e => {
      const ev = Object.assign({}, e, { minute: toInt(e.minute), extra: toInt(e.extra_minute) || 0 });
      if (ev.extra && ev.minute !== 45 && ev.minute !== 90)
        addIssue('warn', 'bad_extra', e.event_id + ': extra_minute(추가시간)는 minute가 45 또는 90일 때만 써요');
      if (!matchById.has(e.match_id)) { addIssue('error', 'orphan_event', e.event_id + ': 없는 match_id (' + e.match_id + ')'); return; }
      if (!players.has(e.player_id)) addIssue('error', 'unknown_player', e.event_id + ': roster에 없는 player_id (' + e.player_id + ')');
      if (ev.minute === null) addIssue('warn', 'no_minute', e.event_id + ': minute가 비어 있어요');
      if (!eventsByMatch.has(e.match_id)) eventsByMatch.set(e.match_id, []);
      eventsByMatch.get(e.match_id).push(ev);
    });

    // 경기 길이: matches.csv의 first_half_extra / second_half_extra 가 있으면 그 값,
    // 없으면 이벤트에 기록된 추가시간 중 가장 긴 값(= 최소치)을 쓴다
    matches.forEach(m => {
      const evs = eventsByMatch.get(m.match_id) || [];
      const obs = at => evs.reduce((n, e) => (e.minute === at && e.extra > n ? e.extra : n), 0);
      const fh = toInt(m.first_half_extra), sh = toInt(m.second_half_extra);
      m.fhx = fh !== null ? fh : obs(45);
      m.shx = sh !== null ? sh : obs(90);
      m.length = 90 + m.fhx + m.shx;
      m.extraKnown = fh !== null && sh !== null;
      if (evs.length && !m.extraKnown)
        addIssue('info', 'extra_estimated', m.match_id + ': 추가시간을 matches.csv에 적지 않아, 이벤트에 적힌 값(전반 +' + m.fhx + ' · 후반 +' + m.shx +
          ')으로 출전 시간을 계산했어요. 실제 경기 시간보다 짧을 수 있어요');
    });

    // 점수 vs 득점 이벤트 대조
    matches.forEach(m => {
      if (m.home_score === null || m.away_score === null) return;
      const evs = eventsByMatch.get(m.match_id) || [];
      if (!evs.length) { addIssue('info', 'no_events', m.match_id + ': 이벤트가 아직 없어요 (득점자·출장 기록 미입력)'); return; }
      const cnt = t => evs.filter(e => (e.type === 'GOAL' || e.type === 'OWN_GOAL') && e.team === t).length;
      if (cnt(m.home_team) !== m.home_score || cnt(m.away_team) !== m.away_score)
        addIssue('error', 'score_mismatch',
          m.match_id + ': 점수 ' + m.home_score + '-' + m.away_score + ' 인데 득점 이벤트는 ' +
          cnt(m.home_team) + '-' + cnt(m.away_team));
    });

    // 생년월일
    const scorers = new Set();
    eventsByMatch.forEach(list => list.forEach(e => { if (e.type === 'GOAL') scorers.add(e.player_id); }));
    scorers.forEach(pid => {
      const p = players.get(pid);
      if (p && !p.birth_date) addIssue('warn', 'no_birth_scorer', p.name + '(' + pid + '): 득점자인데 생년월일이 비어 있어요');
    });
    players.forEach(p => {
      if (p.birth_date && !parseYMD(p.birth_date)) addIssue('error', 'bad_birth', p.name + ': 생년월일 형식 오류 (' + p.birth_date + ')');
    });
    eventsByMatch.forEach((list, mid) => {
      const m = matchById.get(mid);
      list.forEach(e => {
        const p = players.get(e.player_id);
        if (p && p.birth_date && parseYMD(p.birth_date) && parseYMD(m.date) && ageAt(p.birth_date, m.date) === null)
          addIssue('error', 'birth_after_match', p.name + ': 생년월일이 경기일(' + m.date + ')보다 늦어요');
      });
    });

    // 출처 누락
    const missing = {
      matches: raw.matches.filter(r => !r.source).length,
      roster: raw.roster.filter(r => !r.source).length,
      events: raw.events.filter(r => !r.source).length,
    };
    ['matches', 'roster', 'events'].forEach(k => {
      if (missing[k]) addIssue('warn', 'no_source', k + '.csv: 출처(source)가 비어 있는 행 ' + missing[k] + '개');
    });

    // 메타
    const leagues = Array.from(new Set(matches.map(m => m.league))).filter(Boolean);
    leagues.sort((a, b) => {
      const ia = LEAGUE_ORDER.indexOf(a), ib = LEAGUE_ORDER.indexOf(b);
      return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib) || a.localeCompare(b, 'ko');
    });
    const seasons = Array.from(new Set(matches.map(m => m.season))).filter(s => s !== null).sort((a, b) => b - a);
    const teamsByLeague = {};
    matches.forEach(m => {
      (teamsByLeague[m.league] = teamsByLeague[m.league] || new Set()).add(m.home_team).add(m.away_team);
    });
    Object.keys(teamsByLeague).forEach(k => { teamsByLeague[k] = Array.from(teamsByLeague[k]).sort((a, b) => a.localeCompare(b, 'ko')); });

    return {
      players, matches, matchById, eventsByMatch, issues, missing,
      meta: { leagues, seasons, teamsByLeague },
      counts: { matches: matches.length, players: players.size, events: raw.events.length },
    };
  }

  // ---------- 순위 매기기 ----------
  function ranked(items, keyFn, limit) {
    // items는 이미 정렬된 상태. keyFn 값이 같으면 같은 순위 (1,1,3 방식)
    const out = [];
    let prevKey, prevRank = 0;
    items.forEach((it, i) => {
      const k = keyFn(it);
      const rank = i > 0 && k === prevKey ? prevRank : i + 1;
      prevKey = k; prevRank = rank;
      out.push(Object.assign({ rank }, it));
    });
    // 공동 순위가 많아 목록이 길어지는 건 화면에서 접어서 보여준다
    return limit ? out.filter(r => r.rank <= limit) : out;
  }

  function longestStreak(rows, pred) {
    let best = null, cur = null;
    rows.forEach(r => {
      if (pred(r)) {
        if (!cur) cur = { len: 0, from: r, to: r };
        cur.len++; cur.to = r;
        if (!best || cur.len > best.len) best = { len: cur.len, from: cur.from, to: cur.to };
      } else cur = null;
    });
    return best;
  }

  // 경기 시작부터 흐른 시간(분). 전반 추가시간만큼 후반 이벤트가 뒤로 밀린다
  function clock(e, m) {
    if (e.minute === null) return null;
    const x = e.extra || 0;
    if (e.minute <= 45) return e.minute + (e.minute === 45 ? x : 0);
    return e.minute + (m.fhx || 0) + (e.minute === 90 ? x : 0);
  }

  // ---------- 조회 ----------
  function query(model, filter) {
    const f = Object.assign({ league: 'all', season: 'all', team: null }, filter || {});
    const P = pid => model.players.get(pid);
    const nameOf = pid => (P(pid) ? P(pid).name : pid);

    const ms = model.matches
      .filter(m =>
        (f.league === 'all' || m.league === f.league) &&
        (f.season === 'all' || m.season === f.season) &&
        (!f.team || m.home_team === f.team || m.away_team === f.team))
      .slice()
      .sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : a.match_id < b.match_id ? -1 : 1));

    const evsOf = m => (model.eventsByMatch.get(m.match_id) || []).filter(e => !f.team || e.team === f.team);

    // 출장
    const apps = [];
    ms.forEach(m => {
      const list = evsOf(m);
      const by = new Map();
      list.forEach(e => {
        if ((e.type === 'START' || e.type === 'SUB_IN') && !by.has(e.player_id))
          by.set(e.player_id, { pid: e.player_id, team: e.team, m, start: e.type === 'START', from: e.type === 'START' ? 0 : (clock(e, m) || 0), to: m.length, source: e.source });
      });
      list.forEach(e => {
        const a = by.get(e.player_id);
        const t = clock(e, m);
        if (a && (e.type === 'SUB_OUT' || e.type === 'RED') && t !== null && t >= a.from) a.to = Math.min(a.to, t);
      });
      by.forEach(a => { a.minutes = Math.max(0, a.to - a.from); apps.push(a); });
    });

    // 선수별 통산
    const stats = new Map();
    const S = (pid, team) => {
      if (!stats.has(pid)) stats.set(pid, { pid, team, apps: 0, starts: 0, minutes: 0, goals: 0, assists: 0, yellow: 0, red: 0, cleanSheets: 0 });
      const s = stats.get(pid); if (team) s.team = team; return s;
    };
    apps.forEach(a => {
      const s = S(a.pid, a.team);
      s.apps++; if (a.start) s.starts++; s.minutes += a.minutes;
      const p = P(a.pid), m = a.m;
      if (p && p.position === 'GK' && a.start && a.to >= m.length) {
        const conceded = a.team === m.home_team ? m.away_score : m.home_score;
        if (conceded === 0) s.cleanSheets++;
      }
    });
    const goalEvents = [];
    ms.forEach(m => evsOf(m).forEach(e => {
      if (e.type === 'GOAL') {
        S(e.player_id, e.team).goals++;
        goalEvents.push({ e, m });
        if (e.related_player_id) S(e.related_player_id, null).assists++;
      } else if (e.type === 'YELLOW') S(e.player_id, e.team).yellow++;
      else if (e.type === 'RED') S(e.player_id, e.team).red++;
    }));

    const row = (o) => o;
    const topList = (field, label) => {
      const items = Array.from(stats.values()).filter(s => s[field] > 0)
        .sort((a, b) => b[field] - a[field] || nameOf(a.pid).localeCompare(nameOf(b.pid), 'ko'));
      return ranked(items, s => s[field], TOP_N).map(s => row({
        rank: s.rank, name: nameOf(s.pid), team: s.team || '', pid: s.pid,
        value: s[field] + label,
        sub: field === 'apps' ? s.starts + '경기 선발 · ' + s.minutes + '분' : s.apps + '경기 출장 · ' + s.minutes + '분',
      }));
    };

    // 나이 기록
    const ageRows = (events, getPid, getDate, dir) => {
      const best = new Map(); let excluded = new Set();
      events.forEach(x => {
        const pid = getPid(x), p = P(pid);
        const a = p && p.birth_date ? ageAt(p.birth_date, getDate(x)) : null;
        if (!a) { excluded.add(pid); return; }
        const cur = best.get(pid);
        if (!cur || (dir === 'asc' ? a.total < cur.a.total : a.total > cur.a.total)) best.set(pid, { x, a, pid });
      });
      const items = Array.from(best.values()).sort((p, q) =>
        (dir === 'asc' ? p.a.total - q.a.total : q.a.total - p.a.total) || (getDate(p.x) < getDate(q.x) ? -1 : 1));
      return { items, excluded: excluded.size };
    };
    const matchLabel = m => m.date + ' · ' + m.home_team + ' ' + m.home_score + '-' + m.away_score + ' ' + m.away_team;
    const ageList = (events, getPid, getDate, getTeam, getMatch, getSource, dir) => {
      const { items, excluded } = ageRows(events, getPid, getDate, dir);
      return {
        excluded,
        rows: ranked(items, it => it.a.total, TOP_N).map(it => row({
          rank: it.rank, name: nameOf(it.pid), team: getTeam(it.x), pid: it.pid,
          value: ageText(it.a), sub: matchLabel(getMatch(it.x)), matchId: getMatch(it.x).match_id, source: getSource(it.x),
        })),
      };
    };

    const gA = ageList(goalEvents, x => x.e.player_id, x => x.m.date, x => x.e.team, x => x.m, x => x.e.source || x.m.source, 'asc');
    const gO = ageList(goalEvents, x => x.e.player_id, x => x.m.date, x => x.e.team, x => x.m, x => x.e.source || x.m.source, 'desc');
    const aA = ageList(apps, x => x.pid, x => x.m.date, x => x.team, x => x.m, x => x.source || x.m.source, 'asc');
    const aO = ageList(apps, x => x.pid, x => x.m.date, x => x.team, x => x.m, x => x.source || x.m.source, 'desc');

    // 단일 경기·시즌 득점 기록
    const perMatch = new Map(), perSeason = new Map();
    goalEvents.forEach(({ e, m }) => {
      const k1 = e.player_id + '|' + m.match_id;
      if (!perMatch.has(k1)) perMatch.set(k1, { pid: e.player_id, team: e.team, m, n: 0, source: e.source });
      perMatch.get(k1).n++;
      const k2 = e.player_id + '|' + m.season;
      if (!perSeason.has(k2)) perSeason.set(k2, { pid: e.player_id, team: e.team, season: m.season, league: m.league, n: 0 });
      perSeason.get(k2).n++;
    });
    const matchGoals = ranked(
      Array.from(perMatch.values()).filter(x => x.n >= 2).sort((a, b) => b.n - a.n || (a.m.date < b.m.date ? -1 : 1)),
      x => x.n, TOP_N).map(x => row({
        rank: x.rank, name: nameOf(x.pid), team: x.team, pid: x.pid,
        value: x.n + '골', sub: matchLabel(x.m), matchId: x.m.match_id, source: x.source || x.m.source,
      }));
    const seasonGoals = ranked(
      Array.from(perSeason.values()).sort((a, b) => b.n - a.n || nameOf(a.pid).localeCompare(nameOf(b.pid), 'ko')),
      x => x.n, TOP_N).map(x => row({
        rank: x.rank, name: nameOf(x.pid), team: x.team, pid: x.pid,
        value: x.n + '골', sub: x.season + ' 시즌 · ' + x.league,
      }));
    const fastest = ranked(
      goalEvents.filter(g => g.e.minute !== null && g.e.minute >= 1)
        .sort((a, b) => (a.e.minute * 100 + a.e.extra) - (b.e.minute * 100 + b.e.extra) || (a.m.date < b.m.date ? -1 : 1)),
      g => g.e.minute * 100 + g.e.extra, TOP_N).map(g => row({
        rank: g.rank, name: nameOf(g.e.player_id), team: g.e.team, pid: g.e.player_id,
        value: g.e.minute + (g.e.extra ? '+' + g.e.extra : '') + '분', sub: matchLabel(g.m), matchId: g.m.match_id, source: g.e.source || g.m.source,
      }));

    // 경기(팀) 기록
    const sides = [];
    ms.forEach(m => {
      if (m.home_score === null || m.away_score === null) return;
      [[m.home_team, m.away_team, m.home_score, m.away_score, '홈'], [m.away_team, m.home_team, m.away_score, m.home_score, '원정']]
        .forEach(([team, opp, gf, ga, venue]) => { if (!f.team || team === f.team) sides.push({ team, opp, gf, ga, venue, m }); });
    });
    const sideLine = s => ({
      name: s.team, team: '', value: s.gf + '-' + s.ga,
      sub: s.m.date + ' · ' + s.opp + ' (' + s.venue + ')', matchId: s.m.match_id, source: s.m.source,
    });
    const bigWins = ranked(
      sides.filter(s => s.gf > s.ga).sort((a, b) => (b.gf - b.ga) - (a.gf - a.ga) || b.gf - a.gf || (a.m.date < b.m.date ? -1 : 1)),
      s => (s.gf - s.ga) + ':' + s.gf, TOP_N).map(s => Object.assign({ rank: s.rank }, sideLine(s)));
    const bigLosses = ranked(
      sides.filter(s => s.gf < s.ga).sort((a, b) => (a.gf - a.ga) - (b.gf - b.ga) || b.ga - a.ga || (a.m.date < b.m.date ? -1 : 1)),
      s => (s.gf - s.ga) + ':' + s.ga, TOP_N).map(s => Object.assign({ rank: s.rank }, sideLine(s)));
    const scored = ms.filter(m => m.home_score !== null && m.away_score !== null);
    const highest = ranked(
      scored.slice().sort((a, b) => (b.home_score + b.away_score) - (a.home_score + a.away_score) || (a.date < b.date ? -1 : 1)),
      m => m.home_score + m.away_score, TOP_N).map(m => ({
        rank: m.rank, name: m.home_team + ' ' + m.home_score + '-' + m.away_score + ' ' + m.away_team, team: '',
        value: (m.home_score + m.away_score) + '골', sub: m.date + ' · ' + m.league, matchId: m.match_id, source: m.source,
      }));
    const att = ranked(
      ms.filter(m => m.attendance !== null).sort((a, b) => b.attendance - a.attendance || (a.date < b.date ? -1 : 1)),
      m => m.attendance, TOP_N).map(m => ({
        rank: m.rank, name: m.home_team + ' vs ' + m.away_team, team: '',
        value: m.attendance.toLocaleString('ko-KR') + '명', sub: m.date + ' · ' + (m.venue || '경기장 —'), matchId: m.match_id, source: m.source,
      }));

    const byTeam = new Map();
    sides.forEach(s => { if (!byTeam.has(s.team)) byTeam.set(s.team, []); byTeam.get(s.team).push(s); });
    const streakList = pred => {
      const items = [];
      byTeam.forEach((rows, team) => {
        const b = longestStreak(rows, pred);
        if (b) items.push({ team, len: b.len, from: b.from.m.date, to: b.to.m.date });
      });
      items.sort((a, b) => b.len - a.len || a.team.localeCompare(b.team, 'ko'));
      return ranked(items, i => i.len, TOP_N).map(i => ({
        rank: i.rank, name: i.team, team: '', value: i.len + '경기', sub: i.from + ' ~ ' + i.to,
      }));
    };

    const lists = [
      { id: 'apps', group: 'player', title: '통산 출장', rows: topList('apps', '경기'), empty: '출장 기록이 아직 없어요 (events.csv에 START / SUB_IN 입력)' },
      { id: 'goals', group: 'player', title: '통산 득점', rows: topList('goals', '골'), empty: '득점 기록이 아직 없어요 (events.csv에 GOAL 입력)' },
      { id: 'assists', group: 'player', title: '통산 도움', rows: topList('assists', '개'), empty: '도움 기록이 없어요 (GOAL 행의 related_player_id에 입력)' },
      { id: 'minutes', group: 'player', title: '통산 출전 시간', rows: topList('minutes', '분'), empty: '출전 시간 기록이 없어요' },
      { id: 'yellow', group: 'player', title: '통산 경고', rows: topList('yellow', '회'), empty: '경고 기록이 없어요 (events.csv에 YELLOW 입력)' },
      { id: 'red', group: 'player', title: '통산 퇴장', rows: topList('red', '회'), empty: '퇴장 기록이 없어요 (events.csv에 RED 입력)' },
      { id: 'cs', group: 'player', title: '통산 무실점 경기 (GK)', rows: topList('cleanSheets', '경기'), empty: '무실점 경기 기록이 없어요' },

      { id: 'young_goal', group: 'unusual', title: '최연소 득점', rows: gA.rows, excluded: gA.excluded, empty: '생년월일이 입력된 득점자가 없어요' },
      { id: 'old_goal', group: 'unusual', title: '최고령 득점', rows: gO.rows, excluded: gO.excluded, empty: '생년월일이 입력된 득점자가 없어요' },
      { id: 'young_app', group: 'unusual', title: '최연소 출장', rows: aA.rows, excluded: aA.excluded, empty: '생년월일이 입력된 출장 선수가 없어요' },
      { id: 'old_app', group: 'unusual', title: '최고령 출장', rows: aO.rows, excluded: aO.excluded, empty: '생년월일이 입력된 출장 선수가 없어요' },
      { id: 'fast', group: 'unusual', title: '가장 빠른 득점', rows: fastest, empty: '득점 시간이 입력된 기록이 없어요' },
      { id: 'match_goals', group: 'unusual', title: '한 경기 최다 득점 (선수)', rows: matchGoals, empty: '한 경기 2골 이상 기록한 선수가 아직 없어요' },
      { id: 'season_goals', group: 'unusual', title: '한 시즌 최다 득점 (선수)', rows: seasonGoals, empty: '득점 기록이 아직 없어요' },

      { id: 'big_win', group: 'match', title: '최다 점수차 승리', rows: bigWins, empty: '승리 경기가 아직 없어요' },
      { id: 'big_loss', group: 'match', title: '최다 점수차 패배', rows: bigLosses, empty: '패배 경기가 아직 없어요' },
      { id: 'high', group: 'match', title: '한 경기 최다 득점 (양 팀 합계)', rows: highest, empty: '점수가 입력된 경기가 없어요' },
      { id: 'att', group: 'match', title: '최다 관중', rows: att, empty: '관중 수가 입력된 경기가 없어요' },
      { id: 's_win', group: 'match', title: '최다 연승', rows: streakList(r => r.gf > r.ga), empty: '경기 결과가 없어요' },
      { id: 's_unb', group: 'match', title: '최다 연속 무패', rows: streakList(r => r.gf >= r.ga), empty: '경기 결과가 없어요' },
      { id: 's_los', group: 'match', title: '최다 연패', rows: streakList(r => r.gf < r.ga), empty: '패배 경기가 없어요' },
      { id: 's_cs', group: 'match', title: '최다 연속 무실점', rows: streakList(r => r.ga === 0), empty: '무실점 경기가 없어요' },
    ];

    const teamSet = new Set();
    ms.forEach(m => { teamSet.add(m.home_team); teamSet.add(m.away_team); });
    return {
      filter: f,
      summary: {
        matches: ms.length,
        goals: scored.reduce((n, m) => n + m.home_score + m.away_score, 0),
        teams: f.team ? 1 : teamSet.size,
        players: stats.size,
        withEvents: ms.filter(m => (model.eventsByMatch.get(m.match_id) || []).length > 0).length,
      },
      lists,
      table: Array.from(stats.values()).map(s => Object.assign({ name: nameOf(s.pid) }, s))
        .filter(s => s.apps || s.goals || s.assists || s.yellow || s.red),
    };
  }

  return { parseCSV, buildModel, query, ageAt, ageText, parseYMD, LEAGUE_ORDER };
});
