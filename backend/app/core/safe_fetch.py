"""Fetch a user-supplied URL without letting it reach our own network (SSRF).

A URL a user types ("analyze my portfolio") is fetched by *our* server, so it must not be
able to point at localhost, the office LAN, or a cloud metadata endpoint. Every hop:

- only http/https on the default ports;
- the hostname is resolved once and *every* address must be public (`is_global`);
- the request connects to that vetted IP (Host header and TLS SNI keep the real name),
  so a DNS answer that changes between check and connect (rebinding) can't slip through;
- redirects are followed by hand, re-vetting each hop, at most `max_redirects`;
- the body is streamed and cut off at `max_bytes`; only text/HTML content is accepted.
"""

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import httpx

USER_AGENT = "GlideUp/0.1 (portfolio analyzer; fetches only the page the user submitted)"
ALLOWED_CONTENT_TYPES = ("text/html", "application/xhtml+xml", "text/plain")
_DEFAULT_PORTS = {"http": 80, "https": 443}

Resolver = Callable[[str, int], Awaitable[list[str]]]


class UnsafeUrlError(ValueError):
    """The URL points somewhere we refuse to fetch (shown to the user)."""


class FetchError(Exception):
    """The site could not be fetched (shown to the user)."""


@dataclass(frozen=True, slots=True)
class FetchedPage:
    url: str  # final URL after redirects
    content_type: str
    text: str


async def system_resolver(host: str, port: int) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(
        host, port, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP
    )
    return sorted({str(info[4][0]) for info in infos})


def _is_public(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%", 1)[0])  # drop an IPv6 zone id
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


async def vet_url(url: str, resolver: Resolver = system_resolver) -> tuple[str, str, str]:
    """Return (scheme, host, public ip) for a fetchable URL, or raise UnsafeUrlError."""
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    if scheme not in _DEFAULT_PORTS:
        raise UnsafeUrlError("Only http:// and https:// links can be analyzed.")
    if parts.username or parts.password:
        raise UnsafeUrlError("Links with a username or password can't be analyzed.")
    host = (parts.hostname or "").rstrip(".").lower()
    if not host:
        raise UnsafeUrlError("That link has no website address.")
    try:
        port = parts.port
    except ValueError as exc:
        raise UnsafeUrlError("That link has an invalid port.") from exc
    if port not in (None, _DEFAULT_PORTS[scheme]):
        raise UnsafeUrlError("Only websites on the standard ports can be analyzed.")
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        raise UnsafeUrlError("Use the website's name, not an IP address.")
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        raise UnsafeUrlError("That address is not a public website.")
    try:
        addresses = await resolver(host, _DEFAULT_PORTS[scheme])
    except OSError as exc:
        raise FetchError("We couldn't find that website. Check the link.") from exc
    if not addresses:
        raise FetchError("We couldn't find that website. Check the link.")
    if not all(_is_public(a) for a in addresses):
        raise UnsafeUrlError("That address is not a public website.")
    return scheme, host, addresses[0]


def _pinned_request(url: str, host: str, ip: str) -> httpx.Request:
    parts = urlsplit(url)
    netloc = f"[{ip}]" if ":" in ip else ip
    target = parts._replace(netloc=netloc).geturl()
    return httpx.Request(
        "GET",
        target,
        headers={
            "Host": host,
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml;q=0.9,text/plain;q=0.8",
        },
        extensions={"sni_hostname": host},
    )


async def fetch_page(
    url: str,
    *,
    max_bytes: int = 2 * 1024 * 1024,
    timeout: float = 10.0,
    max_redirects: int = 3,
    resolver: Resolver = system_resolver,
    transport: httpx.AsyncBaseTransport | None = None,
) -> FetchedPage:
    # httpx timeouts apply per read; this caps the whole fetch, so a server that drips
    # one byte at a time can't hold a worker for long.
    try:
        async with asyncio.timeout(timeout * 2):
            return await _fetch(url, max_bytes, timeout, max_redirects, resolver, transport)
    except TimeoutError as exc:
        raise FetchError("The website took too long to respond.") from exc


async def _fetch(
    url: str,
    max_bytes: int,
    timeout: float,
    max_redirects: int,
    resolver: Resolver,
    transport: httpx.AsyncBaseTransport | None,
) -> FetchedPage:
    async with httpx.AsyncClient(
        transport=transport, timeout=timeout, follow_redirects=False
    ) as client:
        current = url
        for _ in range(max_redirects + 1):
            _, host, ip = await vet_url(current, resolver)
            request = _pinned_request(current, host, ip)
            try:
                response = await client.send(request, stream=True)
            except httpx.TimeoutException as exc:
                raise FetchError("The website took too long to respond.") from exc
            except httpx.HTTPError as exc:
                raise FetchError("We couldn't connect to that website.") from exc
            try:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        raise FetchError("The website sent a broken redirect.")
                    current = urljoin(current, location)
                    continue
                if response.status_code != 200:
                    raise FetchError(f"The website answered with HTTP {response.status_code}.")
                content_type = response.headers.get("content-type", "").split(";")[0].strip()
                if content_type.lower() not in ALLOWED_CONTENT_TYPES:
                    raise FetchError("That link isn't a web page (we can read HTML pages only).")
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > max_bytes:
                        raise FetchError("That page is too large to analyze.")
                text = bytes(body).decode(response.encoding or "utf-8", errors="replace")
                return FetchedPage(url=current, content_type=content_type.lower(), text=text)
            finally:
                await response.aclose()
        raise FetchError("The website redirected too many times.")
