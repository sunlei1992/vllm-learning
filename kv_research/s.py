#!/usr/bin/env python3
import re,html,sys,urllib.parse,subprocess,time,os

CACHE='cache'
os.makedirs(CACHE,exist_ok=True)

def fetch(url):
    key=os.path.join(CACHE,re.sub(r'[^A-Za-z0-9]+','_',url)[:180])
    if os.path.exists(key):
        return open(key,encoding='utf-8').read()
    out=subprocess.run(['curl','-sL','--max-time','45','-A','Mozilla/5.0',url],capture_output=True,text=True).stdout
    open(key,'w',encoding='utf-8').write(out)
    time.sleep(5)
    return out

def clean(x):
    return html.unescape(re.sub('<[^>]+>','',x)).strip()

def search(q,size=25,start=0,abstracts=True):
    url=f"https://arxiv.org/search/?searchtype=all&query={urllib.parse.quote(q)}&start={start}&size={size}"
    if abstracts: url+="&abstracts=show"
    h=fetch(url)
    items=re.findall(r'<li class="arxiv-result">(.*?)</li>\s*(?=<li class="arxiv-result">|</ul>)',h,re.S)
    if not items:
        items=re.findall(r'<li class="arxiv-result">(.*?)(?=<li class="arxiv-result">|</ol>)',h,re.S)
    res=[]
    for it in items:
        t=re.search(r'<p class="title is-5 mathjax">(.*?)</p>',it,re.S)
        i=re.search(r'<a href="(https://arxiv.org/abs/[^"]+)"',it)
        d=re.search(r'Submitted</span>\s*([^;<]+)',it)
        a=re.search(r'<span class="abstract-full[^"]*"[^>]*>(.*?)</span>\s*(?:<a class|</p>)',it,re.S)
        if not a:
            a=re.search(r'<span class="abstract-full[^"]*"[^>]*>(.*)',it,re.S)
        au=re.findall(r'<a href="/search/\?searchtype=author[^"]*">([^<]+)</a>',it)
        cm=re.search(r'<span class="has-text-black-bis has-text-weight-semibold">Comments:</span>\s*<span class="has-text-grey-dark[^"]*">(.*?)</span>',it,re.S)
        jr=re.search(r'Journal ref:</span>\s*<span[^>]*>(.*?)</span>',it,re.S)
        res.append(dict(title=clean(t.group(1)) if t else '?',
                        url=i.group(1) if i else '?',
                        date=d.group(1).strip() if d else '',
                        authors=au[:6],
                        comment=clean(cm.group(1)) if cm else '',
                        jref=clean(jr.group(1)) if jr else '',
                        abstract=clean(a.group(1)) if a else ''))
    return res

if __name__=='__main__':
    q=sys.argv[1]; size=int(sys.argv[2]) if len(sys.argv)>2 else 50
    for r in search(q,size):
        print('=== '+r['title'])
        print('URL: '+r['url']+'   DATE: '+r['date'])
        if r['comment']: print('COMMENT: '+r['comment'])
        if r['jref']: print('JREF: '+r['jref'])
        print('ABS: '+r['abstract'][:900])
        print()
