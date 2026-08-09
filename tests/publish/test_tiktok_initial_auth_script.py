"""
tests/publish/test_tiktok_initial_auth_script.py

Covers scripts/tiktok_initial_auth.py: authorize-URL construction,
CSRF state save/verify, and the credential file it writes. Does not
make any real network or TikTok call -- exchange_authorization_code
is mocked throughout.
"""
import json
import os
import platform
import stat
import subprocess

import pytest

import scripts.tiktok_initial_auth as tiktok_initial_auth
from core.providers.publish.tiktok_auth import (
    TikTokAuthorizationCodeInvalid,
    TokenPair,
)


@pytest.fixture(autouse=True)
def _isolated_cwd(tmp_path, monkeypatch):
    """Every test runs with cwd inside a throwaway tmp_path, so the
    state/credentials files this script writes never touch the real
    repo directory or leak between tests."""
    monkeypatch.chdir(tmp_path)
    yield tmp_path


@pytest.fixture(autouse=True)
def _tiktok_app_env(monkeypatch):
    monkeypatch.setenv("TIKTOK_CLIENT_KEY", "real_client_key_123")
    monkeypatch.setenv("TIKTOK_CLIENT_SECRET", "real_client_secret_456")


def test_start_prints_real_redirect_uri_and_scopes_and_saves_state(capsys):
    code = tiktok_initial_auth.main(["start"])
    out = capsys.readouterr().out

    assert code == 0
    assert tiktok_initial_auth.REDIRECT_URI in out
    assert "video.publish" in out
    assert "user.info.basic" in out
    assert "video.upload" in out
    # client_key must appear (it's not a secret, it's public per OAuth) --
    # but client_secret must NEVER appear anywhere in start's output.
    assert "real_client_key_123" in out
    assert "real_client_secret_456" not in out

    assert os.path.exists(tiktok_initial_auth._STATE_PATH)
    with open(tiktok_initial_auth._STATE_PATH) as f:
        saved = json.load(f)
    assert "state" in saved and len(saved["state"]) > 10


def test_start_fails_cleanly_without_client_key(monkeypatch, capsys):
    monkeypatch.delenv("TIKTOK_CLIENT_KEY", raising=False)
    code = tiktok_initial_auth.main(["start"])
    assert code == 1
    assert not os.path.exists(tiktok_initial_auth._STATE_PATH)


def test_exchange_succeeds_writes_file_with_restricted_permissions_and_never_prints_values(capsys):
    tiktok_initial_auth.main(["start"])  # establishes state file

    fake_pair = TokenPair(access_token="act.REALVALUE", refresh_token="rft.REALVALUE",
                           expires_in=86400, open_id="oid-999")

    def fake_exchange(client_key, client_secret, code, redirect_uri, timeout=30):
        assert redirect_uri == tiktok_initial_auth.REDIRECT_URI
        assert client_key == "real_client_key_123"
        assert client_secret == "real_client_secret_456"
        assert code == "THE_CODE_FROM_CALLBACK"
        return fake_pair

    import unittest.mock as mock
    with mock.patch.object(tiktok_initial_auth, "exchange_authorization_code", fake_exchange):
        code = tiktok_initial_auth.main(["exchange", "--code", "THE_CODE_FROM_CALLBACK"])
    out = capsys.readouterr().out

    assert code == 0
    # Never print the actual secret values.
    assert "act.REALVALUE" not in out
    assert "rft.REALVALUE" not in out
    assert "real_client_secret_456" not in out

    output_path = tiktok_initial_auth._CREDENTIALS_OUTPUT_PATH
    assert os.path.exists(output_path)
    with open(output_path) as f:
        data = json.load(f)
    assert data["access_token"] == "act.REALVALUE"
    assert data["refresh_token"] == "rft.REALVALUE"
    assert data["brand_id"] == "horror_lab"

    # Permission restriction is platform-specific -- see
    # _restrict_file_permissions's docstring in the script itself for
    # why (os.chmod cannot express real per-user restriction on
    # Windows; POSIX stat bits aren't meaningful on Windows either).
    if platform.system() == "Windows":
        # Verify the REAL icacls-based ACL, not simulated stat bits --
        # this branch only executes when actually run on Windows.
        acl = subprocess.run(["icacls", output_path], capture_output=True,
                              text=True, timeout=10).stdout
        current_user = os.environ.get("USERNAME", "")
        assert current_user and current_user in acl
        for broad_group in ("Everyone", "Authenticated Users", "BUILTIN\\Users"):
            assert broad_group not in acl
    else:
        mode = stat.S_IMODE(os.stat(output_path).st_mode)
        assert not (mode & stat.S_IRWXG) and not (mode & stat.S_IRWXO)

    # State file is consumed/removed after a successful exchange.
    assert not os.path.exists(tiktok_initial_auth._STATE_PATH)


