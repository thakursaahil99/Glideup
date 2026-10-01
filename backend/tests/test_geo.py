"""Location parsing against strings taken from the real job boards."""

import pytest

from app.db.models import WorkMode
from app.jobsources.geo import (
    INDIA_STATES,
    location_index,
    lookup_state,
    parse_location,
)
from app.jobsources.geo_data import STATES
from app.jobsources.normalize import remote_scope

Place = tuple[str | None, str | None, str | None]


def places(text: str, **kwargs: object) -> list[Place]:
    return [(p.country, p.state, p.city) for p in parse_location(text, **kwargs).places]  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # India: names, aliases, country codes, office codes
        ("Bengaluru, India", [("IN", "Karnataka", "Bengaluru")]),
        ("Bangalore, IND", [("IN", "Karnataka", "Bengaluru")]),
        ("Bangalore, Karnataka", [("IN", "Karnataka", "Bengaluru")]),
        ("Bengaluru - BLR1", [("IN", "Karnataka", "Bengaluru")]),
        ("Bengaluru-VTP, India", [("IN", "Karnataka", "Bengaluru")]),
        ("Bangalore - DD", [("IN", "Karnataka", "Bengaluru")]),  # DD is an office code here
        ("Gurgaon, IND", [("IN", "Haryana", "Gurugram")]),
        ("Noida, Uttar Pradesh", [("IN", "Uttar Pradesh", "Noida")]),
        ("Noida, UP", [("IN", "Uttar Pradesh", "Noida")]),
        ("Bombay", [("IN", "Maharashtra", "Mumbai")]),
        ("Madras, Tamil Nadu", [("IN", "Tamil Nadu", "Chennai")]),
        ("Delhi, India", [("IN", "Delhi", "Delhi")]),
        ("New Delhi", [("IN", "Delhi", "New Delhi")]),
        ("Bir, Himachal Pradesh", [("IN", "Himachal Pradesh", "Bir")]),
        ("Remote - India", [("IN", None, None)]),
        (
            "Bangalore, IND; Hyderabad, IND",
            [("IN", "Karnataka", "Bengaluru"), ("IN", "Telangana", "Hyderabad")],
        ),
        # United States: abbreviations in context, multi-location separators
        ("San Francisco, CA | New York City, NY", [("US", "California", "San Francisco"), ("US", "New York", "New York")]),  # noqa: E501
        ("New York, NY (HQ)", [("US", "New York", "New York")]),
        ("Seattle, Washington, United States", [("US", "Washington", "Seattle")]),
        ("Washington, D.C.", [("US", "District of Columbia", "Washington")]),
        ("Indianapolis, IN", [("US", "Indiana", "Indianapolis")]),  # IN = Indiana here, not India
        ("Clarks Summit, PA", [("US", "Pennsylvania", "Clarks Summit")]),  # unknown city kept
        ("US-San Francisco, US-New York, US-Remote", [("US", "California", "San Francisco"), ("US", "New York", "New York")]),  # noqa: E501
        ("Remote - US", [("US", None, None)]),
        # Elsewhere
        ("Canada - Remote (ON, AB, BC, or NS Only)", [("CA", "Ontario", None), ("CA", "Alberta", None), ("CA", "British Columbia", None)]),  # noqa: E501
        ("Melbourne, Victoria", [("AU", "Victoria", "Melbourne")]),
        ("Japan, Tokyo", [("JP", None, "Tokyo")]),
        ("London, UK", [("GB", "England", "London")]),
        ("Cambridge, UK", [("GB", None, "Cambridge")]),  # explicit country beats the US guess
        ("Chicago, Toronto", [("US", "Illinois", "Chicago"), ("CA", "Ontario", "Toronto")]),
        ("Munich, Germany", [("DE", "Bavaria", "Munich")]),
        # Not places
        ("Hybrid", []),
        ("Remote", []),
        ("N/A", []),
        ("Remote Friendly, UK", [("GB", None, None)]),
        ("Remote-first", []),
    ],
)  # fmt: skip
def test_real_world_locations(text: str, expected: list[Place]) -> None:
    assert places(text) == expected


def test_india_has_every_state_and_union_territory() -> None:
    assert len(INDIA_STATES) == 36
    for state in INDIA_STATES:
        assert lookup_state(state, None) == ("IN", state)
    for alias, canonical in [
        ("Orissa", "Odisha"),
        ("Pondicherry", "Puducherry"),
        ("J&K", "Jammu and Kashmir"),
        ("Uttaranchal", "Uttarakhand"),
        ("NCT of Delhi", "Delhi"),
    ]:
        assert lookup_state(alias, None) == ("IN", canonical)


def test_abbreviations_need_context() -> None:
    assert lookup_state("KA", None) is None  # could be anything without a country
    assert lookup_state("KA", "IN") == ("IN", "Karnataka")
    assert lookup_state("TN", "US") == ("US", "Tennessee")
    assert lookup_state("TN", "IN") == ("IN", "Tamil Nadu")
    assert all(state in STATES for state in ("US", "CA", "GB", "AU", "DE", "IN"))


def test_remote_and_worldwide_detection() -> None:
    assert parse_location("Remote - India").remote
    worldwide = parse_location("Remote, Global")
    assert (worldwide.remote, worldwide.worldwide) == (True, True)
    assert not parse_location("Bengaluru").remote


def test_remote_scope() -> None:
    india = parse_location("Remote - India")
    anywhere = parse_location("Distributed")
    assert remote_scope(WorkMode.REMOTE, india) == "country"
    assert remote_scope(WorkMode.REMOTE, anywhere) == "worldwide"
    assert remote_scope(WorkMode.REMOTE, parse_location("Anywhere, India")) == "worldwide"
    assert remote_scope(WorkMode.HYBRID, india) is None


def test_country_hint_fills_gaps() -> None:
    assert places("Bangalore - WF", country_hint="IN") == [("IN", "Karnataka", "Bengaluru")]
    assert places("Remote", country_hint="IN") == [("IN", None, None)]
    assert places("Pune", country_hint="in") == [("IN", "Maharashtra", "Pune")]


def test_structured_region_hint_from_adzuna() -> None:
    assert places("Bangalore", region_hint=["India", "Karnataka", "Bangalore"]) == [
        ("IN", "Karnataka", "Bengaluru")
    ]
    # Unknown towns are kept as published rather than dropped.
    assert places("Hosur", region_hint=["India", "Tamil Nadu", "Hosur"]) == [
        ("IN", "Tamil Nadu", "Hosur")
    ]
    assert places("London", region_hint=["UK", "London"]) == [("GB", "London", None)]


def test_location_index() -> None:
    parsed = parse_location("Bangalore, IND; Pune, IND")
    assert location_index(parsed) == "|c:IN|s:Karnataka|s:Maharashtra|ci:Bengaluru|ci:Pune|"
    assert location_index(parse_location("Remote")) == ""
