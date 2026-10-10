"""Regression coverage for ambiguous citations and silently broken fragments."""
import importlib.util
from pathlib import Path

spec=importlib.util.spec_from_file_location('check_docs',Path(__file__).resolve().parents[1]/'scripts/check_docs.py')
docs=importlib.util.module_from_spec(spec)
spec.loader.exec_module(docs)


def test_fragment_and_duplicate_citation_failures(tmp_path):
    page=tmp_path/'page.md'
    page.write_text('# Good heading\n[ok](#good-heading)\n[bad](#gone)\n<a id="ref1"></a>\n<a id="ref1"></a>\n')
    failures=docs.check([page])
    assert len(failures)==2
    assert any('duplicate explicit id #ref1' in f for f in failures)
    assert any('missing fragment #gone' in f for f in failures)


def test_code_examples_are_not_links_and_repeated_headings_resolve(tmp_path):
    page=tmp_path/'page.md'
    page.write_text('# Same\n# Same\n[ok](#same-1)\n```python\n[example](missing.md)\n```\n')
    assert not docs.check([page])
