#!/usr/bin/env python3
"""Check local Markdown links in the maintained documentation (outside fenced code)."""
from pathlib import Path
import re
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]


def main():
    failures = []
    paths = [ROOT/'README.md', ROOT/'THIRD_PARTY_NOTICES.md', *sorted((ROOT/'docs').rglob('*.md'))]
    for path in paths:
        text = re.sub(r'```.*?```', '', path.read_text(), flags=re.S)
        for link in re.findall(r'\]\(([^\s)]+)\)', text):
            if re.match(r'[a-zA-Z]+:|#', link):
                continue
            target = unquote(link.split('#')[0])
            if target and not (path.parent/target).exists():
                failures.append(f'{path.relative_to(ROOT)}: {target}')
    if failures:
        raise SystemExit('Broken documentation links:\n'+'\n'.join(failures))
    print(f'{len(paths)} maintained Markdown files: local links resolve.')


if __name__ == '__main__':
    main()
