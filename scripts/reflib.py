"""reflib — shared parsing for references, citations and the in-page TOC (PIPELINE §7).

Used by link_refs.py, build_toc.py and audit_links.py. Pure functions on HTML strings.
"""
import html as H
import re
import unicodedata

YEAR = r'(?:1[89]\d\d|20\d\d)'
REF_H2 = '<h2 id="references"'
ORG_WORDS = {'corporation', 'corp', 'inc', 'ltd', 'limited', 'llc', 'gmbh', 'co'}


def fold(s):
    """ASCII-fold, lowercase, keep [a-z0-9]."""
    s = unicodedata.normalize('NFKD', H.unescape(s)).encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z0-9]', '', s.lower())


def text(s):
    return re.sub(r'\s+', ' ', H.unescape(re.sub(r'<[^>]+>', '', s))).strip()


def chapter_num(path):
    m = re.search(r'chapter-(\d\d)', str(path))
    return m.group(1) if m else '00'


# ── references ──────────────────────────────────────────────────────────

def refs_span(page):
    """(start, end) of the References section: from h2#references to the first <script> after it."""
    s = page.find(REF_H2)
    if s < 0:
        return None
    e = page.find('<script', s)
    return s, (e if e > 0 else len(page))


def author_segment(t):
    """Return (segment, style) for the first author of a reference's plain text."""
    t = t.lstrip(' "“ ')
    m = re.match(r'((?:[A-Z]\.(?:\s?-?[A-Z]\.)*\s+)+)([A-Z][\w’\'\-]+(?:\s[A-Z][\w’\'\-]+)?)', t)
    if m and not re.match(r'[A-Z]\.\s?[A-Z]', m.group(2)):
        seg = re.split(r',| and ', m.group(2))[0]
        return seg.strip(), 'ieee'
    m = re.match(r'([^,.\"“( ]+)([,.\"“( ])', t)
    seg = (m.group(1) if m else t[:40]).strip()
    seg = re.sub(r'\s+et al$', '', seg)
    style = 'surname' if (m and m.group(2) == ',' and len(seg.split()) <= 3) else 'other'
    return seg, style


def ref_record(li_inner):
    """Parse one reference <li> body into {key_base, year, names}."""
    t = text(li_inner)
    seg, style = author_segment(t)
    words = [fold(w) for w in seg.split() if fold(w)]
    ym = re.search(r'\b(' + YEAR + r')\b', t)
    year = ym.group(1) if ym else 'nd'
    if style in ('ieee', 'surname'):
        base = fold(seg)
    else:
        base = words[0] if words else 'ref'
    names = {w for w in words if w not in ORG_WORDS} | {fold(seg)}
    return {'base': base or 'ref', 'year': year, 'names': names, 'text': t}


LI_RE = re.compile(r'<li(?:\s+id="(ref-[^"]*)")?>(.*?)</li>', re.S)


def parse_refs(page):
    """List of dicts {start, end, inner, key, year, names} for every reference <li>, in order.

    Keys are stable: an <li> that already carries id="ref-…" keeps that key, so moving entries
    (e.g. to Further Reading) never re-letters a/b suffixes. New entries get surname-year, with
    a/b suffixes only when that base repeats.
    """
    span = refs_span(page)
    if not span:
        return []
    s0, e0 = span
    out = []
    for m in LI_RE.finditer(page, s0, e0):
        r = ref_record(m.group(2))
        out.append(dict(r, start=m.start(), end=m.end(), inner=m.group(2), fixed=(m.group(1) or '')[4:],
                        k0=f"{r['base']}-{r['year']}"))
    taken = {r['fixed'] for r in out if r['fixed']}
    counts = {}
    for r in out:
        counts[r['k0']] = counts.get(r['k0'], 0) + 1
    seen = {}
    for r in out:
        if r['fixed']:
            r['key'] = r['fixed']
            continue
        seen[r['k0']] = seen.get(r['k0'], 0) + 1
        key = r['k0'] + (chr(96 + seen[r['k0']]) if counts[r['k0']] > 1 else '')
        while key in taken:                      # never collide with an existing id
            seen[r['k0']] += 1
            key = r['k0'] + chr(96 + seen[r['k0']])
        taken.add(key)
        r['key'] = key
    return out


# ── citations ───────────────────────────────────────────────────────────

