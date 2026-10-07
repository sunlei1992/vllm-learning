import sys, s, json, os
queries=json.load(open(sys.argv[1]))
out={}
for q in queries:
    try:
        r=s.search(q,25)
    except Exception as e:
        r=[]
        print('ERR',q,e)
    out[q]=r
    print(f'### QUERY: {q}  (n={len(r)})')
    for x in r:
        print('  * %s | %s | %s' % (x['title'], x['url'], x['date']))
        if x['comment']: print('      C: '+x['comment'][:160])
        print('      A: '+x['abstract'][:700])
    print()
json.dump(out,open(sys.argv[2],'w'),ensure_ascii=False)