def test_exchange_without_prior_start_refuses_by_default():
    code = tiktok_initial_auth.main(["exchange", "--code", "SOMECODE"])
    assert code == 1
    assert not os.path.exists(tiktok_initial_auth._CREDENTIALS_OUTPUT_PATH)


def test_exchange_skip_state_check_bypasses_missing_state():
    fake_pair = TokenPair(access_token="a", refresh_token="r", expires_in=86400, open_id="o")
    import unittest.mock as mock
    with mock.patch.object(tiktok_initial_auth, "exchange_authorization_code",
                            return_value=fake_pair):
        code = tiktok_initial_auth.main(
            ["exchange", "--code", "SOMECODE", "--skip-state-check"]
        )
    assert code == 0
    assert os.path.exists(tiktok_initial_auth._CREDENTIALS_OUTPUT_PATH)


def test_exchange_mismatched_state_refuses():
    tiktok_initial_auth.main(["start"])
    code = tiktok_initial_auth.main(
        ["exchange", "--code", "SOMECODE", "--state", "totally-wrong-state-value"]
    )
    assert code == 1
    assert not os.path.exists(tiktok_initial_auth._CREDENTIALS_OUTPUT_PATH)


def test_exchange_invalid_code_propagates_failure_and_writes_nothing(capsys):
    tiktok_initial_auth.main(["start"])

    def failing_exchange(*args, **kwargs):
        raise TikTokAuthorizationCodeInvalid("TikTok rejected the authorization code")

    import unittest.mock as mock
    with mock.patch.object(tiktok_initial_auth, "exchange_authorization_code", failing_exchange):
        code = tiktok_initial_auth.main(["exchange", "--code", "DEAD_CODE"])
    out = capsys.readouterr().err

    assert code == 1
    assert "rejected the authorization code" in out
    assert not os.path.exists(tiktok_initial_auth._CREDENTIALS_OUTPUT_PATH)


def test_build_authorize_url_uses_documented_scopes_and_redirect():
    # Regression guard: these three literal values must always match
    # what tiktok-auth.html already uses in production, or the
    # exchange will fail with redirect_uri_mismatch / invalid scope.
    assert tiktok_initial_auth.REDIRECT_URI == "https://sweetlifeofrosee.github.io/sweetystorylab/callback"
    assert tiktok_initial_auth.SCOPES == "user.info.basic,video.upload,video.publish"


# --- _restrict_file_permissions: cross-platform credential-file protection ---
#
# Background: os.chmod(path, 0o600) genuinely restricts a file on
# POSIX, but on Windows os.chmod() can only toggle the
# FILE_ATTRIBUTE_READONLY DOS attribute -- it cannot express
# group/other permission bits at all. Calling it there silently does
# nothing to restrict access, and os.stat().st_mode afterward reports
# a synthesized 0o666 regardless (confirmed by a real run: mode 438 ==
# 0o666). _restrict_file_permissions() dispatches to a real ACL change
# (icacls) on Windows instead. The two mocked tests below can run on
# any host (including this Linux CI) because they mock
# platform.system() and subprocess.run rather than requiring an actual
# Windows machine; the third test only runs when genuinely on Windows.

