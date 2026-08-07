"""
scripts/persist_tiktok_credentials.py

The consumer side of the handoff run_brand() writes to
(.tiktok_refreshed_credentials.json, or whatever
TIKTOK_REFRESHED_CREDENTIALS_PATH points to -- see
core/pipeline/run.py's _persist_refreshed_tiktok_credentials). This
script is intentionally NOT part of core/ -- it is GitHub-Actions-
specific mechanics, kept separate on purpose from tiktok_auth.py and
tiktok_provider.py, which know nothing about where credentials are
stored (see those modules' docstrings for that boundary).

What this does, in order, matching the four steps agreed:
  1. Read the handoff file. If it doesn't exist, this is a no-op --
     that's the normal case for a dry run, a facebook-platform run, or
     any run where TikTokProvider never reached a successful refresh.
  2. Update the two GitHub Actions repository secrets (access_token,
     refresh_token) via GitHub's REST API, sealed-box encrypted per
     secret as required. See ATOMICITY NOTE below for what "atomic"
     actually means here.
  3. Delete the handoff file -- but ONLY after both secret writes
     succeed. If either write fails, the file is left in place
     deliberately, so a re-run of this step (or manual inspection)
     isn't working from data that's already been thrown away.
  4. Exit 0 on success or no-op. Exit 1 on failure, so the workflow
     step is visibly red in the Actions UI -- see the suggested
     workflow wiring at the bottom of this file for how to let the
     rest of the job continue anyway.

ATOMICITY NOTE: GitHub's secrets API has no multi-key transaction --
each secret is a separate PUT call. True atomicity across two
independent HTTP calls isn't achievable here, and this script doesn't
pretend otherwise. What it does instead: write refresh_token FIRST
(it's the one that actually gates the next scheduled run's ability to
auth at all -- access_token is re-derived fresh from refresh_token on
every publish() call and is never read back from secrets, see
TikTokProvider's docstring), then access_token. If the second write
fails after the first succeeded, this is reported as a distinct,
loud failure mode (not silently swallowed) -- the pipeline will still
work next run since refresh_token is already persisted, but
access_token's secret value is now stale for anyone using it for
manual inspection/debugging, and that's surfaced explicitly rather
than hidden.

REQUIRED ENV VARS:
  GH_SECRETS_PAT      Fine-grained PAT scoped to ONLY "Secrets: write"
                       on this repo. Deliberately not GITHUB_TOKEN --
                       the default Actions token cannot manage repo
                       secrets, this needs its own credential.
  GITHUB_REPOSITORY   "owner/repo" -- set automatically by GitHub
                       Actions; only needs setting manually for local
                       testing.
"""
import json
import os
import sys

import requests
from nacl import encoding, public

_API_BASE = "https://api.github.com"


class PersistError(Exception):
    """Raised for a failure this script should report distinctly (see
    module docstring's ATOMICITY NOTE) rather than a generic crash."""


