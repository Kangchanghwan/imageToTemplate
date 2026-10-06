import json
for run in ('r8b','r8c'):
    s=json.load(open('runs/%s/sched_10/r8_sched_10.json'%run))
    print(run,[(c['r'],c['c'],c['size_pt'],c['text'][:8]) for c in s['cells'] if c.get('role')=='table' and c['r'] in (1,2,3)])
