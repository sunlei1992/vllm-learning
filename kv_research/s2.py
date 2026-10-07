import s,sys
for q in sys.argv[1:]:
    print('##### '+q)
    for r in s.search(q):
        print(' * %s | %s | %s | %s' % (r['title'],r['url'],r['date'],r['comment'][:80]))
    print()
