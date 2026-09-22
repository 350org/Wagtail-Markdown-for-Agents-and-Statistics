"""Explicit public routes; hosts choose where to include the package URLconf."""

from django.http import Http404
from django.views.decorators.http import require_safe

from .export.paths import ExportPathError, validate_path
from .serving import request_site, serve_export


@require_safe
def export(request, export_path):
    try:
        validate_path(export_path)
    except ExportPathError as exc:
        raise Http404 from exc
    site = request_site(request)
    if site is None:
        raise Http404
    response = serve_export(request, f"{site.hostname}/{export_path}")
    if response is None:
        raise Http404
    return response
