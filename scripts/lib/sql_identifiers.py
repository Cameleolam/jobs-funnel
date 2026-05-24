"""SQL identifier validation for env-configured table names."""
import re

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def validate_identifier(name: str, label: str = "identifier") -> str:
    value = str(name or "")
    if not _IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"Invalid {label}: {value!r}")
    return value
