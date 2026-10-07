import re,html,json,sys,urllib.request,time
def get(aid):
    url="https://arxiv.org/abs/"+aid
    req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
    t=urllib.request.urlopen(req,timeout=45).read().decode('utf-8','ignore')
    def m(p,f=re.S):
        x=re.search(p,t,f); return html.unescape(re.sub(r'<[^>]+>','',x.group(1))).strip() if x else ''
    title=m(r'<h1 class="title mathjax">(.*?)</h1>')
    abs_=m(r'<blockquote class="abstract mathjax">(.*?)</blockquote>')
    comm=m(r'<td class="tablecell comments[^"]*">(.*?)</td>')
    jour=m(r'<td class="tablecell journal-ref">(.*?)</td>')
    doi=m(r'<td class="tablecell doi">(.*?)</td>')
    subj=m(r'<td class="tablecell subjects">(.*?)</td>')
    dt=m(r'<div class="dateline">(.*?)</div>')
    return {"id":aid,"title":title.replace('Title:','').strip(),"abs":re.sub(r'\s+',' ',abs_.replace('Abstract:','').strip()),
            "comment":re.sub(r'\s+',' ',comm),"journal":re.sub(r'\s+',' ',jour),"doi":re.sub(r'\s+',' ',doi),
            "subjects":re.sub(r'\s+',' ',subj),"dateline":re.sub(r'\s+',' ',dt)}
ids=[l.strip() for l in open(sys.argv[1]) if l.strip()]
out=[]
for a in ids:
    try:
        out.append(get(a))
    except Exception as e:
        out.append({"id":a,"error":str(e)})
    time.sleep(1)
json.dump(out,open(sys.argv[2],'w'),ensure_ascii=False,indent=1)
for o in out:
    print("="*70); print(o.get('id'),"|",o.get('title','ERR'),"|",o.get('comment',''),"|",o.get('journal',''),"|",o.get('doi',''))
    print(o.get('abs','')[:1100])
