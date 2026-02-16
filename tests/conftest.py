"""Pytest configuration and shared fixtures."""


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers",
        "integration: marks tests as integration tests (require network, external services)",
    )
    config.addinivalue_line(
        "markers",
        "credentials: marks tests that require google-credentials.json",
    )
