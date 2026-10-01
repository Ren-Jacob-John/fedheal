"""
Request size limits for the vitals upload / validation endpoints.

CANONICAL COPY: duplicated verbatim into module1-auth and
module2-validation (see config.py's note).

Three layers, all answering HTTP 413:

  1. BodySizeLimitMiddleware — rejects on the declared Content-Length before
     the body is read, and counts streamed bytes for chunked requests that
     declare none. Runs before FastAPI parses/buffers anything, so an
     oversized body never reaches pydantic, pandas or the multipart parser.
  2. check_records() — record count, fields per record, characters per
     string field (JSON uploads and parsed CSV rows alike).
  3. Endpoint code checks the CSV file's byte size and row/column counts.

Defaults are generous for real hospital exports (a few thousand rows) and
tunable per deployment:

    FEDHEAL_MAX_JSON_BODY_BYTES   5 MiB    JSON upload body
    FEDHEAL_MAX_CSV_BYTES         5 MiB    CSV file (multipart overhead is added on top)
    FEDHEAL_MAX_RECORDS           5000     records / CSV rows per request
    FEDHEAL_MAX_RECORD_FIELDS     50       keys / CSV columns per record
    FEDHEAL_MAX_FIELD_CHARS       256      characters in any single string field / header
"""
from dataclasses import dataclass

from fastapi import HTTPException
from starlette.responses import JSONResponse

import config

MULTIPART_OVERHEAD_BYTES = 64 * 1024  # boundaries + headers around the CSV file part


@dataclass(frozen=True)
class UploadLimits:
    max_json_body_bytes: int
    max_csv_bytes: int
    max_records: int
    max_record_fields: int
    max_field_chars: int

    @classmethod
    def from_env(cls) -> "UploadLimits":
        return cls(
            max_json_body_bytes=config.env_int("FEDHEAL_MAX_JSON_BODY_BYTES", 5 * 1024 * 1024),
            max_csv_bytes=config.env_int("FEDHEAL_MAX_CSV_BYTES", 5 * 1024 * 1024),
            max_records=config.env_int("FEDHEAL_MAX_RECORDS", 5000),
            max_record_fields=config.env_int("FEDHEAL_MAX_RECORD_FIELDS", 50),
            max_field_chars=config.env_int("FEDHEAL_MAX_FIELD_CHARS", 256),
        )


def too_large(detail: str) -> HTTPException:
    return HTTPException(status_code=413, detail=detail)


class _BodyTooLarge(HTTPException):
    """Raised while the body streams in. It is an HTTPException(413) on
    purpose: FastAPI turns any *other* exception raised during body reading
    into a 400 "error parsing the body"."""

    def __init__(self, limit: int = 0):
        super().__init__(status_code=413, detail=f"Request body too large (limit {limit} bytes)")


class BodySizeLimitMiddleware:
    """
    Pure-ASGI middleware. `limits` maps an exact request path to the maximum
    body size in bytes for POSTs to it; every other request is untouched.
    """

    def __init__(self, app, limits: dict[str, int]):
        self.app = app
        self.limits = limits

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "POST" or scope["path"] not in self.limits:
            await self.app(scope, receive, send)
            return

        limit = self.limits[scope["path"]]
        declared = None
        for name, value in scope["headers"]:
            if name == b"content-length":
                try:
                    declared = int(value)
                except ValueError:
                    await JSONResponse({"detail": "Invalid Content-Length header"}, status_code=400)(scope, receive, send)
                    return
                break

        if declared is not None and declared > limit:
            await self._reject(scope, receive, send, limit)
            return

        received = 0
        started = False

        async def counting_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise _BodyTooLarge(limit)
            return message

        async def tracking_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, counting_receive, tracking_send)
        except _BodyTooLarge:
            if started:
                raise  # too late to change the status line; surface the abort
            await self._reject(scope, receive, send, limit)

    @staticmethod
    async def _reject(scope, receive, send, limit: int):
        response = JSONResponse(
            {"detail": f"Request body too large (limit {limit} bytes)"},
            status_code=413,
        )
        await response(scope, receive, send)


def check_records(records, limits: UploadLimits) -> None:
    """
    Enforce record count / fields per record / characters per string field.
    Error text names the record INDEX and limit only — never a value.
    """
    if len(records) > limits.max_records:
        raise too_large(f"Too many records in one request (limit {limits.max_records})")
    for idx, record in enumerate(records):
        if not isinstance(record, dict):
            continue
        if len(record) > limits.max_record_fields:
            raise too_large(f"Record {idx} has too many fields (limit {limits.max_record_fields})")
        for key, value in record.items():
            if isinstance(key, str) and len(key) > limits.max_field_chars:
                raise too_large(f"Record {idx} has a field name longer than {limits.max_field_chars} characters")
            if isinstance(value, str) and len(value) > limits.max_field_chars:
                raise too_large(f"Record {idx} has a field value longer than {limits.max_field_chars} characters")
