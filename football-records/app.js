(function () {
  'use strict';
  const R = window.Records;
  const app = document.getElementById('app');
  const LEAGUES = R.LEAGUE_ORDER;
  const LEAGUE_COLOR = { 'K리그1': '#E4572E', 'K리그2': '#4C956C', 'K3리그': '#4D80E4', 'K4리그': '#B98CCB', 'WK리그': '#E0B354' };
  const TAB_GROUPS = [['unusual', '특이 기록'], ['player', '선수 통산'], ['match', '경기 기록']];
  const SHOW_ROWS = 8;
  let model = null;
  let mode = 'real';

  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  // ---------- 데이터 불러오기 ----------
  async function fetchCSV(path) {
    const r = await fetch(path, { cache: 'no-cache' });
    if (!r.ok) throw new Error(path + ' → ' + r.status);
    return R.parseCSV(await r.text());
  }
  async function loadSet(base) {
    const [matches, roster, events] = await Promise.all(['matches', 'roster', 'events'].map(n => fetchCSV(base + n + '.csv')));
    return { matches, roster, events };
  }
  async function init() {
    const force = new URLSearchParams(location.search).get('data');
    try {
      let raw = null;
      if (force !== 'sample') { raw = await loadSet('data/'); mode = 'real'; }
      if (force === 'sample' || (force !== 'real' && raw.matches.length === 0)) { raw = await loadSet('data/sample/'); mode = 'sample'; }
      model = R.buildModel(raw);
    } catch (err) {
      app.innerHTML = '<div class="fatal"><b>데이터 파일을 읽지 못했어요.</b><br>' +
        'index.html을 더블클릭해서 열면 브라우저가 파일 읽기를 막아요. 이 폴더에서 <code>python3 -m http.server 8000</code> 을 실행하고 ' +
        '<code>http://localhost:8000</code> 으로 열어주세요.<br><small>' + esc(err.message) + '</small></div>';
      return;
    }
    window.addEventListener('hashchange', route);
    route();
  }

  // ---------- 라우팅 ----------
  function parseHash() {
    const h = location.hash.replace(/^#/, '') || '/';
    const [path, qs] = h.split('?');
    return { path, params: new URLSearchParams(qs || '') };
  }
  function href(base, params) {
    const u = new URLSearchParams();
    Object.keys(params || {}).forEach(k => { if (params[k] && params[k] !== 'all') u.set(k, params[k]); });
    const s = u.toString();
    return '#' + base + (s ? '?' + s : '');
  }
  function route() {
    const { path, params } = parseHash();
    let nav = 'home', html;
    if (path === '/records') { nav = 'records'; html = viewRecords(params); }
    else if (path === '/teams') { nav = 'teams'; html = viewTeams(); }
    else if (path.indexOf('/team/') === 0) { nav = 'teams'; html = viewTeam(decodeURIComponent(path.slice(6)), params); }
    else if (path === '/data') { nav = 'data'; html = viewData(); }
    else html = viewHome(params);
    app.innerHTML = (mode === 'sample' ? sampleBanner() : '') + html;
    document.querySelectorAll('#tabs a').forEach(a => {
      if (a.dataset.nav === nav) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
    });
    window.scrollTo(0, 0);
  }
  app.addEventListener('change', e => {
    const sel = e.target.closest('select[data-param]');
    if (!sel) return;
    const { path, params } = parseHash();
    const next = {};
    params.forEach((v, k) => { next[k] = v; });
    next[sel.dataset.param] = sel.value;
    location.hash = href(path, next);
  });

  // ---------- 조각 ----------
  function sampleBanner() {
    return '<div class="banner"><b>가상의 샘플 데이터예요.</b> 실제 팀·선수·기록이 아니에요. ' +
      '<a href="#/data">내 데이터 넣는 방법</a></div>';
  }
  function leagueChips(base, current, extra) {
    const present = model.meta.leagues;
    const chip = (label, value, color) => {
      const on = (current || 'all') === value;
      const off = value !== 'all' && present.indexOf(value) < 0;
      return '<a class="chip' + (off ? ' off' : '') + '" style="--c:' + color + '" ' +
        (on ? 'aria-current="true" ' : '') + (off ? 'aria-disabled="true" tabindex="-1" ' : '') +
        'href="' + href(base, Object.assign({}, extra, { league: value })) + '"><i></i>' + esc(label) + (off ? ' · 준비 중' : '') + '</a>';
    };
    // 데이터가 있는 리그를 앞에, 준비 중인 리그를 뒤에 둔다
    const known = LEAGUES.slice().sort((a, b) => (present.indexOf(a) < 0) - (present.indexOf(b) < 0));
    let s = chip('전체', 'all', 'var(--chalk)');
    known.forEach(l => { s += chip(l, l, LEAGUE_COLOR[l]); });
    present.filter(l => LEAGUES.indexOf(l) < 0).forEach(l => { s += chip(l, l, 'var(--muted)'); });
    return '<div class="chips">' + s + '</div>';
  }
  function seasonSelect(current) {
    const opts = ['<option value="all">전체 시즌</option>']
      .concat(model.meta.seasons.map(s => '<option value="' + s + '"' + (String(s) === String(current) ? ' selected' : '') + '>' + s + ' 시즌</option>'));
    return '<div class="filters"><label class="sel">시즌 <select data-param="season">' + opts.join('') + '</select></label></div>';
  }
  function srcHTML(s) {
    if (!s) return '<span class="src">출처 —</span>';
    if (/^https?:\/\//i.test(s)) return '<span class="src">출처 <a href="' + esc(s) + '" target="_blank" rel="noopener noreferrer">링크</a></span>';
    return '<span class="src">출처 ' + esc(s) + '</span>';
  }
  function listHTML(l, hideTeam) {
    let h = '<section class="rec"><h3>' + esc(l.title) + '</h3>';
    if (!l.rows.length) {
      h += '<p class="empty">' + esc(l.empty) + '</p>';
    } else {
      const shown = l.rows.slice(0, SHOW_ROWS);
      h += '<ol>' + shown.map(r =>
        '<li' + (r.rank === 1 ? ' class="first"' : '') + '><span class="rk">' + r.rank + '</span>' +
        '<div class="who2"><b>' + esc(r.name) + '</b>' +
        (r.team && !hideTeam ? '<span class="team">' + esc(r.team) + '</span>' : '') +
        (r.sub ? '<span class="sub">' + esc(r.sub) + '</span>' : '') +
        (r.source !== undefined ? srcHTML(r.source) : '') + '</div>' +
        '<div class="val">' + esc(r.value) + '</div></li>').join('') + '</ol>';
      if (l.rows.length > shown.length) h += '<p class="more">공동 순위 ' + (l.rows.length - shown.length) + '건 더 있어요</p>';
    }
    if (l.excluded) h += '<p class="note">생년월일이 없는 ' + l.excluded + '명은 이 기록에서 제외했어요</p>';
    return h + '</section>';
  }
  function tabs(base, params, current) {
    return '<nav class="seg" aria-label="기록 종류">' + TAB_GROUPS.map(([k, label]) =>
      '<a href="' + href(base, Object.assign({}, params, { tab: k })) + '"' + (k === current ? ' aria-current="true"' : '') + '>' + label + '</a>').join('') + '</nav>';
  }
  function currentTab(p) {
    const t = p.get('tab');
    return TAB_GROUPS.some(g => g[0] === t) ? t : 'unusual';
  }
  function seasonOf(p) {
    const s = p.get('season');
    return s && s !== 'all' ? Number(s) : 'all';
  }
  function wdl(team, season) {
    let w = 0, d = 0, l = 0, gf = 0, ga = 0, n = 0;
    model.matches.forEach(m => {
      if ((m.home_team !== team && m.away_team !== team) || (season !== 'all' && m.season !== season)) return;
      if (m.home_score === null || m.away_score === null) return;
      const mine = m.home_team === team ? m.home_score : m.away_score;
      const their = m.home_team === team ? m.away_score : m.home_score;
      n++; gf += mine; ga += their;
      if (mine > their) w++; else if (mine === their) d++; else l++;
    });
    return { w, d, l, gf, ga, n };
  }

  // ---------- 화면 ----------
  function plate(label, list) {
    const r = list.rows[0];
    if (!r) {
      return '<div class="plate blank"><p class="what">' + esc(label) + '</p><div class="age"><span class="big">—</span></div>' +
        '<p class="none">' + esc(model.counts.matches === 0 ? 'data/ 폴더의 CSV에 경기·선수·이벤트를 넣으면 여기에 나와요' : list.empty) + '</p></div>';
    }
    const m = /만 (\d+)세 (\d+)일/.exec(r.value);
    return '<div class="plate"><p class="what">' + esc(label) + '</p>' +
      '<div class="age"><span class="big">' + (m ? m[1] : esc(r.value)) + '</span><span class="unit">' + (m ? '세 ' + m[2] + '일' : '') + '</span></div>' +
      '<p class="who">' + esc(r.name) + '</p>' +
      '<p class="meta">' + esc(r.team) + ' · ' + esc(r.sub) + '</p>' +
      (r.source !== undefined ? '<p class="meta">' + srcHTML(r.source) + '</p>' : '') + '</div>';
  }
  function viewHome(p) {
    const league = p.get('league') || 'all';
    const q = R.query(model, { league });
    const L = id => q.lists.find(l => l.id === id);
    const s = q.summary;
    return '<h1>K3·K4부터 프로리그까지,<br>구단의 기록을 한곳에</h1>' +
      '<p class="lead">최연소·최고령 득점 같은 특이 기록까지 경기 단위 데이터로 계산해요.</p>' +
      leagueChips('/', league) +
      '<div class="plates">' + plate('최연소 득점', L('young_goal')) + plate('최고령 득점', L('old_goal')) + '</div>' +
      '<ul class="glance">' +
      [['경기', s.matches], ['골', s.goals], ['구단', s.teams], ['선수', s.players]].map(x =>
        '<li><span class="n">' + x[1].toLocaleString('ko-KR') + '</span><span class="l">' + x[0] + '</span></li>').join('') + '</ul>' +
      '<div class="links">' +
      '<a class="link" href="' + href('/records', { league }) + '"><span>리그 기록 전체 보기<small>통산·특이·경기 기록</small></span><span>›</span></a>' +
      '<a class="link" href="#/teams"><span>구단별 기록실<small>구단을 골라 그 팀의 기록만 보기</small></span><span>›</span></a></div>';
  }
  function viewRecords(p) {
    const league = p.get('league') || 'all';
    const season = seasonOf(p);
    const tab = currentTab(p);
    const q = R.query(model, { league, season });
    const base = { league, season: season === 'all' ? '' : String(season) };
    return '<h1>리그 기록</h1>' +
      '<p class="lead">' + q.summary.matches + '경기 · ' + q.summary.goals + '골 기준</p>' +
      leagueChips('/records', league, { season: base.season, tab }) +
      seasonSelect(season) + tabs('/records', base, tab) +
      q.lists.filter(l => l.group === tab).map(listHTML).join('');
  }
  function viewTeams() {
    let h = '<h1>구단</h1><p class="lead">구단을 누르면 그 팀의 기록실이 열려요.</p>';
    if (!model.meta.leagues.length) return h + '<p class="empty">경기 데이터가 아직 없어요</p>';
    model.meta.leagues.forEach(lg => {
      h += '<div class="league-h" style="--c:' + (LEAGUE_COLOR[lg] || 'var(--muted)') + '"><i></i>' + esc(lg) + '</div>';
      model.meta.teamsByLeague[lg].forEach(t => {
        const r = wdl(t, 'all');
        h += '<a class="teamrow" href="#/team/' + encodeURIComponent(t) + '"><span><b>' + esc(t) + '</b><small>' +
          r.n + '경기 · 득점 ' + r.gf + ' 실점 ' + r.ga + '</small></span><span class="wdl">' + r.w + '승 ' + r.d + '무 ' + r.l + '패</span></a>';
      });
    });
    return h;
  }
  function viewTeam(team, p) {
    const known = model.matches.some(m => m.home_team === team || m.away_team === team);
    if (!known) return '<a class="crumb" href="#/teams">← 구단 목록</a><h1>찾을 수 없는 구단이에요</h1><p class="lead">구단 이름이 데이터에 없어요.</p>';
    const season = seasonOf(p);
    const tab = currentTab(p);
    const q = R.query(model, { team, season });
    const lg = (model.matches.find(m => m.home_team === team || m.away_team === team) || {}).league;
    const r = wdl(team, season);
    return '<a class="crumb" href="#/teams">← 구단 목록</a><h1>' + esc(team) + '</h1>' +
      '<p class="lead">' + esc(lg || '') + ' · ' + r.n + '경기 ' + r.w + '승 ' + r.d + '무 ' + r.l + '패 · 득점 ' + r.gf + ' 실점 ' + r.ga + '</p>' +
      seasonSelect(season) + tabs('/team/' + encodeURIComponent(team), { season: season === 'all' ? '' : String(season) }, tab) +
      q.lists.filter(l => l.group === tab).map(l => listHTML(l, true)).join('');
  }
  function viewData() {
    const c = model.counts, m = model.missing;
    const order = { error: 0, warn: 1, info: 2 };
    const issues = model.issues.slice().sort((a, b) => order[a.level] - order[b.level]);
    const label = { error: '오류', warn: '확인', info: '참고' };
    let h = '<h1>데이터 현황</h1><p class="lead">' + (mode === 'sample'
      ? '지금은 data/ 폴더가 비어 있어서 샘플 데이터를 보여주고 있어요.'
      : '이 사이트는 data/ 폴더의 CSV 3개만으로 모든 기록을 계산해요.') + '</p>';
    h += '<table class="table"><tbody>' +
      [['경기', c.matches], ['선수', c.players], ['이벤트(득점·출장·카드)', c.events],
        ['출처가 비어 있는 행', m.matches + m.roster + m.events]]
        .map(x => '<tr><td>' + x[0] + '</td><td>' + x[1].toLocaleString('ko-KR') + '</td></tr>').join('') + '</tbody></table>';
    h += '<div class="h2">점검 결과</div>';
    h += issues.length
      ? issues.map(i => '<div class="issue"><span class="tag ' + i.level + '">' + label[i.level] + '</span><span>' + esc(i.message) + '</span></div>').join('')
      : '<p class="empty">문제가 발견되지 않았어요</p>';
    h += '<div class="h2">데이터 넣는 방법</div><ul class="guide">' +
      '<li><code>matches.csv</code> 경기 하나당 한 줄. 날짜는 <code>YYYY-MM-DD</code>.</li>' +
      '<li><code>roster.csv</code> 선수 한 명당 한 줄. 생년월일을 모르면 비워두세요. 추정해서 넣지 않아요.</li>' +
      '<li><code>events.csv</code> 선발(START)·교체(SUB_IN/SUB_OUT)·득점(GOAL)·자책(OWN_GOAL)·경고(YELLOW)·퇴장(RED). 도움은 GOAL 행의 <code>related_player_id</code>에 넣어요.</li>' +
      '<li>모든 행의 <code>source</code>에 공식 출처(주소)를 적어요. 비어 있으면 위 점검 결과에 표시돼요.</li>' +
      '<li>경기 시간은 90분 기준이에요. 연장·추가시간은 반영하지 않아요.</li></ul>' +
      '<div class="dl"><a href="data/matches.csv" download>matches.csv 빈 양식</a><a href="data/roster.csv" download>roster.csv 빈 양식</a><a href="data/events.csv" download>events.csv 빈 양식</a></div>';
    return h;
  }

  init();
})();
