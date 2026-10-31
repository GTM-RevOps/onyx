"""HTTP client for the Onyx admin and chat APIs."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Protocol

from gtm.lib.parse import ConfigError


class Api(Protocol):
    def request(
        self,
        method: str,
        path: str,
        body: dict[str, object] | None = None,
        query: dict[str, str] | None = None,
    ) -> object:
        """Send one API call and return the decoded JSON body."""


class OnyxClient:
    """Call Onyx with an admin API key. Authorization uses Bearer."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: float,
        secrets: list[str],
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.secrets = [secret for secret in secrets if secret]

    def request(
        self,
        method: str,
        path: str,
        body: dict[str, object] | None = None,
        query: dict[str, str] | None = None,
    ) -> object:
        if not path.startswith("/"):
            raise ConfigError(f"Path must start with /: {path}")
        url = self.base_url + path
        if query:
            url = url + "?" + urllib.parse.urlencode(query)
        data: bytes | None = None
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        }
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            redacted = _redact(detail, self.secrets)[:500]
            raise ConfigError(
                f"{method} {path} failed ({error.code}): {redacted}"
            ) from None
        except urllib.error.URLError as error:
            raise ConfigError(f"{method} {path} failed: {error.reason}") from None
        if not raw:
            return None
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as error:
            raise ConfigError(f"{method} {path} returned non-JSON") from error


def _redact(text: str, secrets: list[str]) -> str:
    redacted = text
    for secret in secrets:
        redacted = redacted.replace(secret, "***")
    return redacted
