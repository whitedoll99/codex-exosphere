def first_normalized(items: list[str]) -> str:
    if not items:
        return ""
    return items[0].strip().lower()
