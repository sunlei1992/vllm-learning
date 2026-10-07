import urllib.request,urllib.parse,re,html,json,time,sys
queries=[
 'all:"KV cache" AND all:"serving"',
 'all:"KV cache" AND all:"disaggregated"',
 'all:"prefix caching" AND all:"LLM serving"',
 'all:"KV cache" AND all:"offloading"',
 'all:"KV cache" AND all:"routing"',
 'all:"context caching" AND all:"LLM serving"',
 'all:"KV cache" AND all:"survey"',
 'all:"prefill-decode disaggregation"',
 'all:"KV cache" AND all:"CXL"',
 'all:"KV cache" AND all:"tiered storage"',
]
out=[]
for q in queries:
    for start in (0,100):
        url="http://export.arxiv.org/api/query?"+urllib.parse.urlencode({
            "search_query":q,"start":start,"max_results":100,
            "sortBy":"submittedDate","sortOrder":"descending"})
        try:
            t=urllib.request.urlopen(url,timeout=60).read().decode('utf-8','ignore')
        except Exception as e:
            print("ERR",q,start,e); continue
        for e in re.findall(r'<entry>(.*?)</entry>',t,re.S):
            def g(tag):
                m=re.search(r'<%s>(.*?)</%s>'%(tag,tag),e,re.S)
                return html.unescape(re.sub(r'\s+',' ',m.group(1)).strip()) if m else ''
            out.append({"q":q,"t":g('title'),"id":g('id'),"pub":g('published'),"comment":g('arxiv:comment'),"journal":g('arxiv:journal_ref'),"abs":g('summary')})
        print("done",q,start,len(out)); sys.stdout.flush()
        time.sleep(3)
json.dump(out,open('arxiv_search.json','w'),ensure_ascii=False,indent=1)
print("TOTAL",len(out))
