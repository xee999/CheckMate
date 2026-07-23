"""Test Google OAuth 2.0 flow for Gemini API access.

Usage:
  1. Set up a Google Cloud project, enable Generative Language API
  2. Create OAuth 2.0 Desktop credentials → copy Client ID + Secret
  3. pip install google-auth-oauthlib httpx
  4. python test_oauth.py
"""

import json
import logging
import os
import socket
import threading
import webbrowser
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("test_oauth")

# ── Config ──────────────────────────────────────────────────────────

SCOPE = "https://www.googleapis.com/auth/generative-language.retriever"
CLIENT_SECRETS_PATH = Path.home() / ".bod" / "oauth_client_secret.json"
TOKEN_PATH = Path.home() / ".bod" / "oauth_token.json"

# Gemini OpenAI-compatible endpoint
GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
TEST_MODEL = "gemini-2.0-flash"


# ── OAuth Flow ──────────────────────────────────────────────────────

def load_client_secrets() -> dict:
    if CLIENT_SECRETS_PATH.exists():
        with open(CLIENT_SECRETS_PATH) as f:
            return json.load(f)
    return {}


def save_client_secrets(data: dict):
    CLIENT_SECRETS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CLIENT_SECRETS_PATH, "w") as f:
        json.dump(data, f, indent=2)


def load_token() -> dict | None:
    if TOKEN_PATH.exists():
        with open(TOKEN_PATH) as f:
            return json.load(f)
    return None


def save_token(token: dict):
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(TOKEN_PATH, "w") as f:
        json.dump(token, f, indent=2)


def run_oauth_flow(client_id: str, client_secret: str) -> dict:
    """Run the full OAuth 2.0 authorization flow using localhost redirect."""

    from google_auth_oauthlib.flow import InstalledAppFlow

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }

    flow = InstalledAppFlow.from_client_config(
        client_config, scopes=[SCOPE]
    )

    token = flow.run_local_server(
        port=8088,
        prompt="consent",
        open_browser=True,
    )

    return {
        "access_token": token.token,
        "refresh_token": token.refresh_token,
        "expiry": token.expiry.isoformat() if token.expiry else None,
        "scope": " ".join(token.scopes) if token.scopes else SCOPE,
    }


def refresh_access_token(client_id: str, client_secret: str, refresh_token: str) -> dict:
    """Use the refresh token to get a new access token."""
    resp = httpx.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
    )
    resp.raise_for_status()
    return resp.json()


def test_gemini_call(access_token: str) -> bool:
    """Make a test call to the Gemini API via the OpenAI-compatible endpoint."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": TEST_MODEL,
        "messages": [
            {"role": "user", "content": "Say 'Gemini OAuth works' in exactly two words."}
        ],
        "max_tokens": 20,
        "temperature": 0.1,
    }

    log(f"Calling: POST {GEMINI_ENDPOINT}")
    log(f"Model: {TEST_MODEL}")
    log(f"Payload: {json.dumps(payload)}")
    log("")

    resp = httpx.post(GEMINI_ENDPOINT, headers=headers, json=payload, timeout=30)
    log(f"HTTP {resp.status_code}")

    if resp.status_code == 200:
        data = resp.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        log(f"Response: {content.strip()!r}")
        log("\n✅ Gemini OAuth works! Token is valid.")
        return True
    else:
        log(f"Error body: {resp.text[:500]}")
        log("\n❌ Gemini OAuth failed.")
        return False


# ── Main ────────────────────────────────────────────────────────────

def main():
    print("")
    print("╔══════════════════════════════════════════════════════════╗")
    print("║       Bod — Google OAuth / Gemini API Test             ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print("")

    secrets = load_client_secrets()
    token = load_token()

    if not secrets:
        print("First-time setup needed.")
        print("1. Go to https://console.cloud.google.com")
        print("2. Create a project → enable Generative Language API")
        print("3. APIs & Services → Credentials → Create OAuth Desktop Client ID")
        print("")
        client_id = input("Paste Client ID: ").strip()
        client_secret = input("Paste Client Secret: ").strip()
        if not client_id or not client_secret:
            print("Aborted.")
            return
        secrets = {"client_id": client_id, "client_secret": client_secret}
        save_client_secrets(secrets)
        print("Client secrets saved to ~/.bod/oauth_client_secret.json")
    else:
        print(f"Using saved client: {secrets['client_id'][:20]}...")
        client_id = secrets["client_id"]
        client_secret = secrets["client_secret"]

    if token and token.get("refresh_token"):
        print(f"\nSaved token found (expiry: {token.get('expiry', 'unknown')})")
        use_saved = input("Use saved token? (y/N): ").strip().lower()
        if use_saved == "y":
            print("\nRefreshing access token...")
            try:
                new_token = refresh_access_token(
                    client_id, client_secret, token["refresh_token"]
                )
                access_token = new_token.get("access_token")
                if not access_token:
                    print("Refresh returned no access token, re-authing...")
                    raise ValueError("no access token")
                print("Token refreshed.")
            except Exception as e:
                print(f"Refresh failed: {e}")
                access_token = None
        else:
            access_token = None
    else:
        access_token = None

    if not access_token:
        print("\nOpening browser for Google sign-in...")
        try:
            token_data = run_oauth_flow(client_id, client_secret)
        except ImportError:
            print("\nNeed google-auth-oauthlib. Installing...")
            os.system("pip install google-auth-oauthlib")
            try:
                token_data = run_oauth_flow(client_id, client_secret)
            except Exception as e:
                print(f"OAuth flow failed: {e}")
                return
        except Exception as e:
            print(f"OAuth flow failed: {e}")
            return

        save_token(token_data)
        print(f"Token saved to ~/.bod/oauth_token.json")
        print(f"  Expiry: {token_data.get('expiry')}")
        access_token = token_data.get("access_token")

    if not access_token:
        print("No access token available. Aborting.")
        return

    print("")
    print("─" * 50)
    print("Testing Gemini API call...")
    print("─" * 50)
    print("")

    success = test_gemini_call(access_token)

    if success:
        print("\nThis OAuth approach is confirmed working.")
    else:
        print("\nThe approach failed. Check the error above.")


if __name__ == "__main__":
    main()