@pytest.mark.skipif(platform.system() == "Windows",
                     reason="POSIX chmod semantics only apply off Windows -- "
                            "see test_restrict_file_permissions_windows_real_acl "
                            "for the Windows-native equivalent.")
def test_restrict_file_permissions_posix_sets_owner_only_bits(tmp_path):
    path = tmp_path / "creds.json"
    path.write_text("{}")
    tiktok_initial_auth._restrict_file_permissions(str(path))
    mode = stat.S_IMODE(os.stat(path).st_mode)
    assert mode == (stat.S_IRUSR | stat.S_IWUSR)


def test_restrict_file_permissions_windows_invokes_icacls_with_current_user_only(tmp_path, monkeypatch):
    """
    Mocks platform.system() to force the Windows branch regardless of
    the actual host, and mocks subprocess.run so no real icacls
    process is ever spawned -- this verifies OUR code calls icacls
    correctly, runnable on any CI including Linux.
    """
    path = str(tmp_path / "creds.json")
    monkeypatch.setenv("USERNAME", "testuser")

    import unittest.mock as mock
    with mock.patch.object(tiktok_initial_auth.platform, "system", return_value="Windows"), \
         mock.patch.object(tiktok_initial_auth.subprocess, "run") as mock_run:
        tiktok_initial_auth._restrict_file_permissions(path)

    mock_run.assert_called_once()
    called_args = mock_run.call_args.args[0]
    assert called_args[0] == "icacls"
    assert called_args[1] == path
    assert "/inheritance:r" in called_args
    assert "testuser:F" in called_args
    # Check only the actual grant-target token (before the colon in
    # "testuser:F"), not a blanket substring scan across the whole
    # command -- `path` is also an element of called_args, and on a
    # real Windows machine tmp_path resolves under C:\Users\<name>\...,
    # so "Users" legitimately appears in the path itself. Scanning
    # every arg for that substring produces a false failure that has
    # nothing to do with whether the actual ACL grant is overly broad.
    grant_arg = called_args[-1]
    assert grant_arg == "testuser:F"
    grant_target = grant_arg.split(":", 1)[0]
    assert grant_target not in ("Everyone", "Users", "Authenticated Users")


def test_restrict_file_permissions_windows_icacls_failure_warns_but_does_not_raise(tmp_path, capsys):
    """
    If icacls itself fails (missing binary, permission issue, etc.),
    the function must not raise -- the credential exchange already
    succeeded and the file is already written and gitignored; a
    protection-step failure should degrade to a loud warning, not
    crash the whole utility. _restrict_file_permissions_windows also
    only ever receives a bare path, never a secret value, so it
    cannot leak credentials regardless of how it fails.
    """
    path = str(tmp_path / "creds.json")

    import unittest.mock as mock
    with mock.patch.object(tiktok_initial_auth.platform, "system", return_value="Windows"), \
         mock.patch.object(tiktok_initial_auth.subprocess, "run",
                            side_effect=OSError("icacls not found")):
        tiktok_initial_auth._restrict_file_permissions(path)  # must not raise

    err = capsys.readouterr().err
    assert "WARNING" in err
    assert path in err


@pytest.mark.skipif(platform.system() != "Windows",
                     reason="Exercises the real Windows icacls binary -- only "
                            "meaningful and runnable on an actual Windows host.")
def test_restrict_file_permissions_windows_real_acl(tmp_path):
    path = tmp_path / "creds.json"
    path.write_text("{}")
    tiktok_initial_auth._restrict_file_permissions(str(path))

    acl = subprocess.run(["icacls", str(path)], capture_output=True, text=True, timeout=10).stdout
    current_user = os.environ.get("USERNAME", "")
    assert current_user and current_user in acl
    for broad_group in ("Everyone", "Authenticated Users", "BUILTIN\\Users"):
        assert broad_group not in acl
