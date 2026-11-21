"""Justice Manual extraction from a real chapter page excerpt (justice.gov, fetched 2026-10-16)."""

from pathlib import Path

import pytest

from uslaw_mcp.server import jm_extract

PAGE = (Path(__file__).resolve().parents[3] / "plugins" / "legal-research" / "tests" / "fixtures"
        / "jm-9-28.700-excerpt.html").read_text(encoding="utf-8")


def test_section_text_heading_and_update():
    text, heading, updated = jm_extract(PAGE, "9-28.700")
    assert heading == "The Value of Cooperation"
    assert updated == "March 2023"
    assert text.startswith("Cooperation is a mitigating factor")
    assert "[1] Of course, in addition to cooperation in an investigation" in text
    assert "9-28.710" not in text.split("\n")[0]


def test_missing_section_raises():
    with pytest.raises(ValueError, match="not on its chapter page"):
        jm_extract(PAGE, "9-28.999")
