#!/usr/bin/env python3
"""build_footer.py — one consistent chapter footer (prev · Contents · next) after References.

Usage: python3 scripts/build_footer.py [--check] [chapters/ | file.html ...]
  --check  dry run; exit 1 if any file would change

Source of truth for titles/order: the page's own `var CHAPTERS = [...]` (same data as the sidebar).
Ad-hoc footers after the reference list are normalised:
  - "Next Chapter: ..." lines are removed (replaced by the generated footer);
  - any other trailing prose paragraph is moved to the end of the body, just before References.
Idempotent: a second run changes nothing.
"""
import html as H
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import reflib as R

REPO = Path(__file__).resolve().parent.parent
NAV_RE = re.compile(r'\n?<nav class="chapter-nav"[^>]*>.*?</nav>\n?', re.S)
TRAIL_RE = re.compile(r'\s*<hr\s*/?>\s*(<p>.*?</p>)', re.S)


def chapters(page):
    m = re.search(r'var CHAPTERS = (\[.*?\]);', page, re.S)
    if not m:
        raise ValueError('no CHAPTERS array')
    return json.loads(m.group(1))


def footer_html(chs, num):
    i = next(k for k, c in enumerate(chs) if int(c['num']) == num)
    esc = lambda s: H.escape(s, quote=False)
    parts = []
    if i > 0:
        p = chs[i - 1]
        parts.append(f'<a class="chapter-nav-prev" href="{p["file"]}" rel="prev">&larr; Chapter {int(p["num"])}: {esc(p["short"])}</a>')
    parts.append('<a class="chapter-nav-home" href="../index.html">Contents</a>')
    if i + 1 < len(chs):
        n = chs[i + 1]
        parts.append(f'<a class="chapter-nav-next" href="{n["file"]}" rel="next">Chapter {int(n["num"])}: {esc(n["short"])} &rarr;</a>')
    return '<nav class="chapter-nav" aria-label="Chapter navigation">\n' + '\n'.join(parts) + '\n</nav>\n'


def process(page, num):
    page = NAV_RE.sub('\n', page, count=1)
    span = R.refs_span(page)
    if not span:
        raise ValueError('no References section')
    s, e = span
    end = page.rfind('</ol>', s, e)
    if end < 0:
        raise ValueError('no reference list')
    end += len('</ol>')
    rest = page[end:e]
    moved = []
    while True:
        m = TRAIL_RE.match(rest)
        if not m:
            break
        if not re.match(r'<p>\s*<em>\s*Next Chapter', m.group(1)):
            moved.append(m.group(1))
        rest = rest[m.end():]
    page = page[:end] + '\n' + footer_html(chapters(page), num) + rest.lstrip('\n') + page[e:]
    if moved:
        h = page.find(R.REF_H2)
        page = page[:h] + '\n'.join(moved) + '\n' + page[h:]
    return page


def main(argv):
    check = '--check' in argv
    args = [a for a in argv if not a.startswith('--')] or [str(REPO / 'chapters')]
    changed = 0
    for a in args:
        p = Path(a)
        for f in (sorted(p.glob('chapter-*-WITH-FIGURES.html')) if p.is_dir() else [p]):
            page = f.read_text()
            new = process(page, int(R.chapter_num(f)))
            if new != page:
                changed += 1
                if not check:
                    f.write_text(new)
            print(f'{f.name}' + (' CHANGED' if new != page else ''))
    return 1 if (check and changed) else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
