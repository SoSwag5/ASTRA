"""Test-only helper: run discovery through the real Start Scan confirmation.

It calls the production preview() and confirm() exactly as POST
/api/scan/preview and /api/scan/start do, then runs the worker in the
calling thread instead of a background thread so a test can read the result.
It adds no production entry point: without the confirmation that confirm()
issues, main.task('discover') refuses.
"""
from fastapi.responses import JSONResponse


def confirmed_discover(source_id=None):
    from backend import scan_control as sc
    from backend.main import task
    preview = sc.preview(sc.PreviewRequest(source_id=source_id))
    if isinstance(preview, JSONResponse):
        raise AssertionError(preview.body)
    confirmation = sc.confirm(preview['token'])
    if not isinstance(confirmation, sc.ScanConfirmation):
        raise AssertionError(confirmation.body)
    try:
        return task('discover', confirmation=confirmation)
    finally:
        with sc._guard:
            sc._cancel.pop(confirmation.run_id, None)
