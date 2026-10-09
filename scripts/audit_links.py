#!/usr/bin/env python3
"""audit_links.py — G12 gate: citations, reference links, collapsible TOC (PIPELINE §7.7).

  G12a  every a.cite targets an existing li#ref-* on the page           ERROR
  G12b  bracketed [Name, YYYY] citation left unlinked                   ERROR (WARN if listed in ledger "missing")
  G12c  every reference <li> has a unique id="ref-…"                    ERROR
  G12d  reference has a.ref-link, or ledger status mismatch/none        WARN (ERROR with --strict)
  G12e  ledger entry/alias points at a reference that does not exist    ERROR
  G12f  TOC has one expand/collapse toggle and matches h2/h3 order             ERROR
  G12g  link_refs.py / build_toc.py would change the file (not idempotent / not applied)  ERROR
  G12h  build_footer.py would change the file (footer missing, stale, or ad-hoc footer)  ERROR

Usage: python3 scripts/audit_links.py [--strict] [chapters/]
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import reflib as R
import link_refs as L
import build_toc as T
import build_footer as F

REPO = Path(__file__).resolve().parent.parent


def audit(path, entries, aliases, strict=False, missing=()):
    page = path.read_text()
    ch = R.chapter_num(path)
    errs, warns = [], []
    ids = re.findall(r'<li id="(ref-[^"]+)"', page)
    refs = R.parse_refs(page)
    # G12c
    if len(ids) != len(refs) or len(set(ids)) != len(ids):
        errs.append(f'G12c {len(refs)} refs, {len(ids)} ids, {len(set(ids))} unique')
    # G12a
    bad = [h for h in re.findall(r'<a class="cite" href="#([^"]+)"', page) if h not in ids]
    if bad:
        errs.append(f'G12a cite targets missing: {bad[:3]}')
    # G12b
    s, e = R.body_span(page)
    left = []
    for i, p in enumerate(R.text_pieces(page[s:e])):
        if i % 2 == 0:
            left += [m.group(0) for m in R.BRACKET.finditer(p) if R.items(m.group(1))]
    known = [x for x in left if f'ch{ch}:' + x.replace('\n', ' ') in missing]
    left = [x for x in left if x not in known]
    if known:
        warns.append(f'G12b {len(known)} citation(s) to works missing from References (ledger "missing")')
    if left:
        errs.append(f'G12b unlinked citations ×{len(left)}: {left[:3]}')
    # G12d
    for r in refs:
        if 'ref-link' in r['inner']:
            continue
        st = entries.get(f'ch{ch}:{r["key"]}', {}).get('status')
        if st not in ('mismatch', 'none'):
            (errs if strict else warns).append(f'G12d ref-{r["key"]} has no link ({st or "not in ledger"})')
    # G12e
    keys = {r['key'] for r in refs}
    for k in entries:
        if k.startswith(f'ch{ch}:') and k.split(':', 1)[1] not in keys:
            errs.append(f'G12e ledger entry {k} matches no reference')
    for k, v in aliases.items():
        if k.startswith(f'ch{ch}:') and v.removeprefix('ref-') not in keys:
            errs.append(f'G12e alias {k} -> {v} matches no reference')
    # G12f / G12g
    if 'id="toc-expand"' not in page:
        errs.append('G12f TOC lacks the single expand/collapse toggle')
    try:
        if T.process(page) != page:
            errs.append('G12g build_toc.py would change this file')
        if F.process(page, int(ch)) != page:
            errs.append('G12h build_footer.py would change this file (chapter footer missing/stale)')
        if L.process(page, ch, entries, aliases) != page:
            errs.append('G12g link_refs.py would change this file')
    except ValueError as x:
        errs.append(f'G12g {x}')
    return errs, warns


def main(argv):
    strict = '--strict' in argv
    args = [a for a in argv if not a.startswith('--')]
    d = Path(args[0]) if args else REPO / 'chapters'
    entries, aliases = L.load_ledger()
    missing = set(L.load_missing())
    ne = nw = 0
    for f in sorted(d.glob('chapter-*-WITH-FIGURES.html')):
        errs, warns = audit(f, entries, aliases, strict, missing)
        ne += len(errs); nw += len(warns)
        if errs:
            print(f'{f.name}: {len(errs)} error(s)')
            for x in errs:
                print('  ERROR', x)
        if warns:
            print(f'{f.name}: {len(warns)} warning(s) (G12d)')
    print(f'G12: {ne} error(s), {nw} warning(s)')
    return 1 if ne else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
