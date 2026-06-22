"""Shared Jinja2Templates instance for the FastAPI harness UI."""
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import jinja2
from fastapi.templating import Jinja2Templates
from jinja2.utils import pass_context

_UI_ROOT = Path(__file__).parent

templates = Jinja2Templates(
    directory=[
        str(_UI_ROOT / "templates"),
        str(_UI_ROOT / "dashboard" / "templates"),
        str(_UI_ROOT / "detail" / "templates"),
        str(_UI_ROOT / "connector_registry" / "templates"),
        str(_UI_ROOT / "evaluator_registry" / "templates"),
        str(_UI_ROOT / "wizard" / "templates"),
        str(_UI_ROOT / "export_ui" / "templates"),
        str(_UI_ROOT / "auth" / "templates"),
        str(_UI_ROOT / "admin" / "templates"),
        str(_UI_ROOT / "docs_ui" / "templates"),
    ]
)


@pass_context
def _url_for_with_query(context: dict, name: str, /, **kwargs: Any) -> str:
    """url_for that appends non-path kwargs as query parameters.

    Starlette 1.0+ raises NoMatchFound when url_for receives extra kwargs
    that are not path parameters. This wrapper separates path params from
    query params by trying url_path_for with all kwargs first, then falling
    back to separating path params from query params.
    """
    from starlette.requests import Request
    from starlette.routing import NoMatchFound

    request: Request = context["request"]
    app = request.app

    # Fast path: all kwargs are path params (most common case)
    try:
        return str(request.url_for(name, **kwargs))
    except NoMatchFound:
        pass
    except TypeError:
        pass

    # Identify which kwargs are path params by trying with no extra params first
    # then incrementally adding them
    try:
        base = str(app.url_path_for(name))
        # All kwargs are query params
        path_params: dict[str, Any] = {}
        query_params: dict[str, Any] = dict(kwargs)
    except (NoMatchFound, TypeError):
        # Try each kwarg as the path param
        path_params = {}
        query_params = {}
        remaining = dict(kwargs)
        for key in list(remaining.keys()):
            candidate = {k: v for k, v in remaining.items() if k == key}
            try:
                app.url_path_for(name, **candidate)
                path_params[key] = remaining.pop(key)
            except (NoMatchFound, TypeError):
                query_params[key] = remaining.pop(key)
        # Any leftover are query params
        query_params.update(remaining)

    try:
        base = str(app.url_path_for(name, **path_params))
    except (NoMatchFound, TypeError):
        base = str(app.url_path_for(name))

    # Build query string, handling lists and None values
    parts: list[tuple[str, str]] = []
    for k, v in query_params.items():
        if v is None:
            continue
        if isinstance(v, (list, tuple)):
            for item in v:
                if item is not None:
                    parts.append((k, str(item)))
        else:
            parts.append((k, str(v)))

    if not parts:
        return base
    return f"{base}?{urlencode(parts)}"


# Override the default url_for with our query-param-aware version
templates.env.globals["url_for"] = _url_for_with_query