def main() -> int:
    handoff_path = os.environ.get(
        "TIKTOK_REFRESHED_CREDENTIALS_PATH",
        ".tiktok_refreshed_credentials.json",
    )

    if not os.path.exists(handoff_path):
        print(f"No handoff file at {handoff_path} -- nothing to persist "
              f"this run (expected for a dry run, facebook-platform run, "
              f"or a run where TikTok publish never reached a successful "
              f"refresh). Continuing.")
        return 0

    pat = os.environ.get("GH_SECRETS_PAT")
    if not pat:
        print("GH_SECRETS_PAT is not set -- cannot update repo secrets. "
              "Leaving the handoff file in place (NOT deleting it) so "
              "the refreshed credentials aren't lost.", file=sys.stderr)
        return 1

    repo = os.environ.get("GITHUB_REPOSITORY")
    if not repo:
        print("GITHUB_REPOSITORY is not set -- cannot determine which "
              "repo's secrets to update. Leaving the handoff file in "
              "place.", file=sys.stderr)
        return 1

    with open(handoff_path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    missing = [k for k in ("brand_id", "access_token", "refresh_token") if k not in payload]
    if missing:
        print(f"Handoff file {handoff_path} is missing expected field(s) "
              f"{missing} -- refusing to guess. Leaving the file in "
              f"place for inspection.", file=sys.stderr)
        return 1

    try:
        refresh_secret_name, access_secret_name = _secret_names_for_brand(payload["brand_id"])
    except PersistError as e:
        print(f"Could not determine secret names: {e}. Leaving the "
              f"handoff file in place.", file=sys.stderr)
        return 1

    try:
        public_key_id, public_key_value = _get_repo_public_key(repo, pat)

        # refresh_token FIRST -- see ATOMICITY NOTE.
        _put_secret(repo, pat, refresh_secret_name, payload["refresh_token"],
                    public_key_id, public_key_value)
        print(f"Updated secret {refresh_secret_name}.")

        try:
            _put_secret(repo, pat, access_secret_name, payload["access_token"],
                        public_key_id, public_key_value)
            print(f"Updated secret {access_secret_name}.")
        except Exception as e:
            # refresh_token (the one that matters for the next run's
            # auth) is already safely persisted at this point -- this
            # failure is real but not pipeline-breaking. Reported
            # distinctly, not swallowed, per the module docstring.
            print(
                f"WARNING: {refresh_secret_name} was updated successfully, "
                f"but updating {access_secret_name} failed: {e}. The "
                f"pipeline's next run is NOT at risk (it never reads "
                f"access_token back from secrets), but that secret's "
                f"value is now stale for manual inspection. Handoff file "
                f"left in place for retry/inspection rather than deleted.",
                file=sys.stderr,
            )
            return 1

    except Exception as e:
        print(f"Failed to update {refresh_secret_name}: {e}. Nothing was "
              f"persisted. Handoff file left in place.", file=sys.stderr)
        return 1

    os.remove(handoff_path)
    print(f"Both secrets updated successfully. Deleted {handoff_path}.")
    return 0


def _secret_names_for_brand(brand_id: str) -> tuple:
    """
    Derives the two secret names from the brand's config.yaml --
    refresh_token_env is already the established source of truth
    (see core/config/loader.py / brands/<brand>/config.yaml), so this
    reads it directly rather than inventing a second naming
    convention. access_token has no config field of its own (it's
    never read back into the pipeline -- see TikTokProvider's
    docstring) but is still persisted for observability, under the
    same name with ACCESS_TOKEN substituted for REFRESH_TOKEN.
    """
    import yaml  # local import: only needed on this path

    config_path = os.path.join("brands", brand_id, "config.yaml")
    if not os.path.exists(config_path):
        raise PersistError(f"{config_path} does not exist")

    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    refresh_env = raw.get("tiktok", {}).get("refresh_token_env")
    if not refresh_env:
        raise PersistError(
            f"{config_path} has no tiktok.refresh_token_env -- can't "
            f"determine which secret to update"
        )
    if "REFRESH_TOKEN" not in refresh_env:
        raise PersistError(
            f"tiktok.refresh_token_env ({refresh_env!r}) doesn't contain "
            f"'REFRESH_TOKEN' -- refusing to guess the access_token "
            f"secret's name from it"
        )

    access_env = refresh_env.replace("REFRESH_TOKEN", "ACCESS_TOKEN")
    return refresh_env, access_env


def _get_repo_public_key(repo: str, pat: str) -> tuple:
    resp = requests.get(
        f"{_API_BASE}/repos/{repo}/actions/secrets/public-key",
        headers=_headers(pat),
        timeout=30,
    )
    resp.raise_for_status()
    body = resp.json()
    return body["key_id"], body["key"]


def _put_secret(repo: str, pat: str, secret_name: str, secret_value: str,
                 public_key_id: str, public_key_value: str) -> None:
    encrypted_value = _seal(secret_value, public_key_value)
    resp = requests.put(
        f"{_API_BASE}/repos/{repo}/actions/secrets/{secret_name}",
        headers=_headers(pat),
        json={"encrypted_value": encrypted_value, "key_id": public_key_id},
        timeout=30,
    )
    resp.raise_for_status()


def _seal(secret_value: str, public_key_b64: str) -> str:
    """Libsodium sealed-box encryption, as required by GitHub's
    'Create or update a repository secret' endpoint."""
    public_key = public.PublicKey(public_key_b64.encode("utf-8"), encoding.Base64Encoder())
    sealed_box = public.SealedBox(public_key)
    encrypted = sealed_box.encrypt(secret_value.encode("utf-8"))
    return encoding.Base64Encoder().encode(encrypted).decode("utf-8")


def _headers(pat: str) -> dict:
    return {
        "Authorization": f"Bearer {pat}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


if __name__ == "__main__":
    sys.exit(main())


# Suggested workflow wiring (see .github/workflows/post_tiktok.yml for
# the real version) -- shown here so this script's contract is legible
# without cross-referencing the yaml:
#
#   - name: Run TikTok reels bot
#     env:
#       ...
#     run: python -m core.pipeline.cli --brand horror_lab --platform tiktok
#
#   - name: Persist refreshed TikTok credentials
#     if: always()   # run even if the publish step above exited 2
#                     # (publish failed) -- a refresh can succeed even
#                     # when the publish call after it fails, and that
#                     # refreshed pair still needs saving (see
#                     # TikTokProvider's docstring on refreshed_credentials
#                     # being returned even on downstream failure).
#     continue-on-error: true   # a failure here is reported (exit 1,
#                     # printed WARNING/error) but shouldn't fail the
#                     # whole job -- the video was already
#                     # generated/published by the previous step
#                     # regardless of this step's outcome.
#     env:
#       GH_SECRETS_PAT: ${{ secrets.GH_SECRETS_PAT }}
#     run: python scripts/persist_tiktok_credentials.py
