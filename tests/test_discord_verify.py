"""Tests for Discord Ed25519 interaction signature verification."""

# pylint: disable=missing-function-docstring

from nacl.signing import SigningKey

from aws_idc_pim.discord_verify import verify_discord_signature


def _keypair():
    signing_key = SigningKey.generate()
    return signing_key, signing_key.verify_key.encode().hex()


def _sign(signing_key, timestamp, body):
    return signing_key.sign((timestamp + body).encode("utf-8")).signature.hex()


def test_valid_signature_verifies():
    signing_key, public_key_hex = _keypair()
    timestamp = "1700000000"
    body = '{"type":1}'
    signature_hex = _sign(signing_key, timestamp, body)

    assert verify_discord_signature(public_key_hex, signature_hex, timestamp, body)


def test_tampered_body_fails():
    signing_key, public_key_hex = _keypair()
    timestamp = "1700000000"
    signature_hex = _sign(signing_key, timestamp, '{"type":1}')

    assert not verify_discord_signature(
        public_key_hex, signature_hex, timestamp, '{"type":2}'
    )


def test_wrong_key_fails():
    signing_key, _ = _keypair()
    _, other_public_key_hex = _keypair()
    timestamp = "1700000000"
    body = '{"type":1}'
    signature_hex = _sign(signing_key, timestamp, body)

    assert not verify_discord_signature(
        other_public_key_hex, signature_hex, timestamp, body
    )


def test_malformed_signature_fails_cleanly():
    _, public_key_hex = _keypair()
    assert not verify_discord_signature(public_key_hex, "not-hex", "1700000000", "{}")


def test_malformed_public_key_fails_cleanly():
    assert not verify_discord_signature("not-hex", "aa", "1700000000", "{}")
