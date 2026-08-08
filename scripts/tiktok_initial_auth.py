"""
scripts/tiktok_initial_auth.py

ONE-TIME, LOCAL, MANUAL utility for the initial TikTok OAuth
authorization-code exchange -- the step that produces the very first
(access_token, refresh_token) pair for an account, before any
scheduled run exists to refresh it.

Deliberately NOT part of core/pipeline/ and NOT invoked by any
scheduled workflow -- run this yourself, once, on your own machine (or
here in the sandbox), whenever an account needs (re-)connecting from
scratch. TikTokProvider, run_brand(), cli.py, and post_tiktok.yml are
all completely unaware this script exists.

WHY THIS IS SEPARATE FROM tiktok_auth.py's refresh_access_token():
that function needs a refresh_token to already exist. This script's
whole purpose is producing the refresh_token that doesn't exist yet.
It reuses TokenPair and the new exchange_authorization_code() from
tiktok_auth.py (same module, same TokenPair shape, same TikTok
endpoint) but nothing about the scheduled refresh path changes because
this script exists.

WHY callback.html IS NOT INVOLVED: that GitHub Pages page is a static
UI mockup with no backend -- it never performed a real token exchange
and isn't being made to now (see the repo audit that established
this). This script does the real exchange itself, locally. You'll
still be redirected through TikTok to that page as the OAuth
redirect_uri (TikTok requires *a* URL to redirect to, and it must
match what's registered on the TikTok Developer Portal) -- but once
there, you're not clicking anything on that page. You're reading the
`code` value out of your browser's address bar and pasting it into
this script's `exchange` command.

USAGE:
  1. export TIKTOK_CLIENT_KEY=...      (real app values, not TikTok's
     export TIKTOK_CLIENT_SECRET=...    sandbox demo key from
                                         tiktok-auth.html)
  2. python scripts/tiktok_initial_auth.py start
     -> prints the real TikTok authorize URL. Open it in a browser,
        log in as the account to connect, approve the requested
        scopes.
  3. TikTok redirects your browser to callback.html?code=XXXX&state=YYYY
     -- the page itself does nothing useful (see above); just copy the
     `code` value out of the address bar.
  4. python scripts/tiktok_initial_auth.py exchange --code XXXX
     -> exchanges the code for the real TokenPair, writes it to a
        local file (0600 permissions, gitignored), and tells you
        where. Nothing is ever printed to the terminal.
  5. Open that file yourself, copy `refresh_token` into GitHub
     Secrets as HORROR_LAB_TIKTOK_REFRESH_TOKEN, then delete the file.

SECURITY: this script never prints client_secret, access_token, or
refresh_token -- not even partially, not even masked. The only place
those values ever land is the local output file, which you're
responsible for deleting once you've copied refresh_token into GitHub
Secrets.
"""
import argparse
import json
import os
import stat
import sys
from urllib.parse import urlencode

from core.config import platform as platform_config
from core.providers.publish.tiktok_auth import (
    exchange_authorization_code,
    TikTokAuthorizationCodeInvalid,
    TikTokAuthNetworkError,
)

# Must be BYTE-FOR-BYTE identical to what's registered on the TikTok
# Developer Portal and to what tiktok-auth.html already uses --
# confirmed by reading that file directly rather than guessing. Not
# an env var: this is Horror Lab's one registered Web Login Kit
# redirect, not something that should vary per invocation.
REDIRECT_URI = "https://sweetlifeofrosee.github.io/sweetystorylab/callback"

# Same three scopes already requested by tiktok-auth.html (confirmed
# by reading that file), video.publish included as required.
SCOPES = "user.info.basic,video.upload,video.publish"

_AUTHORIZE_URL = "https://www.tiktok.com/v2/auth/authorize/"

_STATE_PATH = ".tiktok_oauth_state.json"
_CREDENTIALS_OUTPUT_PATH = ".tiktok_initial_credentials.json"


def cmd_start(args) -> int:
    client_key = platform_config.get_tiktok_client_key()
    if not client_key:
        print("TIKTOK_CLIENT_KEY is not set. Export the real app client "
              "key (not tiktok-auth.html's hardcoded sandbox demo key) "
              "and try again.", file=sys.stderr)
        return 1

    import secrets as _secrets  # stdlib, unrelated to core.config -- local import to avoid any name confusion with the module-level `code` concept elsewhere
    state = _secrets.token_urlsafe(16)

    # state is a CSRF nonce, not a secret -- safe to persist in plain
    # text and safe to print. It only proves the callback that comes
    # back is responding to a request THIS script made, nothing more.
    with open(_STATE_PATH, "w", encoding="utf-8") as f:
        json.dump({"state": state}, f)

    query = urlencode({
        "client_key": client_key,
        "scope": SCOPES,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "state": state,
    })
    auth_url = f"{_AUTHORIZE_URL}?{query}"

    print("Open this URL in a browser, log in as the TikTok account to "
          "connect, and approve the requested scopes:\n")
    print(auth_url)
    print(f"\nAfter approving, TikTok will redirect to:\n"
          f"  {REDIRECT_URI}?code=...&state={state}\n"
          f"That page (callback.html) does nothing useful -- it's a "
          f"static mockup, not a real backend. Just copy the `code` "
          f"value from your browser's address bar, then run:\n\n"
          f"  python scripts/tiktok_initial_auth.py exchange --code <CODE>")
    return 0


