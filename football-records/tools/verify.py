"""JS 계산 결과를 파이썬으로 따로 계산한 값과 대조한다 (샘플 데이터 기준)."""
import csv, json, subprocess, sys
from collections import defaultdict
from datetime import date
from dateutil.relativedelta import relativedelta
D="data/sample/"
rd=lambda n:list(csv.DictReader(open(D+n+".csv",encoding="utf-8")))
M,P,E=rd("matches"),{p["player_id"]:p for p in rd("roster")},rd("events")
Mi={m["match_id"]:m for m in M}
js=json.loads(subprocess.check_output(["node","tools/dump.js"]))
bad=0
def check(name,ok,detail=""):
    global bad
    print(("OK  " if ok else "FAIL"),name,detail)
    if not ok: bad+=1
def ymd(s): y,m,d=map(int,s.split("-")); return date(y,m,d)
def age(birth,on):
    rd_=relativedelta(ymd(on),ymd(birth)); last=ymd(birth)+relativedelta(years=rd_.years)
    return rd_.years,(ymd(on)-last).days,(ymd(on)-ymd(birth)).days
# 1. 최연소/최고령 득점 (선수별 대표 기록 후 1위)
best={}
for e in E:
    if e["type"]!="GOAL": continue
    b=P[e["player_id"]]["birth_date"]
    if not b: continue
    a=age(b,Mi[e["match_id"]]["date"]); k=e["player_id"]
    best.setdefault(k,[]).append(a)
young=min((min(v,key=lambda x:x[2]),k) for k,v in best.items())
old=max((max(v,key=lambda x:x[2]),k) for k,v in best.items())
txt=lambda a:f"만 {a[0]}세 {a[1]}일"
check("최연소 득점 1위", js["lists"]["young_goal"][0][2]==txt(young[0]) and js["lists"]["young_goal"][0][1]==P[young[1]]["name"], txt(young[0]))
check("최고령 득점 1위", js["lists"]["old_goal"][0][2]==txt(old[0]) and js["lists"]["old_goal"][0][1]==P[old[1]]["name"], txt(old[0]))
check("생일 미상 득점자가 나이 기록에 없음", all("생일미상" not in r[1] for r in js["lists"]["young_goal"]+js["lists"]["old_goal"]))
# 2. 통산 득점 / 출장 최댓값
goals=defaultdict(int); apps=defaultdict(int)
for e in E:
    if e["type"]=="GOAL": goals[e["player_id"]]+=1
    if e["type"] in("START","SUB_IN"): apps[e["player_id"]]+=1
mg=max(goals.values()); ma=max(apps.values())
check("통산 득점 1위 값/공동 인원", js["lists"]["goals"][0][2]==f"{mg}골" and len([r for r in js["lists"]["goals"] if r[0]==1])==sum(1 for v in goals.values() if v==mg), f"{mg}골")
check("통산 출장 1위 값/공동 인원", js["lists"]["apps"][0][2]==f"{ma}경기" and len([r for r in js["lists"]["apps"] if r[0]==1])==sum(1 for v in apps.values() if v==ma), f"{ma}경기")
# 3. 경기 기록
big=max(abs(int(m["home_score"])-int(m["away_score"])) for m in M)
g=list(map(int,js["lists"]["big_win"][0][2].split("-")))
check("최다 점수차", abs(g[0]-g[1])==big, f"{big}점차 / JS {js['lists']['big_win'][0][2]}")
tot=max(int(m["home_score"])+int(m["away_score"]) for m in M)
check("한 경기 최다 득점", js["lists"]["high"][0][2]==f"{tot}골", f"{tot}골")
att=[int(m["attendance"]) for m in M if m["attendance"]]
check("최다 관중", js["lists"]["att"][0][2]==f"{max(att):,}명", f"{max(att):,}명")
# 4. 연승·무패·연패·무실점 (팀별 시간순)
def streaks(pred):
    rows=defaultdict(list)
    for m in sorted(M,key=lambda m:(m["date"],m["match_id"])):
        h,a=int(m["home_score"]),int(m["away_score"])
        rows[m["home_team"]].append((h,a)); rows[m["away_team"]].append((a,h))
    best=0
    for t,r in rows.items():
        cur=0
        for gf,ga in r:
            cur=cur+1 if pred(gf,ga) else 0; best=max(best,cur)
    return best
for key,pred,name in (("s_win",lambda f,a:f>a,"최다 연승"),("s_unb",lambda f,a:f>=a,"최다 연속 무패"),("s_los",lambda f,a:f<a,"최다 연패"),("s_cs",lambda f,a:a==0,"최다 연속 무실점")):
    v=streaks(pred); check(name, js["lists"][key][0][2]==f"{v}경기", f"{v}경기")
# 5. 점수와 이벤트 일치 (JS의 경고가 없어야 함)
check("점수-득점이벤트 불일치 경고 없음", "score_mismatch" not in js["issues"])
print("\n실패",bad,"건"); sys.exit(1 if bad else 0)
