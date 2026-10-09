#!/usr/bin/env python3
"""Repo hygiene gate (G11).

Fails when:
  G11a  .nojekyll is missing at the repo root (GitHub Pages would run Jekyll and
        publish stray Markdown as HTML pages)
  G11b  any Markdown file exists outside the root README.md (stale copies of
        chapters must not be committed; the HTML in chapters/ is the only source)

Usage: python3 scripts/audit_repo.py   (exit 1 on failure)
"""
import subprocess, sys
from pathlib import Path

root = Path(subprocess.check_output(['git', 'rev-parse', '--show-toplevel'], text=True).strip())
errors = []
if not (root / '.nojekyll').exists():
    errors.append('G11a .nojekyll missing at repo root')
tracked = subprocess.check_output(['git', 'ls-files', '*.md', '**/*.md'], cwd=root, text=True).split()
extra = sorted(p for p in set(tracked) if p != 'README.md' and not p.startswith('.github/'))
# untracked but not git-ignored (caches such as .pytest_cache are ignored via .gitignore)
untracked = [p for p in subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard', '*.md', '**/*.md'],
                                                cwd=root, text=True).split()
             if p != 'README.md' and not p.startswith('.github/')]
for p in sorted(set(extra) | set(untracked)):
    errors.append(f'G11b stray Markdown file: {p}')
for e in errors:
    print('ERROR', e)
print(f'SUMMARY: {len(errors)} errors')
sys.exit(1 if errors else 0)
