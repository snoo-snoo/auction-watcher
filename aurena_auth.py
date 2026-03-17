"""
Aurena authentication module.
Handles login via GraphQL and provides an authenticated session.

Credentials are base64-encoded before sending (required by aurena API).
"""

import base64
import sys
import uuid
import time
import requests

AURENA_GQL = "https://webplatform-facade.cluster.prod.aurena.services/api/graphql"
AURENA_API = "https://webplatform-facade.cluster.prod.aurena.services/api/v1"
AURENA_EMAIL = "hi@ypr.at"
AURENA_PASSWORD = "chBX@Du%9z,f4@!"

_GQL_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:148.0) Gecko/20100101 Firefox/148.0",
    "Accept": "*/*",
    "Content-Type": "application/json",
    "Aurena-Auction-Room": "www.aurena.at",
    "Origin": "https://www.aurena.at",
    "Referer": "https://www.aurena.at/",
}

_LOGIN_MUTATION = """
mutation login($email: String!, $password: String!, $deviceId: String!) {
  login(email: $email, password: $password, deviceId: $deviceId) {
    authToken
    authenticated
  }
}
"""

# Cached token (expires after ~1h)
_token_cache: dict = {"token": None, "expires_at": 0}
_device_id = str(uuid.uuid4())


def get_auth_token() -> str | None:
    """
    Return a valid auth token, refreshing if expired.
    Returns None on failure.
    """
    now = time.time()
    if _token_cache["token"] and now < _token_cache["expires_at"]:
        return _token_cache["token"]

    try:
        resp = requests.post(
            AURENA_GQL,
            json={
                "query": _LOGIN_MUTATION,
                "variables": {
                    "email": base64.b64encode(AURENA_EMAIL.encode()).decode(),
                    "password": base64.b64encode(AURENA_PASSWORD.encode()).decode(),
                    "deviceId": _device_id,
                },
            },
            headers=_GQL_HEADERS,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        login = data.get("data", {}).get("login", {})
        token = login.get("authToken")
        if token and login.get("authenticated"):
            _token_cache["token"] = token
            _token_cache["expires_at"] = now + 3500  # ~1h
            return token
        else:
            print("[aurena] Login failed: not authenticated", file=sys.stderr)
            return None
    except Exception as e:
        print(f"[aurena] Login error: {e}", file=sys.stderr)
        return None


def get_api_headers() -> dict:
    """Return headers for authenticated API requests."""
    token = get_auth_token()
    h = {
        "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:148.0) Gecko/20100101 Firefox/148.0",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Aurena-Auction-Room": "www.aurena.at",
        "Origin": "https://www.aurena.at",
    }
    if token:
        h["Authorization"] = token
    return h


def fetch_all_auctions() -> list[dict]:
    """
    Fetch all active auctions via authenticated API (package 180210963).
    Returns list of auction dicts with id, title, location, timeInfo, etc.
    """
    headers = get_api_headers()
    try:
        resp = requests.post(
            f"{AURENA_API}/package/180210963",
            json={},
            headers=headers,
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("items", [])
    except Exception as e:
        print(f"[aurena] Error fetching auctions: {e}", file=sys.stderr)
        return []
