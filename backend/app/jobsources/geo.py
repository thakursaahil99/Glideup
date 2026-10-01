"""Location parsing: free-text job locations -> structured places (country / state / city).

Real inputs from the job boards include "Bangalore, IND", "Noida, Uttar Pradesh",
"Remote - US", "San Francisco, CA | New York City, NY", "US-San Francisco, US-Remote",
"Canada - Remote (ON, AB, BC, or NS Only)" and "Bengaluru - BLR1". The parser walks the
comma/dash-separated tokens of each segment, using the previous tokens as context (so "CA"
after "San Francisco" is California, and "Victoria" after "Melbourne" is the Australian state).
"""

import re
from dataclasses import dataclass, field

from app.jobsources.geo_data import CITIES, COUNTRIES, STATES

# ------------------------------------------------------------------ lookup tables


def _key(text: str) -> str:
    return " ".join(re.sub(r"[.’']", "", text.lower()).split())  # noqa: RUF001


COUNTRY_NAMES: dict[str, str] = {code: name for code, (name, _) in COUNTRIES.items()}
_COUNTRY_LOOKUP: dict[str, str] = {}
for _code, (_name, _aliases) in COUNTRIES.items():
    for _alias in (_name, *_aliases):
        _COUNTRY_LOOKUP[_key(_alias)] = _code

# state name/alias -> [(country, canonical)], abbreviation -> {country: canonical}
_STATE_NAMES: dict[str, list[tuple[str, str]]] = {}
_STATE_ABBR: dict[str, dict[str, str]] = {}
for _country, _states in STATES.items():
    for _state, (_aliases, _abbrs) in _states.items():
        for _alias in (_state, *_aliases):
            _STATE_NAMES.setdefault(_key(_alias), []).append((_country, _state))
        for _abbr in _abbrs:
            _STATE_ABBR.setdefault(_abbr, {})[_country] = _state

_CITY_LOOKUP: dict[str, tuple[str, str, str | None]] = {}
for _city, (_city_country, _city_state, _city_aliases) in CITIES.items():
    for _alias in (_city, *_city_aliases):
        _CITY_LOOKUP.setdefault(_key(_alias), (_city, _city_country, _city_state))

# Common alternative spellings (for the database search fallback).
CITY_ALIASES: dict[str, str] = {
    _key(alias): _key(city) for city, (_c, _s, aliases) in CITIES.items() for alias in aliases
}

INDIA_STATES = sorted(STATES["IN"])

_REMOTE = re.compile(r"\b(remote|distributed|anywhere|worldwide|global|work from home|wfh)\b", re.I)
_WORLDWIDE = re.compile(r"\b(anywhere|worldwide|global|international)\b", re.I)
_NOISE = re.compile(
    r"\b(hybrid|on-?site|in[- ]office|office|hq|headquarters|only|all locations|"
    r"and|or|based|area|metro|region|in the world|friendly|first|preferred|flexible)\b",
    re.I,
)
_SEGMENT_SPLIT = re.compile(r"\s*(?:;|\||•|·|\s/\s|\s+or\s+)\s*")
_TOKEN_SPLIT = re.compile(r"\s*(?:,|\s[-–—]\s|[()]|:)\s*")  # noqa: RUF001
_CODE_PREFIX = re.compile(r"\b([A-Z]{2,3})-(?=[A-Z][a-z])")  # "US-San Francisco"
_CODE_SUFFIX = re.compile(r"([a-z])-(?=[A-Z0-9]{2,5}\b)")  # "Bengaluru-VTP"
_OFFICE_CODE = re.compile(r"^[A-Z0-9]{1,5}$|\d")  # "BLR1", "DD", "VTP", "WF"


# ------------------------------------------------------------------ result types


@dataclass
class Place:
    country: str | None = None
    state: str | None = None
    city: str | None = None
    country_explicit: bool = False

    def key(self) -> tuple[str | None, str | None, str | None]:
        return (self.country, self.state, self.city)


@dataclass
class ParsedLocation:
    places: list[Place] = field(default_factory=list)
    remote: bool = False
    worldwide: bool = False

    def _unique(self, attr: str) -> list[str]:
        seen: dict[str, None] = {}
        for place in self.places:
            value = getattr(place, attr)
            if value:
                seen[value] = None
        return list(seen)

    @property
    def countries(self) -> list[str]:
        return self._unique("country")

    @property
    def states(self) -> list[str]:
        return self._unique("state")

    @property
    def cities(self) -> list[str]:
        return self._unique("city")


# ------------------------------------------------------------------ token classification


def lookup_country(text: str) -> str | None:
    return _COUNTRY_LOOKUP.get(_key(text))


def lookup_state(text: str, country: str | None) -> tuple[str, str] | None:
    """(country, canonical state). Abbreviations only match with a known country."""
    raw = text.strip()
    if raw.isalpha() and raw.isupper() and len(raw) <= 3:
        options = _STATE_ABBR.get(raw, {})
        if country and country in options:
            return country, options[country]
        return None
    for cand_country, state in _STATE_NAMES.get(_key(raw), []):
        if country is None or cand_country == country:
            return cand_country, state
    return None


def lookup_city(text: str) -> tuple[str, str, str | None] | None:
    return _CITY_LOOKUP.get(_key(text))


def _clean_token(token: str) -> str:
    token = _REMOTE.sub(" ", token)
    token = _NOISE.sub(" ", token)
    return " ".join(token.split()).strip(" -–—.")  # noqa: RUF001


