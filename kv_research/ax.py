import sys,urllib.request,urllib.parse,re,html,time,json
def q(title):
    url="http://export.arxiv.org/api/query?"+urllib.parse.urlencode({"search_query":'ti:"%s"'%title,"max_results":2})
    try:
        t=urllib.request.urlopen(url,timeout=40).read().decode('utf-8','ignore')
    except Exception as e:
        return {"title":title,"error":str(e)}
    entries=re.findall(r'<entry>(.*?)</entry>',t,re.S)
    out=[]
    for e in entries:
        def g(tag):
            m=re.search(r'<%s>(.*?)</%s>'%(tag,tag),e,re.S)
            return html.unescape(re.sub(r'\s+',' ',m.group(1)).strip()) if m else ''
        out.append({"t":g('title'),"id":g('id'),"pub":g('published'),"upd":g('updated'),
                    "comment":g('arxiv:comment'),"journal":g('arxiv:journal_ref'),
                    "abs":g('summary')})
    return {"query":title,"hits":out}
titles=[l.strip() for l in open(sys.argv[1]) if l.strip()]
res=[q(x) for x in titles]
json.dump(res,open(sys.argv[2],'w'),ensure_ascii=False,indent=1)
for r in res:
    print("="*80)
    if 'error' in r: print("ERR",r); continue
    if not r['hits']: print("NO HIT:",r['query']); continue
    h=r['hits'][0]
    print("QUERY:",r['query'])
    print("TITLE:",h['t'])
    print("ID:",h['id'],"| pub",h['pub'][:10],"| comment:",h['comment'],"| journal:",h['journal'])
    print("ABS:",h['abs'][:900])
