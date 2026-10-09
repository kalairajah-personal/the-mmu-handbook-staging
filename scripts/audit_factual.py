#!/usr/bin/env python3
"""G10 factual + G6p palette audit for the MMU Handbook.

Usage:  python3 scripts/audit_factual.py [--strict] [chapter numbers...]
Exit 1 on any ERROR. Warnings never fail unless --strict.

Checks
  G10a  reference author field is a group label with no person names        ERROR
  G10b  same work (title keyword) attributed to different venue/year       ERROR
  G10c  known-invalid artifact named in text (denylist below)               ERROR
  G10d  authoring leakage: markdown headings / "continues in next file"     ERROR
  G10e  duplicate numbered h2/h3 section numbers                            ERROR
  G10f  unsourced-anecdote markers (dated incident, $ figures, named firms) WARN
  G6p   SVG colour not in assets/figure-palette.json                        WARN (ERROR with --strict)
"""
import html, json, re, subprocess, sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(subprocess.check_output(['git', 'rev-parse', '--show-toplevel'], text=True).strip())
VENUES = r'(ISCA|MICRO|ASPLOS|HPCA|SIGMETRICS|ISPASS|NDSS|USENIX Security|OSDI|SOSP|EuroSys|ATC|PACT|TACO|IPDPS|CARRV|ISSCC)'
# Artifacts verified NOT to exist in cited primary sources. Extend as audits find more.
DENYLIST = {
    r'CUDA_ENABLE_1GB_PAGES': 'no such CUDA env var in NVIDIA docs',
    r'CUDA_ENABLE_2MB_PAGES': 'no such CUDA env var in NVIDIA docs',
    r'--query-gpu=page_fault': 'nvidia-smi has no page_fault query field',
    r'CONFIG_HUGETLB_PAGE_SIZE_1GB': 'not a Linux Kconfig symbol',
}
ANECDOTE = [
    r'On a (?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|January|February|March|April|May|June|July|August|September|October|November|December)\b[^.]{0,40}(?:morning|afternoon|evening)',
    r'engineers at a (?:leading|large|major|high-frequency)',
    r'\$\d[\d.,]*\s?(?:M|B|million|billion)\b',
    r'A (?:company|cloud provider|streaming service|financial services firm|production deployment) ',
]

def text(s):
    s = re.sub(r'<(script|style)\b.*?</\1>', '', s, flags=re.S)
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', s)))

def palette():
    p = json.loads((ROOT / 'assets/figure-palette.json').read_text())
    return {v.lstrip('#').upper() for k, v in p.items() if not k.startswith('_')}

def audit(path, pal, strict):
    raw = path.read_text()
    errs, warns = [], []
    m = re.search(r'<h2[^>]*id="references"[^>]*>', raw)
    body_raw, refs_raw = (raw[:m.start()], raw[m.end():]) if m else (raw, '')
    body = text(body_raw)
    refs = [text(x).strip() for x in re.findall(r'<li\b.*?</li>', refs_raw, re.S)]

    # G10a
    for i, r in enumerate(refs, 1):
        head = r.split('"')[0]
        if re.search(r'(Research Group|Research Team|Systems Group|Lab)\b', head) and not re.search(r'[A-Z][a-z]+, [A-Z]\.', head):
            errs.append(f'G10a ref {i}: group-label author: {head.strip()[:70]}')

    # G10b
    for i, r in enumerate(refs, 1):
        t = re.search(r'"([A-Z][A-Za-z0-9-]{3,}):', r)
        if not t:
            continue
        key = t.group(1)
        rv = re.search(VENUES + r'[^0-9]{0,40}(\d{4})', r) or re.search(VENUES, r)
        ry = re.search(r'\b(19|20)\d{2}\b', r)
        refset = {(rv.group(1) if rv else None), (ry.group(0) if ry else None)}
        for mm in re.finditer(re.escape(key) + r'[^.]{0,80}?' + VENUES + r'\s*(\d{4})', body):
            if mm.group(1) not in refset or mm.group(2) not in refset:
                errs.append(f'G10b "{key}": text says {mm.group(1)} {mm.group(2)}, ref {i} says {rv.group(1) if rv else "?"} {ry.group(0) if ry else "?"}')

    # G10c
    for pat, why in DENYLIST.items():
        n = len(re.findall(re.escape(pat), raw))
        if n:
            errs.append(f'G10c {pat} ×{n}: {why}')

    # G10d
    leak = re.findall(r'(?:^|\s)#{2,3} \d+\.\d+ [A-Z]', body) + re.findall(r'(?:Content continues|Continue with sections|in next file)', body)
    if leak:
        errs.append(f'G10d authoring leakage ×{len(leak)}: {leak[0].strip()[:50]}')

    # G10e
    nums = [h for h in re.findall(r'<h[23][^>]*>\s*(\d+\.\d+(?:\.\d+)?)\s', body_raw)]
    dup = [n for n, c in Counter(nums).items() if c > 1]
    if dup:
        errs.append(f'G10e duplicate section numbers: {", ".join(sorted(dup))}')

    # G10f
    for pat in ANECDOTE:
        for mm in re.finditer(pat, body):
            warns.append(f'G10f anecdote/figure needs source or hypothetical label: …{body[max(0,mm.start()-30):mm.end()+40]}…')

    # G6p
    off = Counter()
    for sv in re.findall(r'<svg\b.*?</svg>', raw, re.S):
        for c in re.findall(r'(?:fill|stroke|stop-color)\s*[:=]\s*"?#([0-9A-Fa-f]{6})', sv):
            if c.upper() not in pal:
                off[c.upper()] += 1
    if off:
        msg = f'G6p {sum(off.values())} off-palette colour uses ({len(off)} distinct): ' + ', '.join(f'#{k}×{v}' for k, v in off.most_common(6))
        (errs if strict else warns).append(msg)
    return errs, warns

def main():
    strict = '--strict' in sys.argv
    want = {int(a) for a in sys.argv[1:] if a.isdigit()}
    pal = palette()
    files = sorted((ROOT / 'chapters').glob('chapter-*-WITH-FIGURES.html'))
    tot_e = tot_w = 0
    for f in files:
        n = int(re.search(r'chapter-(\d+)', f.name).group(1))
        if want and n not in want:
            continue
        e, w = audit(f, pal, strict)
        tot_e += len(e); tot_w += len(w)
        print(f'{"✅" if not e else "❌"}  Chapter {n:02d}  errors={len(e)} warnings={len(w)}')
        for x in e: print('     ERROR', x)
        for x in w[:8]: print('     warn ', x)
        if len(w) > 8: print(f'     … {len(w)-8} more warnings')
    print(f'\nSUMMARY: {tot_e} errors, {tot_w} warnings')
    sys.exit(1 if tot_e else 0)

if __name__ == '__main__':
    main()
