"""Small command-line interface fixture."""

DEFAULT_LIMIT = 100


def parse_limit(raw: str | None) -> int:
    """Parse the optional limit supplied by a command-line caller."""
    if raw is None:
        return DEFAULT_LIMIT
    if raw == "":
        return 0
    return int(raw)
