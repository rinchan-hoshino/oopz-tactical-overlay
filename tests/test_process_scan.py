import ctypes
import os

import pytest

from oopz_overlay.adapters.session import _oopz_is_running


@pytest.mark.skipif(os.name != 'nt', reason='Windows process enumeration')
def test_repeated_session_polls_do_not_retain_new_native_structure_types():
    _oopz_is_running()
    before = len(ctypes._pointer_type_cache)
    for _ in range(32):
        _oopz_is_running()
    assert len(ctypes._pointer_type_cache) == before
