#!/bin/bash
# usage: ./q.sh "query" [max]
Q=$(python3 -c "import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))" "$1")
MAX=${2:-8}
curl -sL --max-time 40 "http://export.arxiv.org/api/query?search_query=${Q}&start=0&max_results=${MAX}&sortBy=relevance" \
 | python3 -c "
import sys,xml.etree.ElementTree as ET
ns={'a':'http://www.w3.org/2005/Atom'}
r=ET.fromstring(sys.stdin.read())
for e in r.findall('a:entry',ns):
    t=' '.join(e.find('a:title',ns).text.split())
    i=e.find('a:id',ns).text
    d=e.find('a:published',ns).text[:10]
    u=e.find('a:updated',ns).text[:10]
    s=' '.join(e.find('a:summary',ns).text.split())
    c=e.find('a:comment',ns)
    j=e.find('a:journal_ref',ns)
    print('=== '+t)
    print('URL: '+i)
    print('PUB: '+d+'  UPD: '+u)
    if c is not None: print('COMMENT: '+' '.join(c.text.split()))
    if j is not None: print('JOURNAL: '+' '.join(j.text.split()))
    print('ABS: '+s)
    print()
"
