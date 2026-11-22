"""
가상 샘플 데이터 생성기.

주의: 여기서 만드는 팀·선수·경기는 전부 가짜입니다. 실제 기록이 아닙니다.
사이트의 계산 로직과 화면을 확인하기 위한 용도이고, 실제 데이터는 data/ 폴더의
CSV 3종(matches.csv, roster.csv, events.csv)에 직접 입력하세요.

일부러 넣어둔 엣지 케이스:
  - 만 16세 득점자 / 만 38세 득점자
  - 생년월일이 비어 있는 득점자 (나이 기록에서 제외되어야 함)
  - 자책골, 퇴장, 교체 출전
  - 6-0 대승 경기, 관중 수가 비어 있는 경기
"""
import csv
import random
from datetime import date, timedelta
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "data" / "sample"
OUT.mkdir(parents=True, exist_ok=True)
rnd = random.Random(20261104)

SRC = "샘플(가상 데이터)"

TEAMS = {
    "K3리그": ["샘플FC 알파", "샘플FC 베타", "샘플FC 감마", "샘플FC 델타"],
    "K4리그": ["샘플FC 엡실론", "샘플FC 제타"],
}
POS_PLAN = ["GK", "GK", "DF", "DF", "DF", "DF", "DF", "MF", "MF", "MF", "MF", "FW", "FW", "FW"]

roster = []  # dict rows
by_team = {}
pid = 0
for league, teams in TEAMS.items():
    for ti, team in enumerate(teams):
        by_team[team] = []
        for k, pos in enumerate(POS_PLAN):
            pid += 1
            birth = date(1989, 1, 1) + timedelta(days=rnd.randint(0, 365 * 18))
            row = {
                "player_id": f"P{pid:03d}",
                "name": f"가상선수 {team[-2:]}{k + 1:02d}",
                "birth_date": birth.isoformat(),
                "position": pos,
                "team": team,
                "shirt_no": k + 1,
                "source": SRC,
            }
            roster.append(row)
            by_team[team].append(row)

# 엣지 케이스 선수 지정
def find(team, idx):
    return by_team[team][idx]

young = find("샘플FC 알파", 13)          # FW
young["birth_date"] = "2009-08-20"
young["name"] = "가상선수 알파-최연소"
old = find("샘플FC 베타", 12)            # FW
old["birth_date"] = "1987-02-03"
old["name"] = "가상선수 베타-최고령"
unknown = find("샘플FC 감마", 13)        # FW
unknown["birth_date"] = ""
unknown["name"] = "가상선수 감마-생일미상"

pidx = {p["player_id"]: p for p in roster}


def age_days(birth: str, on: date):
    if not birth:
        return None
    y, m, d = map(int, birth.split("-"))
    return (on - date(y, m, d)).days


matches, events = [], []
mid = 0
eid = 0


def add_event(match_id, minute, typ, player, team, related=""):
    global eid
    eid += 1
    events.append({
        "event_id": f"E{eid:05d}",
        "match_id": match_id,
        "minute": minute,
        "type": typ,
        "player_id": player["player_id"],
        "team": team,
        "related_player_id": related,
        "source": SRC,
    })


def play(league, season, rnd_no, d, home, away, force=None, no_attendance=False, own_goal=False, red=False):
    global mid
    mid += 1
    match_id = f"M{mid:04d}"
    gh = rnd.choice([0, 0, 1, 1, 1, 2, 2, 3, 4])
    ga = rnd.choice([0, 0, 1, 1, 1, 2, 2, 3])
    if force:
        gh, ga = force

    # 선발 + 교체
    pitch = {}
    for team in (home, away):
        squad = by_team[team]
        gks = [p for p in squad if p["position"] == "GK"]
        field = [p for p in squad if p["position"] != "GK"]
        starters = [rnd.choice(gks)] + rnd.sample(field, 10)
        bench = [p for p in field if p not in starters]
        for s in starters:
            add_event(match_id, 0, "START", s, team)
        sub_in = rnd.choice(bench)
        sub_out = rnd.choice([s for s in starters if s["position"] != "GK"])
        m_sub = rnd.randint(55, 80)
        add_event(match_id, m_sub, "SUB_OUT", sub_out, team, sub_in["player_id"])
        add_event(match_id, m_sub, "SUB_IN", sub_in, team, sub_out["player_id"])
        # (선수, 시작분, 종료분)
        windows = []
        for s in starters:
            windows.append((s, 0, m_sub if s is sub_out else 90))
        windows.append((sub_in, m_sub, 90))
        pitch[team] = windows

    def scorer_for(team):
        wins = pitch[team]
        weights = [{"FW": 6, "MF": 3, "DF": 1, "GK": 0}[w[0]["position"]] for w in wins]
        w = rnd.choices(wins, weights=weights)[0]
        minute = rnd.randint(max(1, w[1] + (1 if w[1] else 0)), w[2] if w[2] < 90 else 90)
        return w[0], minute, wins

    # 엣지 케이스 선수를 득점 가능 위치로 강제 투입
    for team, p in (("샘플FC 알파", young), ("샘플FC 베타", old), ("샘플FC 감마", unknown)):
        pass

    goals = {home: gh, away: ga}
    og_done = False
    for team, n in goals.items():
        other = away if team == home else home
        for _ in range(n):
            if own_goal and not og_done:
                og_done = True
                victim = [w for w in pitch[other] if w[0]["position"] == "DF"]
                w = victim[0] if victim else pitch[other][1]
                add_event(match_id, rnd.randint(5, 85), "OWN_GOAL", w[0], team)
                continue
            p, minute, wins = scorer_for(team)
            mates = [w[0] for w in wins if w[0] is not p]
            assist = rnd.choice(mates)["player_id"] if rnd.random() < 0.6 else ""
            add_event(match_id, minute, "GOAL", p, team, assist)
    if red:
        w = rnd.choice(pitch[home][1:])
        add_event(match_id, rnd.randint(30, 85), "RED", w[0], home)
    for team in (home, away):
        if rnd.random() < 0.5:
            w = rnd.choice(pitch[team])
            add_event(match_id, rnd.randint(10, 88), "YELLOW", w[0], team)

    matches.append({
        "match_id": match_id,
        "season": season,
        "league": league,
        "round": rnd_no,
        "date": d.isoformat(),
        "venue": f"{home} 홈구장(가상)",
        "home_team": home,
        "away_team": away,
        "home_score": gh,
        "away_score": ga,
        "attendance": "" if no_attendance else rnd.randint(300, 2600),
        "source": SRC,
    })