ITEM = re.compile(r'^\s*([A-Z][^,;\[\]()<>]*?),\s*(' + YEAR + r')([a-z]?)\s*$')
BRACKET = re.compile(r'\[([^\[\]<>]{3,240}?)\]')
PAREN = re.compile(r'\(([^()<>]{3,240}?)\)')
NARR = re.compile(r'\b([A-Z][A-Za-z’\'\-]+(?: et al\.| (?:and|&amp;|&) [A-Z][A-Za-z’\'\-]+)?)\s\((' + YEAR + r')([a-z]?)\)')
ETAL = re.compile(r'\b((?:(?:[Vv]an|[Vv]on|[Dd]e|[Dd]el|[Ll]e) )?[A-Z][A-Za-z’\'\-]+) et al\.(?! \[(?:<|$))')
VENUE = re.compile(r'\b(ISCA|MICRO|ASPLOS|HPCA|SOSP|OSDI|ISPASS|NDSS|PACT|EuroSys|CCS|TACO|DAC|ICPP|IISWC|FAST|SIGMETRICS|VEE|PLDI|NeurIPS|ICML|MLSys)(?:-\d+)?[ \u2019\']+((?:19|20)\d\d|\d\d)\b')
SKIP = re.compile(r'(<pre\b.*?</pre>|<code\b.*?</code>|<svg\b.*?</svg>|<h[1-6]\b.*?</h[1-6]>|<a\b.*?</a>|<[^>]+>)', re.S)


def cite_name(author_text):
    """'Bhattacharjee &amp; Lustig' / 'Kocher et al.' / 'Van Bulck et al.' -> 'bhattacharjee' / 'kocher' / 'vanbulck'."""
    a = H.unescape(author_text)
    a = re.split(r'\s+et al\.?|\s*&\s*|\s+and\s+', a)[0]
    return fold(a)


def items(content):
    """Split a bracket/paren body into [(author_text, year, suffix)] or None if any part isn't a citation."""
    out = []
    for part in content.replace('&amp;', '\x00').split(';'):
        m = ITEM.match(part.replace('\n', ' '))
        if not m:
            return None
        out.append((m.group(1).strip().replace('\x00', '&amp;'), m.group(2), m.group(3)))
    return out


def resolver(refs, aliases, ch):
    """Return resolve(author_text, year, suffix) -> ref key or None."""
    def resolve(author, year, suf):
        ak = f'ch{ch}:{H.unescape(author).strip()},{year}{suf}'
        if ak in aliases:
            return aliases[ak].removeprefix('ref-')
        n = cite_name(author)
        hits = [r for r in refs if r['year'] == year and (n in r['names'] or n == r['base'])]
        if suf:
            hits = [r for r in hits if r['key'].endswith(year + suf)]
        return hits[0]['key'] if len(hits) == 1 else None
    return resolve


def body_span(page):
    """Prose region: end of TOC nav to the References h2."""
    n = page.find('<nav id="TOC"')
    s = page.find('</nav>', n) + 6 if n >= 0 else page.find('<body')
    e = page.find(REF_H2)
    return s, (e if e > 0 else len(page))


def text_pieces(segment):
    """re.split on SKIP: even indices are plain text, odd are protected markup."""
    return SKIP.split(segment)


# ── TOC ────────────────────────────────────────────────────────────────

HEAD_RE = re.compile(r'<h([23]) id="([^"]+)"[^>]*>(.*?)</h\1>', re.S)
TOC_RE = re.compile(r'<nav id="TOC" role="doc-toc">.*?</nav>', re.S)


def headings(page):
    """[(level, id, text)] for h2/h3 in the body; stops at References (References h2 included)."""
    s, e = body_span(page)
    out = [(int(m.group(1)), m.group(2), text(m.group(3))) for m in HEAD_RE.finditer(page, s, e)]
    if REF_H2 in page:
        out.append((2, 'references', 'References'))
    return out


def ensure_h3_ids(page):
    """Give id-less body <h3> a stable slug id (unique on the page) so the TOC can link to them."""
    s, e = body_span(page)
    used = set(re.findall(r'\bid="([^"]+)"', page))

    def add(m):
        base = re.sub(r'[^a-z0-9]+', '-', text(m.group(1)).lower()).strip('-')[:60] or 'section'
        base = ('sec-' + base) if base[0].isdigit() else base
        hid, n = base, 2
        while hid in used:
            hid, n = f'{base}-{n}', n + 1
        used.add(hid)
        return f'<h3 id="{hid}">{m.group(1)}</h3>'
    body = re.sub(r'<h3>(.*?)</h3>', add, page[s:e], flags=re.S)
    return page[:s] + body + page[e:]


def toc_html(heads):
    """Flat h2 list with h3 sub-lists; ONE toggle (label + hidden checkbox) shows/hides all sub-lists. No JS."""
    esc = lambda s: H.escape(s, quote=False)
    groups = []
    for lvl, hid, t in heads:
        if lvl == 2 or not groups:
            groups.append([(hid, t), []])
        else:
            groups[-1][1].append((hid, t))
    lines = ['<nav id="TOC" role="doc-toc">',
             '<input type="checkbox" id="toc-expand" class="toc-expand" hidden>',
             '<label for="toc-expand" class="toc-head" title="Show/hide subsections">Contents</label>',
             '<ul>']
    for (hid, t), subs in groups:
        a = f'<a href="#{hid}">{esc(t)}</a>'
        if subs:
            a += '<ul class="toc-sub">' + ''.join(f'<li><a href="#{i}">{esc(x)}</a></li>' for i, x in subs) + '</ul>'
        lines.append(f'<li>{a}</li>')
    lines += ['</ul>', '</nav>']
    return '\n'.join(lines)
