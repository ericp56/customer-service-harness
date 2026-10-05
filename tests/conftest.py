from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TypeVar

import pytest

Result = TypeVar("Result")


@pytest.fixture
def run_async():
    def run(coroutine: Coroutine[Any, Any, Result]) -> Result:
        with ThreadPoolExecutor(max_workers=1) as executor:
            return executor.submit(asyncio.run, coroutine).result()

    return run