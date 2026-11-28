import sys, os, urllib.request
os.makedirs('out', exist_ok=True)
for spec in sys.argv[1:]:
    y, gid = spec.split(':')
    h = urllib.request.urlopen(urllib.request.Request(f'https://www.kleague.com/match.do?year={y}&meetSeq=1&gameId={gid}&leagueId=1&startTabNum=1', headers={'User-Agent': 'Mozilla/5.0'}), timeout=60).read().decode('utf-8', 'replace')
    open(f'out/{y}_{gid}.html', 'w', encoding='utf-8').write(h); print(spec, len(h))
