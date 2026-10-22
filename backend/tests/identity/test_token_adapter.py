from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import jwt
import pytest

from src.core.exceptions.exceptions import UnauthorizedError
from src.modules.identity.keys import load_signing_keys
from src.modules.identity.token_adapter import TokenAdapter


def make_adapter(tmp_path: Path, name: str = "a", ttl: timedelta = timedelta(minutes=5), **kw):
    keys = load_signing_keys(tmp_path / f"{name}.pem", tmp_path / f"{name}.pub.pem", generate=True)
    return TokenAdapter(
        keys,
        issuer=kw.get("issuer", "identity"),
        audience=kw.get("audience", "credit-cabinet"),
        ttl=ttl,
    )


def test_roundtrip(tmp_path: Path) -> None:
    adapter = make_adapter(tmp_path)
    subject = uuid4()
    issued = adapter.issue(subject, ["requests.read"], {"requests.read": ["own_only"]})

    decoded = adapter.decode(issued.access_token)

    assert decoded.subject == subject
    assert decoded.permissions == ["requests.read"]
    assert decoded.policies == {"requests.read": ["own_only"]}
    assert issued.expires_in == 300


def test_header_carries_kid(tmp_path: Path) -> None:
    adapter = make_adapter(tmp_path)
    issued = adapter.issue(uuid4(), [], {})
    header = jwt.get_unverified_header(issued.access_token)
    assert header["alg"] == "RS256"
    assert header["kid"] == adapter.jwks()["keys"][0]["kid"]


def test_keys_are_reused_between_starts(tmp_path: Path) -> None:
    first = make_adapter(tmp_path)
    second = make_adapter(tmp_path)
    assert second.decode(first.issue(uuid4(), [], {}).access_token)


def test_expired_token_is_rejected(tmp_path: Path) -> None:
    adapter = make_adapter(tmp_path, ttl=timedelta(seconds=-1))
    with pytest.raises(UnauthorizedError, match="expired"):
        adapter.decode(adapter.issue(uuid4(), [], {}).access_token)


def test_token_signed_by_another_key_is_rejected(tmp_path: Path) -> None:
    stranger = make_adapter(tmp_path, name="stranger")
    with pytest.raises(UnauthorizedError):
        make_adapter(tmp_path).decode(stranger.issue(uuid4(), [], {}).access_token)


def test_wrong_audience_is_rejected(tmp_path: Path) -> None:
    other = make_adapter(tmp_path, audience="someone-else")
    with pytest.raises(UnauthorizedError):
        make_adapter(tmp_path).decode(other.issue(uuid4(), [], {}).access_token)


def test_unsigned_token_is_rejected(tmp_path: Path) -> None:
    adapter = make_adapter(tmp_path)
    issued = adapter.issue(uuid4(), [], {})
    claims = jwt.decode(issued.access_token, options={"verify_signature": False})
    claims["permissions"] = ["admin"]
    forged = jwt.encode(claims, None, algorithm="none")
    with pytest.raises(UnauthorizedError):
        adapter.decode(forged)


def test_missing_key_without_generation_fails(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError):
        load_signing_keys(tmp_path / "none.pem", tmp_path / "none.pub.pem", generate=False)
