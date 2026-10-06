import json,sys
sys.path.insert(0,'.')
from sheetparser import score
gt=json.load(open('data/photos/gt_content.json'))
for n in ['sched_09','sched_10','sched_11','sched_12','form_activity','form_attendance','form_meal']:
    a=json.load(open('runs/full1/%s/r7_%s.json'%(n,n))); b=json.load(open('runs/r8b/%s/r8_%s.json'%(n,n)))
    sh=lambda s:(len(s['rows']),len(s['columns']),sum(1 for c in s['cells'] if c.get('role')=='table' and (c['rs']>1 or c['cs']>1)))
    print(n,sh(a),sh(b),'block_ok r7',score.content_score(a,gt,n).get('block_ok'),'r8',score.content_score(b,gt,n).get('block_ok'), a['columns']==b['columns'] and a['rows']==b['rows'])
