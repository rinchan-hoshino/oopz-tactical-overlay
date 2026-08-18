import os

import pytest

from oopz_overlay.dpapi import WindowsDpapiProtector


@pytest.mark.skipif(os.name != "nt", reason="Windows DPAPI is Windows-only")
def test_windows_dpapi_round_trip_is_not_plaintext() -> None:
    protector = WindowsDpapiProtector()
    encrypted = protector.protect(b"private-oopz-session")

    assert b"private-oopz-session" not in encrypted
    assert protector.unprotect(encrypted) == b"private-oopz-session"
