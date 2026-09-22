"""Canonical owned paths shared by policy, writer and future serving routes."""


class ExportPathError(ValueError):
    """A logical export path is unsafe or ambiguous."""


def validate_path(path: str, *, objects: bool = False) -> str:
    if (
        not isinstance(path, str)
        or not path
        or len(path) > 1024
        or any(char in path for char in "\\%?#:")
        or any(ord(char) < 32 or ord(char) == 127 for char in path)
        or any(part in {"", ".", ".."} for part in path.split("/"))
        or (not objects and ".objects" in path.split("/"))
    ):
        raise ExportPathError(f"Unsafe export path {path!r}; use a canonical relative path")
    return path


def site_path(path: str, hostname: str, *, objects: bool = False) -> str:
    validate_path(hostname)
    if "/" in hostname:
        raise ExportPathError("Site hostname must be one path segment")
    validate_path(path, objects=objects)
    if not path.startswith(hostname + "/"):
        raise ExportPathError("Export path must stay within its site's hostname directory")
    return path
