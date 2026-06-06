# =============================================================================
# conftest.py — Shared pytest configuration for SponsorShield
#
# Place this file at the project root so pytest discovers it automatically
# for both tests/direct/ and tests/integration/ suites.
#
# Docs: https://docs.pytest.org/en/stable/reference/fixtures.html#conftest-py
# =============================================================================

import pytest


def pytest_configure(config):
    """
    Register custom markers so pytest does not warn about unknown marks.
    Usage in tests:
        @pytest.mark.direct       — in-memory, no infra
        @pytest.mark.integration  — requires `genlayer up` (Studio simulator)
        @pytest.mark.slow         — long-running tests, skip with -m "not slow"
    """
    config.addinivalue_line("markers", "direct: fast in-memory direct-mode tests")
    config.addinivalue_line("markers", "integration: requires GenLayer simulator")
    config.addinivalue_line("markers", "slow: tests that take > 5 s")


def pytest_collection_modifyitems(config, items):
    """
    Auto-apply the `direct` marker to every test inside tests/direct/ and
    the `integration` marker to every test inside tests/integration/ so you
    can filter with:
        pytest -m direct         # unit tests only
        pytest -m integration    # simulator tests only
    """
    for item in items:
        if "tests/direct" in str(item.fspath) or "tests\\direct" in str(item.fspath):
            item.add_marker(pytest.mark.direct)
        elif "tests/integration" in str(item.fspath) or "tests\\integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
