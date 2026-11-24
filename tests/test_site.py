"""The case-study page is self-contained, current, and its bridge adds up."""

from __future__ import annotations

import json
import re

import pytest

from retailrev import site


def test_page_is_current_and_self_contained():
    html = site.OUT.read_text(encoding="utf-8")
    embedded = json.loads(re.search(r'application/json">(.*?)</script>', html, re.S).group(1))
    assert embedded == json.loads(json.dumps(site.page_data()))
    assert not re.search(r"(?:src=|@import|url\(|<link)", html)  # nothing loaded from anywhere else
    assert "__" not in re.sub(r'application/json">.*?</script>', "", html, flags=re.S)  # no unfilled placeholder


def test_bridge_parts_add_up():
    for b in site.page_data()["bridge"]:
        assert sum(p["v"] for p in b["parts"]) == pytest.approx(b["current"] - b["prior"], abs=1.0)