def cmd_exchange(args) -> int:
    client_key = platform_config.get_tiktok_client_key()
    client_secret = platform_config.get_tiktok_client_secret()
    if not client_key or not client_secret:
        print("TIKTOK_CLIENT_KEY and/or TIKTOK_CLIENT_SECRET are not "
              "set.", file=sys.stderr)
        return 1

    if not args.skip_state_check:
        expected_state = _read_saved_state()
        if expected_state is None:
            print(f"No saved state found at {_STATE_PATH} (did you run "
                  f"`start` first, in this same directory?). Pass "
                  f"--skip-state-check to bypass this if you're certain "
                  f"the code is legitimate.", file=sys.stderr)
            return 1
        if args.state and args.state != expected_state:
            print("The --state you passed does not match the state "
                  "saved during `start` -- this could mean the code "
                  "you have isn't from a request this script made. "
                  "Refusing to proceed. Re-run `start` for a fresh "
                  "request, or pass --skip-state-check if you're "
                  "certain this is fine.", file=sys.stderr)
            return 1

    try:
        token_pair = exchange_authorization_code(
            client_key=client_key,
            client_secret=client_secret,
            code=args.code,
            redirect_uri=REDIRECT_URI,
        )
    except TikTokAuthorizationCodeInvalid as e:
        print(f"Exchange failed: {e}", file=sys.stderr)
        return 1
    except TikTokAuthNetworkError as e:
        print(f"Exchange failed (network/response issue, may be worth "
              f"retrying): {e}", file=sys.stderr)
        return 1

    output_path = args.output or _CREDENTIALS_OUTPUT_PATH
    payload = {
        "brand_id": "horror_lab",
        "access_token": token_pair.access_token,
        "refresh_token": token_pair.refresh_token,
        "expires_in": token_pair.expires_in,
        "open_id": token_pair.open_id,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    # 0600: owner read/write only. Best-effort -- some filesystems
    # (e.g. certain CI/sandbox mounts) may not honor this, which is
    # exactly why the file is also gitignored and this script prints
    # an explicit reminder to delete it below regardless.
    try:
        os.chmod(output_path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass

    if os.path.exists(_STATE_PATH):
        os.remove(_STATE_PATH)

    # Never print the values themselves -- only field names and the
    # file path, matching the same discipline used everywhere else in
    # this repo's TikTok credential handling.
    print(f"Exchange succeeded. Wrote {list(payload.keys())} to "
          f"{output_path} (permissions restricted to your user where "
          f"supported).")
    print(f"\nNext steps:")
    print(f"  1. Open {output_path} yourself and copy the "
          f"`refresh_token` value.")
    print(f"  2. Add it to GitHub Secrets as "
          f"HORROR_LAB_TIKTOK_REFRESH_TOKEN (Settings -> Secrets and "
          f"variables -> Actions -> New repository secret).")
    print(f"  3. Delete {output_path} -- it is gitignored but still "
          f"sitting in plaintext on this machine until you remove it.")
    return 0


def _read_saved_state():
    if not os.path.exists(_STATE_PATH):
        return None
    try:
        with open(_STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f).get("state")
    except (json.JSONDecodeError, OSError):
        return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="One-time local TikTok OAuth authorization-code exchange."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    start = sub.add_parser("start", help="Print the TikTok authorize URL to open in a browser.")
    start.set_defaults(func=cmd_start)

    exchange = sub.add_parser("exchange", help="Exchange a code for the initial TokenPair.")
    exchange.add_argument("--code", required=True, help="The `code` param from the callback redirect.")
    exchange.add_argument("--state", default=None,
                           help="Optional: the `state` param from the callback redirect, "
                                "verified against what `start` saved.")
    exchange.add_argument("--skip-state-check", action="store_true",
                           help="Bypass CSRF state verification (not recommended).")
    exchange.add_argument("--output", default=None,
                           help=f"Where to write the credentials (default: {_CREDENTIALS_OUTPUT_PATH}).")
    exchange.set_defaults(func=cmd_exchange)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