def _parse_segment(segment: str, places: list[Place]) -> None:
    segment = _CODE_PREFIX.sub(r"\1, ", segment)
    segment = _CODE_SUFFIX.sub(r"\1 - ", segment)
    current: Place | None = None
    pending: str | None = None  # an unknown token that may be a city ("Clarks Summit, PA")

    def start(place: Place) -> Place:
        places.append(place)
        return place

    for raw in _TOKEN_SPLIT.split(segment):
        token = _clean_token(raw)
        if not token:
            continue
        ctx = current.country if current else None

        # Names that are both a city and a state ("Delhi", "New York", "Washington") are the
        # city unless the place already has one ("Seattle, Washington" -> the state).
        city = lookup_city(token)
        confirms_state = (
            current is not None
            and current.city is not None
            and (as_state := lookup_state(token, ctx)) is not None
            and as_state[1] == current.state
        )
        if city is not None and not pending and not confirms_state:
            name, city_country, state_name = city
            if (
                current is not None
                and current.city is None
                and current.country in (None, city_country)
                and current.state in (None, state_name)
            ):
                current.city, current.country = name, city_country
                current.state = current.state or state_name
            else:
                current = start(Place(city_country, state_name, name))
            continue

        state = lookup_state(token, ctx)
        if state is None and token.isupper() and len(token) == 2 and pending:
            state = lookup_state(token, "US")  # "Clarks Summit, PA"
        is_abbreviation = token.isalpha() and token.isupper() and len(token) <= 3
        if (
            state is not None
            and is_abbreviation
            and current is not None
            and current.city is not None
            and current.state not in (None, state[1])
        ):
            # An abbreviation may fill in or confirm a state, never add a different one:
            # "Bangalore - DD" is an office code, not Dadra and Nagar Haveli and Daman and Diu.
            state = None
        if state is not None:
            country, name = state
            if pending:
                current = start(Place(country, name, pending))
            elif (
                current is not None
                and current.state in (None, name)
                and current.country in (None, country)
            ):
                current.country, current.state = country, name
            else:
                current = start(Place(country, name))
            pending = None
            continue

        country_code = lookup_country(token)
        if country_code is not None:
            if pending:
                current = start(Place(country_code, None, pending, True))
            elif current is not None and not current.country_explicit:
                if current.country not in (None, country_code):
                    current.state = None  # the inferred state belonged to another country
                current.country, current.country_explicit = country_code, True
            elif current is None or current.country != country_code:
                current = start(Place(country_code, country_explicit=True))
            pending = None
            continue

        city = lookup_city(token)
        if city is not None:
            name, city_country, state_name = city
            if (
                current is not None
                and current.city is None
                and current.country in (None, city_country)
                and current.state in (None, state_name)
            ):
                current.city, current.country = name, city_country
                current.state = current.state or state_name
            else:
                current = start(Place(city_country, state_name, name))
            pending = None
            continue

        if not _OFFICE_CODE.search(token) and len(token) >= 3:
            pending = token  # maybe a city we don't know; confirmed by a following state/country


def parse_location(
    text: str | None,
    *,
    country_hint: str | None = None,
    region_hint: list[str] | None = None,
) -> ParsedLocation:
    text = (text or "").strip()
    result = ParsedLocation(
        remote=bool(_REMOTE.search(text)), worldwide=bool(_WORLDWIDE.search(text))
    )

    if region_hint:  # structured source data, e.g. Adzuna: ["India", "Karnataka", "Bangalore"]
        country = lookup_country(region_hint[0]) or country_hint
        state = lookup_state(region_hint[1], country) if len(region_hint) > 1 else None
        city = lookup_city(region_hint[-1]) if len(region_hint) > 2 else None
        result.places.append(
            Place(
                country=country,
                state=state[1] if state else (region_hint[1] if len(region_hint) > 1 else None),
                city=city[0] if city else (region_hint[-1] if len(region_hint) > 2 else None),
                country_explicit=True,
            )
        )
        return result

    places: list[Place] = []
    for segment in _SEGMENT_SPLIT.split(text):
        if segment.strip():
            _parse_segment(segment, places)

    hint = country_hint.upper() if country_hint and len(country_hint) == 2 else None
    if hint:
        for place in places:
            place.country = place.country or hint
        if not places:
            places.append(Place(country=hint))

    unique: dict[tuple[str | None, str | None, str | None], Place] = {}
    for place in places:
        if place.country or place.state or place.city:
            unique.setdefault(place.key(), place)
    result.places = list(unique.values())
    return result


# ------------------------------------------------------------------ helpers for callers


def state_countries(state: str) -> set[str]:
    """Countries a canonical state name belongs to (empty if not in the gazetteer)."""
    return {country for country, name in _STATE_NAMES.get(_key(state), []) if name == state}


def city_place(city: str) -> tuple[str, str | None] | None:
    """(country, state) of a canonical city, or None if not in the gazetteer."""
    found = _CITY_LOOKUP.get(_key(city))
    return (found[1], found[2]) if found else None


def guess_country(location: str | None) -> str | None:
    countries = parse_location(location).countries
    return countries[0] if countries else None


def location_variants(term: str) -> set[str]:
    """All spellings of a place: "bengaluru" -> {"bengaluru", "bangalore", ...}."""
    term = _key(term)
    canonical = CITY_ALIASES.get(term, term)
    return {canonical} | {alias for alias, target in CITY_ALIASES.items() if target == canonical}


def location_index(parsed: ParsedLocation) -> str:
    """'|c:IN|s:Karnataka|ci:Bengaluru|' - exact-token filtering for the database fallback."""
    parts = [f"c:{c}" for c in parsed.countries]
    parts += [f"s:{s}" for s in parsed.states]
    parts += [f"ci:{c}" for c in parsed.cities]
    return "|" + "|".join(parts) + "|" if parts else ""