def round_robin(teams):
    # 2회전 (홈/원정)
    out = []
    for a in teams:
        for b in teams:
            if a != b:
                out.append((a, b))
    rnd.shuffle(out)
    return out


for season, start in ((2025, date(2025, 3, 8)), (2026, date(2026, 3, 7))):
    for league, teams in TEAMS.items():
        fixtures = round_robin(teams)
        for i, (h, a) in enumerate(fixtures):
            d = start + timedelta(days=7 * (i // max(1, len(teams) // 2)))
            play(league, season, i // max(1, len(teams) // 2) + 1, d, h, a,
                 force=(6, 0) if (season == 2026 and league == "K3리그" and i == 3) else None,
                 no_attendance=(season == 2025 and league == "K3리그" and i == 1),
                 own_goal=(season == 2026 and league == "K3리그" and i == 5),
                 red=(i == 2))

# 엣지 케이스 선수가 실제 득점 기록을 갖도록 마지막 경기 몇 개를 직접 추가
def force_scorer(match_date, season, league, home, away, scorer, score, minute=33):
    global mid
    mid += 1
    match_id = f"M{mid:04d}"
    team = scorer["team"]
    squad = by_team[home] + by_team[away]
    for t in (home, away):
        gk = [p for p in by_team[t] if p["position"] == "GK"][0]
        starters = [gk] + [p for p in by_team[t] if p["position"] != "GK" and p is not None][:10]
        if scorer["team"] == t and scorer not in starters:
            starters[-1] = scorer
        for s in starters:
            add_event(match_id, 0, "START", s, t)
    add_event(match_id, minute, "GOAL", scorer, team, "")
    matches.append({
        "match_id": match_id, "season": season, "league": league, "round": 99,
        "date": match_date.isoformat(), "venue": f"{home} 홈구장(가상)",
        "home_team": home, "away_team": away,
        "home_score": score[0], "away_score": score[1],
        "attendance": 1200, "source": SRC,
    })
    # 점수와 이벤트 일치: 상대 득점은 추가하지 않으므로 0점 처리
    if team == home and score[1] != 0 or team == away and score[0] != 0:
        raise SystemExit("force_scorer: 상대 점수는 0으로 둘 것")


force_scorer(date(2026, 9, 12), 2026, "K3리그", "샘플FC 알파", "샘플FC 델타", young, (1, 0))
force_scorer(date(2026, 9, 19), 2026, "K3리그", "샘플FC 감마", "샘플FC 베타", old, (0, 1))
force_scorer(date(2026, 9, 26), 2026, "K3리그", "샘플FC 감마", "샘플FC 알파", unknown, (1, 0))


def write(name, rows, fields):
    with open(OUT / name, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


write("matches.csv", matches,
      ["match_id", "season", "league", "round", "date", "venue", "home_team", "away_team",
       "home_score", "away_score", "attendance", "source"])
write("roster.csv", roster,
      ["player_id", "name", "birth_date", "position", "team", "shirt_no", "source"])
write("events.csv", events,
      ["event_id", "match_id", "minute", "type", "player_id", "team", "related_player_id", "source"])

print(f"matches={len(matches)} roster={len(roster)} events={len(events)} -> {OUT}")
