import s,re,html,sys,os
def abstract(url):
    h=s.fetch(url)
    m=re.search(r'<blockquote class="abstract mathjax">(.*?)</blockquote>',h,re.S)
    t=re.search(r'<h1 class="title mathjax">(.*?)</h1>',h,re.S)
    d=re.search(r'<div class="dateline">(.*?)</div>',h,re.S)
    cm=re.search(r'<td class="tablecell comments[^"]*">(.*?)</td>',h,re.S)
    jr=re.search(r'<td class="tablecell jref">(.*?)</td>',h,re.S)
    return (s.clean(t.group(1)) if t else '?',
            s.clean(d.group(1)) if d else '',
            s.clean(cm.group(1)) if cm else '',
            s.clean(jr.group(1)) if jr else '',
            s.clean(m.group(1)) if m else 'NOABS')
ids=[l.split('#')[0].strip() for l in open(sys.argv[1]) if l.strip() and not l.startswith('#')]
for i in ids:
    url='https://arxiv.org/abs/'+i
    try:
        t,d,cm,jr,a=abstract(url)
    except Exception as e:
        print('=== ERR '+i+' '+str(e)); continue
    print('=== '+t.replace('Title:','').strip())
    print('URL: '+url)
    print('DATE: '+d.replace('Submitted on','').strip()+' | COMMENT: '+cm+' | JREF: '+jr)
    print('ABS: '+' '.join(a.replace('Abstract:','').split()))
    print()
