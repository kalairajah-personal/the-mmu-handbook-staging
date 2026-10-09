#!/usr/bin/env python3
"""link_refs.py — reference ids + DOI/URL links + in-text citation links (PIPELINE §7.3–§7.5).

Usage: python3 scripts/link_refs.py [--check] [--no-cites] [chapters/ | file.html ...]
  --check     dry run; exit 1 if any file would change
  --no-cites  only reference ids/links (rollout batch R1)
Idempotent: a second run changes nothing.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import reflib as R

REPO = Path(__file__).resolve().parent.parent
LEDGER = REPO / 'assets' / 'ref-links.json'

DOI_RE = re.compile(r'(?i)(?:\bdoi:\s*|https?://(?:dx\.)?doi\.org/)(10\.\d{4,9}/[^\s<>"]+?)(?=[.,;)]?(?:\s|$))')
URL_RE = re.compile(r'https?://[^\s<>"]+?(?=[.,;)]?(?:\s|$))')
A_RE = re.compile(r'<a\b([^>]*)>', re.S)
LEDGER_LINK_RE = re.compile(r' <a class="ref-link[^"]*" href="[^"]*">[^<]*</a>(</p>\s*)?$')


def load_ledger(path=LEDGER):
    try:
        d = json.loads(Path(path).read_text())
    except FileNotFoundError:
        d = {}
    return d.get('entries', {}), d.get('aliases', {})


def load_missing(path=LEDGER):
    """Citations (as 'chNN:<exact text>') to works absent from References — fixed in item 2, warned not failed."""
    try:
        return json.loads(Path(path).read_text()).get('missing', [])
    except FileNotFoundError:
        return []


def _link_text(seg):
    """Wrap DOI/URL text (outside existing tags) in a.ref-link."""
    parts = re.split(r'(<a\b.*?</a>|<[^>]+>)', seg, flags=re.S)
    for i in range(0, len(parts), 2):
        p = parts[i]
        p = DOI_RE.sub(lambda m: f'<a class="ref-link" href="https://doi.org/{m.group(1)}">{m.group(0)}</a>', p)
        sub = re.split(r'(<a\b.*?</a>)', p, flags=re.S)
        for j in range(0, len(sub), 2):
            sub[j] = URL_RE.sub(lambda m: f'<a class="ref-link" href="{m.group(0)}">{m.group(0)}</a>', sub[j])
        parts[i] = ''.join(sub)
    return ''.join(parts)


def _ledger_link(e, title):
    if e.get('status') == 'verified' and e.get('doi'):
        return f'<a class="ref-link" href="https://doi.org/{e["doi"]}">doi:{e["doi"]}</a>'
    if e.get('status') == 'verified' and e.get('url'):
        return f'<a class="ref-link" href="{e["url"]}">{e["url"]}</a>'
    if e.get('status') == 'search':
        q = re.sub(r'\s+', '+', re.sub(r'[^\w\s-]', ' ', title).strip())
        return f'<a class="ref-link ref-link--search" href="https://scholar.google.com/scholar?q={q}">[search]</a>'
    return None


def _title(t):
    m = re.search(r'[“"]([^”"]{8,200})[”"]', t)
    return m.group(1) if m else t[:120]


def link_refs(page, ch, entries, stats):
    refs = R.parse_refs(page)
    for r in reversed(refs):
        inner = r['inner']
        e = entries.get(f'ch{ch}:{r["key"]}')
        if e:
            # ledger keys only exist for refs with no DOI/URL in their text, so any trailing
            # ref-link is one this script appended earlier: drop it and re-derive from the ledger
            inner = LEDGER_LINK_RE.sub(r'\1', inner)
        if 'ref-link' not in inner:
            # existing <a href> (e.g. Ch01) -> tag it; else wrap DOI/URL text; else ledger
            if re.search(r'<a\b[^>]*href=', inner):
                inner = A_RE.sub(lambda m: m.group(0) if 'class=' in m.group(1) else f'<a class="ref-link"{m.group(1)}>', inner)
                stats['tagged'] += 1
            else:
                new = _link_text(inner)
                if new != inner:
                    inner = new
                    stats['wrapped'] += 1
                else:
                    e = entries.get(f'ch{ch}:{r["key"]}')
                    a = _ledger_link(e, _title(r['text'])) if e else None
                    if a:
                        inner = re.sub(r'(</p>\s*)?$', lambda m: ' ' + a + (m.group(1) or ''), inner.rstrip(), count=1)
                        stats['ledger'] += 1
                    else:
                        stats['unlinked'].append(r['key'])
        page = page[:r['start']] + f'<li id="ref-{r["key"]}">{inner}</li>' + page[r['end']:]
    stats['refs'] += len(refs)
    return page


def _cite_a(key, label):
    return f'<a class="cite" href="#ref-{key}">{label}</a>'


def link_cites(page, ch, aliases, stats):
    refs = R.parse_refs(page)
    resolve = R.resolver(refs, aliases, ch)
    s, e = R.body_span(page)
    pieces = R.text_pieces(page[s:e])

    def group(m, open_ch):
        its = R.items(m.group(1))
        if not its:
            return m.group(0)
        keys = [resolve(*it) for it in its]
        if not all(keys):
            stats['unresolved'].append(m.group(0).replace('\n', ' '))
            return m.group(0)
        stats['cites'] += len(keys)
        return '[' + '; '.join(_cite_a(k, f'{a}, {y}{sf}') for k, (a, y, sf) in zip(keys, its)) + ']'

    def narr(m):
        k = resolve(m.group(1), m.group(2), m.group(3))
        if not k:
            stats['unresolved'].append(m.group(0).replace('\n', ' '))
            return m.group(0)
        stats['cites'] += 1
        return f'{m.group(1)} [{_cite_a(k, m.group(2) + m.group(3))}]'

    for i in range(0, len(pieces), 2):
        p = R.BRACKET.sub(lambda m: group(m, '['), pieces[i])
        p = R.PAREN.sub(lambda m: group(m, '('), p)
        p = R.NARR.sub(narr, p)
        pieces[i] = p
    new_body = ''.join(pieces)
    norm = lambda x: re.sub(r'[\[\]()\s]', '', R.text(x))
    if norm(new_body) != norm(page[s:e]):
        raise ValueError('citation transform changed prose text (token-diff check)')
    return page[:s] + new_body + page[e:]


def process(page, ch, entries, aliases, cites=True, stats=None):
    stats = stats if stats is not None else new_stats()
    page = link_refs(page, ch, entries, stats)
    if cites:
        page = link_cites(page, ch, aliases, stats)
    return page


def new_stats():
    return {'refs': 0, 'tagged': 0, 'wrapped': 0, 'ledger': 0, 'unlinked': [], 'cites': 0, 'unresolved': []}


def files(args):
    out = []
    for a in args or [str(REPO / 'chapters')]:
        p = Path(a)
        out += sorted(p.glob('chapter-*-WITH-FIGURES.html')) if p.is_dir() else [p]
    return out


def main(argv):
    check = '--check' in argv
    cites = '--no-cites' not in argv
    entries, aliases = load_ledger()
    changed = 0
    for f in files([a for a in argv if not a.startswith('--')]):
        page = f.read_text()
        st = new_stats()
        new = process(page, R.chapter_num(f), entries, aliases, cites, st)
        if new != page:
            changed += 1
            if not check:
                f.write_text(new)
        print(f"{f.name}: refs {st['refs']} tagged {st['tagged']} wrapped {st['wrapped']} ledger {st['ledger']} "
              f"unlinked {len(st['unlinked'])} cites {st['cites']} unresolved {len(st['unresolved'])}"
              + (' CHANGED' if new != page else ''))
        for u in st['unresolved']:
            print('   unresolved:', u[:100])
    return 1 if (check and changed) else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
