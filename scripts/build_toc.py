#!/usr/bin/env python3
"""build_toc.py — regenerate the in-page <nav id="TOC"> as a collapsible h2→h3 tree (PIPELINE §7.6).

Usage: python3 scripts/build_toc.py [--check] [chapters/ | file.html ...]
  --check  dry run; exit 1 if any file would change
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import reflib as R

REPO = Path(__file__).resolve().parent.parent


def process(page):
    if not R.TOC_RE.search(page):
        raise ValueError('no <nav id="TOC" role="doc-toc"> found')
    page = R.ensure_h3_ids(page)
    new = R.toc_html(R.headings(page))
    return R.TOC_RE.sub(lambda m: new, page, count=1)


def main(argv):
    check = '--check' in argv
    args = [a for a in argv if not a.startswith('--')] or [str(REPO / 'chapters')]
    changed = 0
    for a in args:
        p = Path(a)
        for f in (sorted(p.glob('chapter-*-WITH-FIGURES.html')) if p.is_dir() else [p]):
            page = f.read_text()
            new = process(page)
            if new != page:
                changed += 1
                if not check:
                    f.write_text(new)
            h = R.headings(page)
            print(f"{f.name}: h2 {sum(l == 2 for l, _, _ in h)} h3 {sum(l == 3 for l, _, _ in h)}"
                  + (' CHANGED' if new != page else ''))
    return 1 if (check and changed) else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
