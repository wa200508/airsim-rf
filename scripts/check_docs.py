#!/usr/bin/env python3
"""Validate local files, Markdown fragments and unique explicit citation IDs."""
from collections import Counter
from pathlib import Path
import re
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]


def prose(text):
    return re.sub(r'^\s*(`{3,}|~{3,}).*?^\s*\1\s*$', '', text, flags=re.M | re.S)


def anchors(path):
    text = prose(path.read_text())
    explicit = re.findall(r'\bid=[\"\']([^\"\']+)[\"\']', text)
    duplicates = [key for key,count in Counter(explicit).items() if count > 1]
    result = set(explicit)
    counts = Counter()
    for title in re.findall(r'^#{1,6}\s+(.+?)\s*#*\s*$', text, flags=re.M):
        title = re.sub(r'\[([^]]+)\]\([^)]*\)', r'\1', title)
        title = re.sub(r'<[^>]+>', '', title).lower()
        slug = re.sub(r'[^\w\- ]', '', title).replace(' ', '-')
        n = counts[slug]; counts[slug] += 1
        result.add(slug if not n else f'{slug}-{n}')
    return result, duplicates


def check(paths):
    failures = []
    cache = {}
    for path in paths:
        own, duplicate = anchors(path)
        cache[path.resolve()] = own
        failures.extend(f'{path}: duplicate explicit id #{key}' for key in duplicate)
    for path in paths:
        for match in re.finditer(r'\]\(([^\s)]+)\)', prose(path.read_text())):
            link = match.group(1).strip('<>')
            if re.match(r'[a-zA-Z][a-zA-Z0-9+.-]*:', link):
                continue
            target, _, fragment = link.partition('#')
            dest = (path.parent/unquote(target)).resolve() if target else path.resolve()
            if not dest.exists():
                failures.append(f'{path}: missing file {target}')
            elif fragment and dest.suffix == '.md':
                if dest not in cache:
                    cache[dest] = anchors(dest)[0]
                if unquote(fragment) not in cache[dest]:
                    failures.append(f'{path}: missing fragment {link}')
    return failures


def main():
    paths = [ROOT/'README.md', ROOT/'THIRD_PARTY_NOTICES.md', *sorted((ROOT/'docs').rglob('*.md'))]
    failures = check(paths)
    if failures:
        raise SystemExit('Documentation validation failures:\n'+'\n'.join(failures))
    print(f'{len(paths)} maintained Markdown files: files/fragments resolve; explicit IDs are unique.')


if __name__ == '__main__':
    main()
