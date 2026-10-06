"""Recognition selections shared by the desktop and task protocol."""

PACK_SCOPES = ("resources", "kubejs", "patchouli")
SCOPES = (*PACK_SCOPES, "mods")


def recognition_scopes(value):
    """Accept legacy single selections and canonicalize multiple selections."""
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list) or not value or any(not isinstance(v, str) for v in value):
        raise ValueError("识别范围至少选择一项")
    if set(value) - {"all", *SCOPES}:
        raise ValueError("识别范围无效")
    selected = set(value)
    if "all" in selected:
        selected.update(PACK_SCOPES)
    return [scope for scope in SCOPES if scope in selected]
