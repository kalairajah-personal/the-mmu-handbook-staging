#!/usr/bin/env python3
"""apply_cites.py — insert reviewed in-text citations and split References / Further Reading (PIPELINE §7.13).

Plan: assets/cite-plan.json
  {"chapters": {"11": {"done": true,
                       "cites": [{"ref": "jouppi-2017" | ["a-2014", "b-2014"],
                                  "after": "<exact text ending the claim>", "why": "<what the source says>"}]}}}

For each cite, " [Label, Year]" is inserted directly after the first occurrence of `after` in the prose
(text outside tags, code, figures and headings). `after` must occur exactly once. The label is built from
the reference so link_refs.py resolves it. Re-running is a no-op.

For chapters marked "done", references that no citation points to are moved under
<h3 id="further-reading">Further Reading</h3> at the end of the References section.

Usage: python3 scripts/apply_cites.py [--check] [chapters/]
Run link_refs.py afterwards to turn the new brackets into links.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import reflib as R

REPO = Path(__file__).resolve().parent.parent
PLAN = REPO / 'assets' / 'cite-plan.json'
FR_H3 = '<h3 id="further-reading">Further Reading</h3>'


def load_plan(path=PLAN):
    try:
        return json.loads(Path(path).read_text()).get('chapters', {})
    except FileNotFoundError:
        return {}


def label(ref):
    """'[Label, Year]' text that link_refs' resolver maps back to this reference."""
    seg, _ = R.author_segment(ref['text'])
    seg = re.sub(r'\s+et al\.?$', '', seg).strip()
    year = ref['key'].rsplit('-', 1)[1]          # keeps a/b suffix
    if year == 'nd':
        raise ValueError(f'{ref["key"]}: reference has no year; cannot cite')
    return f'{seg}, {year}'


def insert_cites(page, cites):
    refs = {r['key']: r for r in R.parse_refs(page)}
    s, e = R.body_span(page)
    body = page[s:e]
    for c in cites:
        keys = c['ref'] if isinstance(c['ref'], list) else [c['ref']]
        for k in keys:
            if k not in refs:
                raise ValueError(f'unknown ref {k}')
        tag = ' [' + '; '.join(label(refs[k]) for k in keys) + ']'
        pieces = R.text_pieces(body)
        rx = re.compile(r'\s+'.join(re.escape(w) for w in c['after'].split()))
        hits = [(i, m.end()) for i in range(0, len(pieces), 2) for m in rx.finditer(pieces[i])]
        if len(hits) != 1:
            raise ValueError(f'{keys}: anchor found {len(hits)}×: {c["after"][:60]!r}')
        i, pos = hits[0]
        p = pieces[i]
        rest = p[pos:]
        if rest.startswith(tag) or rest.startswith(' [<') or rest.startswith(' ['):
            continue                                  # already cited here
        pieces[i] = p[:pos] + tag + rest
        body = ''.join(pieces)
    return page[:s] + body + page[e:]


def split_further(page):
    """Move references with no a.cite pointing at them into a Further Reading list (idempotent)."""
    cited = set(re.findall(r'<a class="cite" href="#ref-([^"]+)"', page))
    span = R.refs_span(page)
    s, e = span
    sec = page[s:e]
    # pull an existing Further Reading list back into consideration
    fr = re.search(re.escape(FR_H3) + r'\s*<ol[^>]*>(.*?)</ol>', sec, re.S)
    fr_items = re.findall(r'<li id="ref-[^"]+">.*?</li>', fr.group(1), re.S) if fr else []
    if fr:
        sec = sec[:fr.start()] + sec[fr.end():]
    keep_moving = []
    def pull(m):
        key = m.group(1)
        if key in cited:
            return m.group(0)
        keep_moving.append(m.group(0))
        return ''
    sec = re.sub(r'<li id="ref-([^"]+)">.*?</li>\n?', pull, sec, flags=re.S)
    # items already in Further Reading that are now cited go back to the main list end
    back = [x for x in fr_items if re.search(r'id="ref-([^"]+)"', x).group(1) in cited]
    stay = [x for x in fr_items if x not in back] + keep_moving
    if back:
        last = sec.rfind('</ol>')
        sec = sec[:last] + '\n'.join(back) + '\n' + sec[last:]
    sec = re.sub(r'<h3[^>]*>[^<]*</h3>\s*<ol[^>]*>\s*</ol>\s*', '', sec)   # drop emptied group lists
    sec = re.sub(r'<ol[^>]*>\s*</ol>\s*', '', sec)
    if stay:
        stay.sort(key=lambda x: R.text(x).lower())
        last = sec.rfind('</ol>') + len('</ol>')
        sec = sec[:last] + '\n' + FR_H3 + '\n<ol type="1">\n' + '\n'.join(stay) + '\n</ol>' + sec[last:]
    # renumber main lists continuously (grouped lists carry start="N")
    fr_at = sec.find(FR_H3)
    head, tail = (sec, '') if fr_at < 0 else (sec[:fr_at], sec[fr_at:])
    n = 0
    def renum(m):
        nonlocal n
        cnt = len(re.findall(r'<li\b', m.group(2)))
        attrs = re.sub(r'\s+start="\d+"', '', m.group(1))
        tag = f'<ol{attrs}>' if n == 0 else f'<ol{attrs} start="{n + 1}">'
        n += cnt
        return tag + m.group(2) + '</ol>'
    head = re.sub(r'<ol([^>]*)>(.*?)</ol>', renum, head, flags=re.S)
    sec = re.sub(r'(</ol>)\n{2,}', r'\1\n', head + tail)
    return page[:s] + sec + page[e:]


def process(page, ch, plan):
    cp = plan.get(str(int(ch)))
    if not cp:
        return page
    page = insert_cites(page, cp.get('cites', []))
    return page


def main(argv):
    import link_refs as L
    check = '--check' in argv
    args = [a for a in argv if not a.startswith('--')] or [str(REPO / 'chapters')]
    plan = load_plan()
    entries, aliases = L.load_ledger()
    changed = 0
    for a in args:
        p = Path(a)
        for f in (sorted(p.glob('chapter-*-WITH-FIGURES.html')) if p.is_dir() else [p]):
            ch = R.chapter_num(f)
            page = f.read_text()
            new = process(page, ch, plan)
            new = L.process(new, ch, entries, aliases)
            if plan.get(str(int(ch)), {}).get('done'):
                new = split_further(new)
            if new != page:
                changed += 1
                if not check:
                    f.write_text(new)
            print(f.name + (' CHANGED' if new != page else ''))
    return 1 if (check and changed) else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
