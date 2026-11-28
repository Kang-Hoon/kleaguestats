"""K리그 선수 상세 페이지 받기. 사용: python3 kleague_player.py IDS.txt OUTDIR 샘플수(0=전체)"""
import os, re, sys, json, time, urllib.request
ids = open(sys.argv[1]).read().split(); out = sys.argv[2]; os.makedirs(out, exist_ok=True)
sample = int(sys.argv[3]) if len(sys.argv) > 3 else 0
def get(u):
    for i in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'}), timeout=40) as r: return r.read().decode('utf-8', 'replace')
        except Exception as e: err = repr(e); time.sleep(2 * (i + 1))
    return 'ERR ' + err
if sample: ids = ids[:sample]
for n, pid in enumerate(ids):
    h = get(f'https://www.kleague.com/record/playerDetail.do?playerId={pid}')
    open(f'{out}/{pid}.html', 'w', encoding='utf-8').write(h)
    time.sleep(0.15)
print('done', len(ids))
