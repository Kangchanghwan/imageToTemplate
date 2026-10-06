import json,sys
for n in ['sched_09','sched_10','sched_11','sched_12','form_activity','form_attendance','form_meal']:
    a=json.load(open('runs/r8b/%s/r8_%s.json'%(n,n))); b=json.load(open('runs/%s/%s/r8_%s.json'%(sys.argv[1],n,n)))
    ka={(c['r'],c['c']):c['size_pt'] for c in a['cells']}; kb={(c['r'],c['c']):c['size_pt'] for c in b['cells']}
    d=[(k,ka[k],kb.get(k)) for k in ka if ka[k]!=kb.get(k)]
    print(n,'size diffs',len(d),d[:5])
