import re,html,json,urllib.request,urllib.parse,time,sys
def strip(x): return html.unescape(re.sub(r'<[^>]+>','',x)).strip()
def search(q,size=50,start=0,sort="-announced_date_first"):
    url="https://arxiv.org/search/?"+urllib.parse.urlencode({
      "searchtype":"all","query":q,"start":start,"size":size,"order":sort})
    req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
    t=urllib.request.urlopen(req,timeout=60).read().decode('utf-8','ignore')
    out=[]
    for m in re.finditer(r'<li class="arxiv-result">(.*?)</li>',t,re.S):
        b=m.group(1)
        aid=re.search(r'arxiv.org/abs/([0-9v.]+)',b)
        title=re.search(r'<p class="title is-5 mathjax">(.*?)</p>',b,re.S)
        auth=re.search(r'<p class="authors">(.*?)</p>',b,re.S)
        abst=re.search(r'<span class="abstract-full[^"]*"[^>]*>(.*?)</span>',b,re.S)
        dates=re.search(r'<p class="is-size-7">(.*?)</p>',b,re.S)
        comm=re.search(r'<p class="comments is-size-7">(.*?)</p>',b,re.S)
        jour=re.search(r'<p class="journal-ref is-size-7">(.*?)</p>',b,re.S)
        out.append({"id":aid.group(1) if aid else "","title":strip(title.group(1)) if title else "",
          "authors":strip(auth.group(1))[:200] if auth else "",
          "abs":strip(abst.group(1))[:700] if abst else "",
          "dates":strip(dates.group(1)) if dates else "",
          "comment":strip(comm.group(1)) if comm else "",
          "journal":strip(jour.group(1)) if jour else ""})
    return out
qs=json.load(open(sys.argv[1]))
res={}
for q in qs:
    try:
        res[q]=search(q)
        print("OK",q,len(res[q])); sys.stdout.flush()
    except Exception as e:
        print("ERR",q,e); sys.stdout.flush()
    time.sleep(2)
json.dump(res,open(sys.argv[2],'w'),ensure_ascii=False,indent=1)
