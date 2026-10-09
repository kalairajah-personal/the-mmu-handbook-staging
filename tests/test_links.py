"""Tests for reflib / link_refs / build_toc / audit_links (PIPELINE §7). Run: python3 -m pytest tests -q"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))
import reflib as R
import link_refs as L
import build_toc as T
import audit_links as A

PAGE = '''<body><nav id="TOC" role="doc-toc">
<ul>
<li><a href="#section-2.1">2.1 Intro</a></li>
</ul>
</nav>
<h2 id="section-2.1">2.1 Intro</h2>
<h3 id="a">2.1.1 Alpha</h3>
<p>Paging is old [Denning, 1970]. Both [Bhattacharjee &amp;
Lustig, 2017; Denning, 1968]. Narrative: Belady (1966) showed it.
Parenthetical (Van Bulck et al., 2018) and a date (November 2017).
Code <code>[Denning, 1970]</code> stays. Unknown [Nobody, 1999].</p>
<h2 id="section-2.2">2.2 Next</h2>
<p>Text.</p>
<h2 id="references">References</h2>
<ol type="1">
<li><p><strong>Denning, P. J. (1968)</strong>. “The working set model”. doi:10.1145/363095.363141.</p></li>
<li><p><strong>Denning, P. J. (1970)</strong>. “Virtual memory”. https://example.org/vm.</p></li>
<li><p><strong>Belady, L. A. (1966)</strong>. “A study of replacement algorithms”.</p></li>
<li><p><strong>Bhattacharjee, A., &amp; Lustig, D. (2017)</strong>. <em>Architectural support</em>.</p></li>
<li><p>Van Bulck, J., Minkin, M. "Foreshadow." USENIX Security 2018.</p></li>
<li><p>T. Allen and R. Ge, “In-depth analyses of UVM,” SC21, 2021.</p></li>
<li><p>Intel Corporation. Intel 64 SDM. 2022.</p></li>
</ol>
<script>var CHAPTERS=[];</script>
</body>'''


def test_ref_keys():
    keys = [r['key'] for r in R.parse_refs(PAGE)]
    assert keys == ['denning-1968', 'denning-1970', 'belady-1966', 'bhattacharjee-2017',
                    'vanbulck-2018', 'allen-2021', 'intel-2022']


def test_duplicate_keys_get_suffix():
    p = PAGE.replace('(1970)</strong>', '(1968)</strong>')
    keys = [r['key'] for r in R.parse_refs(p)]
    assert keys[:2] == ['denning-1968a', 'denning-1968b']


def test_ref_links_and_ids():
    st = L.new_stats()
    out = L.link_refs(PAGE, '02', {'ch02:belady-1966': {'status': 'verified', 'doi': '10.1147/sj.52.0078'}}, st)
    assert '<li id="ref-denning-1968">' in out
    assert '<a class="ref-link" href="https://doi.org/10.1145/363095.363141">doi:10.1145/363095.363141</a>.' in out
    assert '<a class="ref-link" href="https://example.org/vm">https://example.org/vm</a>.' in out
    assert 'replacement algorithms”. <a class="ref-link" href="https://doi.org/10.1147/sj.52.0078">doi:10.1147/sj.52.0078</a></p>' in out
    assert st['ledger'] == 1 and 'intel-2022' in st['unlinked']


def test_citations():
    st = L.new_stats()
    out = L.process(PAGE, '02', {}, {}, True, st)
    assert '[<a class="cite" href="#ref-denning-1970">Denning, 1970</a>]' in out
    assert ('[<a class="cite" href="#ref-bhattacharjee-2017">Bhattacharjee &amp; Lustig, 2017</a>; '
            '<a class="cite" href="#ref-denning-1968">Denning, 1968</a>]') in out
    assert 'Belady [<a class="cite" href="#ref-belady-1966">1966</a>] showed' in out
    assert '[<a class="cite" href="#ref-vanbulck-2018">Van Bulck et al., 2018</a>]' in out
    assert '(November 2017)' in out
    assert '<code>[Denning, 1970]</code>' in out
    assert '[Nobody, 1999]' in out and any('Nobody' in u for u in st['unresolved'])


def test_alias_resolves():
    out = L.process(PAGE, '02', {}, {'ch02:Nobody,1999': 'ref-intel-2022'})
    assert '[<a class="cite" href="#ref-intel-2022">Nobody, 1999</a>]' in out


def test_idempotent():
    once = T.process(L.process(PAGE, '02', {}, {}))
    assert T.process(L.process(once, '02', {}, {})) == once


def test_toc_tree():
    out = T.process(PAGE)
    assert '<input type="checkbox" id="toc-expand" class="toc-expand" hidden>' in out
    assert '<label for="toc-expand" class="toc-head" title="Show/hide subsections">Contents</label>' in out
    assert ('<li><a href="#section-2.1">2.1 Intro</a><ul class="toc-sub"><li><a href="#a">2.1.1 Alpha</a></li></ul></li>') in out
    assert '<li><a href="#section-2.2">2.2 Next</a></li>' in out
    assert '<li><a href="#references">References</a></li>' in out
    assert 'details' not in out.split('<nav id="TOC"')[1].split('</nav>')[0]


def test_h3_without_id_gets_slug():
    p = PAGE.replace('<h3 id="a">2.1.1 Alpha</h3>', '<h3>2.1.1 Alpha <em>x</em></h3>')
    out = T.process(p)
    assert '<h3 id="sec-2-1-1-alpha-x">2.1.1 Alpha <em>x</em></h3>' in out
    assert '<a href="#sec-2-1-1-alpha-x">2.1.1 Alpha x</a>' in out
    assert T.process(out) == out


def test_audit(tmp_path):
    f = tmp_path / 'chapter-02-WITH-FIGURES.html'
    f.write_text(PAGE)
    errs, _ = A.audit(f, {}, {})
    assert any(e.startswith('G12c') for e in errs) and any(e.startswith('G12f') for e in errs)
    pg = PAGE.replace('<script>var CHAPTERS=[];</script>', '<script>' + CH + '</script>')
    f.write_text(F.process(T.process(L.process(pg, '02', {}, {'ch02:Nobody,1999': 'ref-intel-2022'})), 2))
    errs, warns = A.audit(f, {}, {'ch02:Nobody,1999': 'ref-intel-2022'})
    assert errs == []
    assert any('ref-belady-1966' in w for w in warns)


def test_ledger_change_replaces_appended_link():
    once = L.link_refs(PAGE, '02', {'ch02:belady-1966': {'status': 'search'}}, L.new_stats())
    assert 'ref-link--search' in once
    twice = L.link_refs(once, '02', {'ch02:belady-1966': {'status': 'verified', 'doi': '10.1147/sj.52.0078'}}, L.new_stats())
    assert 'ref-link--search' not in twice
    assert 'algorithms”. <a class="ref-link" href="https://doi.org/10.1147/sj.52.0078">doi:10.1147/sj.52.0078</a></p>' in twice
    gone = L.link_refs(twice, '02', {'ch02:belady-1966': {'status': 'none'}}, L.new_stats())
    assert 'sj.52.0078' not in gone
    assert L.link_refs(twice, '02', {'ch02:belady-1966': {'status': 'verified', 'doi': '10.1147/sj.52.0078'}}, L.new_stats()) == twice


import build_footer as F

CH = 'var CHAPTERS = [{"num": 1, "file": "chapter-01-WITH-FIGURES.html", "short": "One"}, {"num": 2, "file": "chapter-02-WITH-FIGURES.html", "short": "Two"}, {"num": 3, "file": "chapter-03-WITH-FIGURES.html", "short": "Three"}];'


def test_footer_replaces_next_chapter_and_moves_prose():
    p = PAGE.replace('</ol>\n<script>var CHAPTERS=[];</script>',
                     '</ol>\n<hr />\n<p>Closing prose.</p>\n<hr />\n<p><em>Next Chapter: X.</em></p>\n\n<script>' + CH + '</script>')
    out = F.process(p, 2)
    assert 'Next Chapter: X' not in out
    assert '<p>Closing prose.</p>\n<h2 id="references">' in out
    assert '&larr; Chapter 1: One' in out and 'Chapter 3: Three &rarr;' in out and '../index.html' in out
    assert F.process(out, 2) == out


def test_footer_ends():
    p = PAGE.replace('<script>var CHAPTERS=[];</script>', '<script>' + CH + '</script>')
    first, last = F.process(p, 1), F.process(p, 3)
    assert 'chapter-nav-prev' not in first and 'chapter-nav-next' in first
    assert 'chapter-nav-next' not in last and 'chapter-nav-prev' in last


def test_etal_and_venue_mentions_linked_without_text_change():
    p = PAGE.replace('Unknown [Nobody, 1999].', 'As Van Bulck et al. showed at USENIX, and Allen et al. at SC21. Kim et al. (2014) again.')
    out = L.process(p, '02', {}, {'ch02:Nobody,1999': 'ref-intel-2022'})
    assert '<a class="cite" href="#ref-vanbulck-2018">Van Bulck et al.</a>' in out
    assert '<a class="cite" href="#ref-allen-2021">Allen et al.</a>' in out
    assert 'Kim et al. (2014)' in out  # no ref for Kim in fixture: untouched
    assert L.process(out, '02', {}, {'ch02:Nobody,1999': 'ref-intel-2022'}) == out
