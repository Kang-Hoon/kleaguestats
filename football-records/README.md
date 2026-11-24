# 축구 기록실 (가칭)

K3·K4리그부터 프로리그까지, 구단별 기록과 최연소·최고령 득점 같은 특이 기록을 보여주는 모바일 웹 사이트입니다.
서버나 DB 없이 `data/`의 CSV 3개만 읽어서 브라우저에서 모든 기록을 계산합니다.

## 지금 보는 방법

```
cd football-records
python3 -m http.server 8000
```

브라우저에서 `http://localhost:8000` 을 엽니다. (index.html을 더블클릭하면 브라우저가 CSV 읽기를 막아요.)

`data/`가 비어 있으면 `data/sample/`의 **가상 샘플**을 대신 보여주고, 화면 위에 샘플이라는 안내가 계속 떠 있습니다.
`?data=real` 을 주소 끝에 붙이면 샘플로 넘어가지 않고 빈 상태를 그대로 봅니다.

## 데이터 넣기

`data/matches.csv`, `data/roster.csv`, `data/events.csv` 에 헤더 아래로 행을 추가합니다.

| 파일 | 한 줄의 뜻 | 핵심 칸 |
|---|---|---|
| matches.csv | 경기 1개 | match_id, season, league, date(YYYY-MM-DD), home_team, away_team, home_score, away_score, attendance, source |
| roster.csv | 선수 1명 | player_id, name, birth_date, position(GK/DF/MF/FW), team, source |
| events.csv | 경기 중 사건 1개 | match_id, minute, extra_minute(선택), type, player_id, team, related_player_id, source |

events의 `type`: `START`(선발) `SUB_IN` `SUB_OUT` `GOAL` `OWN_GOAL`(team은 점수를 얻은 쪽) `YELLOW` `RED`.
도움은 GOAL 행의 `related_player_id`, 교체 상대는 SUB_IN/SUB_OUT 행의 `related_player_id`에 넣습니다.

원칙
- 모르는 값은 비워둡니다. 추정해서 넣지 않습니다. 생년월일이 비면 그 선수는 나이 기록에서 빠지고 화면에 제외 인원이 표시됩니다.
- 모든 행의 `source`에 공식 출처 주소를 적습니다. 비어 있으면 데이터 탭의 점검 결과에 뜹니다.
- 경기 시간은 90분 기준입니다. 연장·추가시간은 반영하지 않습니다.
- 데이터 탭에서 점수와 득점 이벤트 불일치, 없는 선수 참조, 날짜 형식 오류를 자동으로 점검합니다.

## 배포

빌드 과정이 없는 정적 사이트입니다. 이 폴더 전체를 그대로 올리면 됩니다.
Cloudflare Pages나 Railway 정적 서비스에서 GitHub 저장소를 연결하고 빌드 명령 없이 루트 폴더를 게시하세요.
`tools/` 폴더는 게시하지 않아도 됩니다.

## 폴더

- `index.html`, `app.js`, `style.css` 화면
- `records.js` CSV 파싱, 데이터 점검, 모든 기록 계산 (브라우저와 Node 양쪽에서 동작)
- `data/` 실제 데이터 (헤더만 있는 빈 양식), `data/sample/` 가상 샘플
- `tools/make_sample.py` 샘플 생성, `tools/verify.py` JS 계산을 파이썬으로 따로 계산해 대조 (`python3 tools/verify.py`)


추가시간: 90+5분 골은 `minute`=90, `extra_minute`=5 로 입력합니다 (전반 추가시간은 45 + extra_minute). 컬럼을 비우거나 아예 없어도 됩니다.

출전 시간은 교체·퇴장 시각과 추가시간으로 계산합니다. 실제 추가시간은 `matches.csv`의 `first_half_extra`(전반), `second_half_extra`(후반)에 분 단위로 적으세요.
비워 두면 events에 적힌 추가시간 중 가장 긴 값으로 대신 계산합니다(실제보다 짧을 수 있음 → 데이터 현황에 '참고'로 표시).

'선수' 탭에서 경기·선발·출전 시간·골·도움·경고·퇴장·무실점을 한 표로 보고, 머리글을 눌러 정렬합니다. 리그·시즌·구단으로 거를 수 있습니다.

events.csv의 선택 컬럼 `note`: 페널티킥 골은 `PK`로 적습니다(현재는 기록만 하고 순위 계산에는 쓰지 않음).

## ID 규칙

- **팀 코드(`teams.csv`)**: 영문 대문자 3자리. 리그 전체에서 겹치지 않게 한 번 정하면 팀 이름이 바뀌어도 바꾸지 않습니다. 새 팀은 `teams.csv`에 먼저 등록합니다.
- **경기 ID**: `K3-2026-0315-JBN-DKR` = 리그-시즌-월일-홈팀코드-원정팀코드
- **선수 Sub ID(`player_id`)**: `DKR-26-07` = 팀코드-시즌 두 자리-등번호. 같은 팀·시즌에 등번호가 겹치면 `b`, `c`…를 붙입니다. 시즌·팀·번호가 바뀌면 새 Sub ID가 생깁니다.
- 선수 고유 ID(예: `P2026-00001`)는 아직 부여하지 않았습니다. 통산 기록이 필요해질 때 `roster.csv`에 열을 추가해 부여할 예정입니다.
- 옛 ID(2자리 코드) → 새 ID 대응표는 `data/id_map.csv`에 있습니다. (`tools/migrate_ids.py`가 한 번 실행한 결과)
- 데이터 검사: `python3 tools/check_data.py` (실데이터 무결성). `tools/verify.py`는 샘플 데이터 계산 대조용입니다.
