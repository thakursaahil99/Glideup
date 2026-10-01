"""Best-effort country detection from free-text locations ("Bengaluru-VTP, India")."""

import re

_COUNTRIES = {
    "india": "IN", "united states": "US", "usa": "US", "united kingdom": "GB", "uk": "GB",
    "england": "GB", "ireland": "IE", "germany": "DE", "france": "FR", "netherlands": "NL",
    "spain": "ES", "portugal": "PT", "italy": "IT", "poland": "PL", "sweden": "SE",
    "switzerland": "CH", "canada": "CA", "mexico": "MX", "brazil": "BR", "argentina": "AR",
    "singapore": "SG", "japan": "JP", "australia": "AU", "new zealand": "NZ",
    "united arab emirates": "AE", "uae": "AE", "israel": "IL", "south korea": "KR",
    "philippines": "PH", "indonesia": "ID", "denmark": "DK", "norway": "NO", "finland": "FI",
    "belgium": "BE", "austria": "AT", "czech republic": "CZ", "romania": "RO",
}  # fmt: skip

_CITIES = {
    "bengaluru": "IN", "bangalore": "IN", "mumbai": "IN", "pune": "IN", "hyderabad": "IN",
    "chennai": "IN", "delhi": "IN", "new delhi": "IN", "gurugram": "IN", "gurgaon": "IN",
    "noida": "IN", "kolkata": "IN", "ahmedabad": "IN", "jaipur": "IN", "chandigarh": "IN",
    "san francisco": "US", "new york": "US", "seattle": "US", "austin": "US", "boston": "US",
    "chicago": "US", "los angeles": "US", "denver": "US", "atlanta": "US", "washington": "US",
    "palo alto": "US", "mountain view": "US", "menlo park": "US", "sunnyvale": "US",
    "london": "GB", "dublin": "IE", "berlin": "DE", "munich": "DE", "paris": "FR",
    "amsterdam": "NL", "toronto": "CA", "vancouver": "CA", "tokyo": "JP", "sydney": "AU",
    "tel aviv": "IL", "zurich": "CH", "stockholm": "SE", "madrid": "ES", "barcelona": "ES",
    "warsaw": "PL", "lisbon": "PT", "dubai": "AE", "sao paulo": "BR", "mexico city": "MX",
}  # fmt: skip

# Common alternative spellings users type when searching.
CITY_ALIASES = {"bangalore": "bengaluru", "gurgaon": "gurugram", "bombay": "mumbai"}


def location_variants(term: str) -> set[str]:
    """All spellings of a place: "bengaluru" -> {"bengaluru", "bangalore"}."""
    term = " ".join(term.lower().split())
    canonical = CITY_ALIASES.get(term, term)
    return {canonical} | {alias for alias, target in CITY_ALIASES.items() if target == canonical}


_US_STATE = re.compile(r",\s*(?:[A-Z]{2})(?:\b|$)")


def guess_country(location: str | None) -> str | None:
    if not location:
        return None
    lowered = location.lower()
    for name, code in _COUNTRIES.items():
        if re.search(rf"\b{re.escape(name)}\b", lowered):
            return code
    for city, code in _CITIES.items():
        if re.search(rf"\b{re.escape(city)}\b", lowered):
            return code
    if _US_STATE.search(location):
        return "US"
    return None


def location_terms(location: str | None) -> list[str]:
    """Normalised tokens for exact location filtering ("Bangalore - WF" -> ["bengaluru", ...])."""
    if not location:
        return []
    terms: set[str] = set()
    for part in re.split(r"[,;/|()\-\u2013]+", location.lower()):
        part = " ".join(part.split())
        if part:
            terms.add(CITY_ALIASES.get(part, part))
    country = guess_country(location)
    if country:
        terms.add(country.lower())
    return sorted(terms)
