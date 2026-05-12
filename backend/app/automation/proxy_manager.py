"""
AutoJob AI — Proxy Manager
Handles proxy rotation, health checks, and geo-matching for browser sessions.
Supports HTTP, HTTPS, and SOCKS5 proxies.

Usage:
    manager = ProxyManager()
    proxy = manager.get_next_proxy()  # Returns Playwright proxy dict or None
"""

import logging
import random
from dataclasses import dataclass, field
from urllib.parse import urlparse

from app.config import settings

logger = logging.getLogger("autojob.proxy_manager")


@dataclass
class ProxyEntry:
    """Parsed proxy with metadata."""
    server: str           # "http://host:port" or "socks5://host:port"
    username: str | None = None
    password: str | None = None
    failures: int = 0
    uses: int = 0
    is_healthy: bool = True


class ProxyManager:
    """
    Manages a pool of proxies with rotation strategies.

    Strategies:
    - round_robin: Cycle through proxies in order
    - random: Pick a random healthy proxy each time
    - sticky: Use the same proxy until it fails, then switch
    """

    def __init__(self):
        self._proxies: list[ProxyEntry] = []
        self._current_index: int = 0
        self._sticky_proxy: ProxyEntry | None = None
        self._rotation = settings.proxy_rotation
        self._parse_proxy_list()

    def _parse_proxy_list(self) -> None:
        """Parse the comma-separated proxy list from settings."""
        raw = settings.proxy_list.strip()
        if not raw:
            logger.info("No proxies configured — running without proxy")
            return

        for proxy_str in raw.split(","):
            proxy_str = proxy_str.strip()
            if not proxy_str:
                continue

            try:
                entry = self._parse_single_proxy(proxy_str)
                self._proxies.append(entry)
            except Exception as e:
                logger.warning(f"Failed to parse proxy '{proxy_str}': {e}")

        logger.info(f"Loaded {len(self._proxies)} proxies (rotation: {self._rotation})")

    @staticmethod
    def _parse_single_proxy(proxy_str: str) -> ProxyEntry:
        """
        Parse a proxy string into a ProxyEntry.
        Supported formats:
            http://host:port
            http://user:pass@host:port
            socks5://host:port
        """
        parsed = urlparse(proxy_str)
        scheme = parsed.scheme or "http"
        host = parsed.hostname
        port = parsed.port

        if not host or not port:
            raise ValueError(f"Invalid proxy format: {proxy_str}")

        server = f"{scheme}://{host}:{port}"
        username = parsed.username
        password = parsed.password

        return ProxyEntry(
            server=server,
            username=username,
            password=password,
        )

    @property
    def has_proxies(self) -> bool:
        """Check if any proxies are configured."""
        return len(self._proxies) > 0

    @property
    def healthy_count(self) -> int:
        """Number of healthy proxies available."""
        return sum(1 for p in self._proxies if p.is_healthy)

    def get_next_proxy(self) -> dict | None:
        """
        Get the next proxy to use based on rotation strategy.
        Returns a Playwright-compatible proxy dict, or None if no proxies.

        Playwright format:
            {"server": "http://host:port", "username": "u", "password": "p"}
        """
        if not self._proxies:
            return None

        healthy = [p for p in self._proxies if p.is_healthy]
        if not healthy:
            logger.warning("All proxies are unhealthy! Resetting all to healthy.")
            for p in self._proxies:
                p.is_healthy = True
                p.failures = 0
            healthy = self._proxies

        proxy = self._select_proxy(healthy)
        if not proxy:
            return None

        proxy.uses += 1
        result = {"server": proxy.server}
        if proxy.username:
            result["username"] = proxy.username
        if proxy.password:
            result["password"] = proxy.password

        logger.debug(f"Using proxy: {proxy.server} (uses: {proxy.uses})")
        return result

    def _select_proxy(self, healthy: list[ProxyEntry]) -> ProxyEntry | None:
        """Select a proxy based on rotation strategy."""
        if self._rotation == "sticky":
            if self._sticky_proxy and self._sticky_proxy.is_healthy:
                return self._sticky_proxy
            self._sticky_proxy = healthy[0] if healthy else None
            return self._sticky_proxy

        elif self._rotation == "random":
            return random.choice(healthy) if healthy else None

        else:  # round_robin (default)
            if self._current_index >= len(healthy):
                self._current_index = 0
            proxy = healthy[self._current_index]
            self._current_index = (self._current_index + 1) % len(healthy)
            return proxy

    def report_failure(self, proxy_server: str) -> None:
        """Report a proxy failure. After 3 failures, mark as unhealthy."""
        for p in self._proxies:
            if p.server == proxy_server:
                p.failures += 1
                if p.failures >= 3:
                    p.is_healthy = False
                    logger.warning(f"Proxy {p.server} marked unhealthy after {p.failures} failures")
                    # Reset sticky proxy if it failed
                    if self._sticky_proxy == p:
                        self._sticky_proxy = None
                break

    def report_success(self, proxy_server: str) -> None:
        """Report that a proxy worked — reset failure count."""
        for p in self._proxies:
            if p.server == proxy_server:
                p.failures = 0
                p.is_healthy = True
                break

    def get_stats(self) -> dict:
        """Get proxy pool statistics."""
        return {
            "total": len(self._proxies),
            "healthy": self.healthy_count,
            "rotation": self._rotation,
            "proxies": [
                {
                    "server": p.server,
                    "healthy": p.is_healthy,
                    "uses": p.uses,
                    "failures": p.failures,
                }
                for p in self._proxies
            ],
        }


# ── Singleton Instance ──────────────────────────────
proxy_manager = ProxyManager()
