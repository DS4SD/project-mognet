from typing import Any, Optional


def _format_value(value: Any, *, max_length: Optional[int]) -> str:
    formatted = f"{value!r}"

    if max_length and len(formatted) > max_length:
        return formatted[0:max_length] + "..."

    return formatted


def format_kwargs_repr(
    args: tuple,
    kwargs: dict,
    *,
    value_max_length: Optional[int] = 64,
) -> str:
    """Utility function to create an args + kwargs representation."""

    parts = []

    for arg in args:
        parts.append(_format_value(arg, max_length=value_max_length))

    for arg_name, arg_value in kwargs.items():
        parts.append(
            f"{arg_name}={_format_value(arg_value, max_length=value_max_length)}"
        )

    return ", ".join(parts)
