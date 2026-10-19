"""A site-profile module for tests/test_profile.py."""

READY_CALLS = []


def ready():
    READY_CALLS.append(True)
