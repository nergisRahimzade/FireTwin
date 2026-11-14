"""Backend settings read from environment variables (BE-05).

Later tasks add their own settings here (MOCK_MODE in BE-06; detector and trust thresholds in
BE-03/ML-04). Read them with get_settings(); never call os.getenv() elsewhere in the backend.
"""

import os
from dataclasses import dataclass
from urllib.parse import urlsplit

from pydantic import AnyHttpUrl

# The Vite dev server (FE-01) runs on port 5173; browsers may use either host name for it.
DEFAULT_CORS_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"


def _parse_origin(origin: str) -> str:
    """Require an explicit HTTP(S) origin, with no credentials or URL suffix."""
    try:
        parsed = urlsplit(origin)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or any(character.isspace() for character in origin)
            or any(character in origin for character in "\\?#*")
            or parsed.path
            or parsed.netloc.endswith(":")
            or parsed.port == 0  # Access also rejects malformed or out-of-range ports.
        ):
            raise ValueError
        # Match browser Origin serialization (host case, default ports, IDNs, IPv6).
        url = AnyHttpUrl(origin)
        if url.host and not url.host.startswith("[") and not _host_labels_ok(url.host):
            raise ValueError
        return str(url).removesuffix("/")
    except ValueError:
        # Name the bad entry (origins aren't secret), so a long list is easy to fix.
        raise ValueError(
            f"CORS_ORIGINS entry {origin!r} is not an explicit http(s) origin "
            "(no credentials, paths, queries, fragments, or wildcards)"
        ) from None


def _host_labels_ok(host: str) -> bool:
    # Browsers never send a host with an empty part ("a..test", "localhost.") or a part that starts
    # or ends with "-"; such an origin could never match a request, so reject it loudly instead.
    return all(
        label and not label.startswith("-") and not label.endswith("-") for label in host.split(".")
    )


# frozen=True: a setting can't be changed by accident while the app runs.
@dataclass(frozen=True)
class Settings:
    # Web pages allowed to call the API from a browser (CORS). A tuple, so it can't be edited.
    cors_origins: tuple[str, ...]


def get_settings() -> Settings:
    """Build Settings from the environment.

    Reads os.getenv fresh on every call, so tests can change values with monkeypatch.
    """
    # Comma-separated list, e.g. "http://localhost:5173,http://example.com".
    raw = os.getenv("CORS_ORIGINS", DEFAULT_CORS_ORIGINS)
    origins = tuple(origin.strip() for origin in raw.split(",") if origin.strip())
    # Fail loudly: an empty list would silently block the frontend from calling the API.
    if not origins:
        raise ValueError("CORS_ORIGINS must list at least one origin")
    return Settings(cors_origins=tuple(_parse_origin(origin) for origin in origins))
