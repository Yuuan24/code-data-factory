"""The four first-version tools.  They intentionally never evaluate arbitrary code."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import duckdb
from pint import UnitRegistry


class ToolInputError(ValueError):
    """A model supplied an invalid tool argument or a hidden resource identifier."""


class RestrictedTools:
    """Read-only document lookup plus typed arithmetic and unit/time conversion."""

    def __init__(self, documents: Mapping[str, str]) -> None:
        if not documents:
            raise ValueError("restricted tools require at least one document")
        self._documents = dict(documents)
        self._db = duckdb.connect(":memory:")
        self._db.execute("CREATE TABLE documents(document_id VARCHAR, content VARCHAR)")
        self._db.executemany("INSERT INTO documents VALUES (?, ?)", list(self._documents.items()))
        self._units: Any = UnitRegistry()

    def search_documents(self, query: str) -> list[str]:
        if not isinstance(query, str) or not query.strip() or len(query) > 256:
            raise ToolInputError("query must be a non-empty string of at most 256 characters")
        words = [part for part in query.lower().split() if part.isalnum()]
        if not words:
            raise ToolInputError("query must contain alphanumeric search terms")
        clause = " OR ".join("lower(content) LIKE ?" for _ in words)
        values = [f"%{word}%" for word in words]
        rows = self._db.execute(
            f"SELECT document_id FROM documents WHERE {clause} ORDER BY document_id", values
        ).fetchall()
        return [str(row[0]) for row in rows]

    def read_document(self, document_id: str) -> str:
        if document_id not in self._documents:
            raise ToolInputError("document_id is not available in this task")
        return self._documents[document_id]

    def calculate(self, operation: str, operands: list[str]) -> str:
        if operation not in {"ADD", "SUBTRACT", "MULTIPLY", "DIVIDE"}:
            raise ToolInputError("operation must be ADD, SUBTRACT, MULTIPLY, or DIVIDE")
        if not isinstance(operands, list) or len(operands) < 2:
            raise ToolInputError("calculation requires at least two numeric operands")
        try:
            values = [Decimal(value) for value in operands]
        except (InvalidOperation, ValueError) as error:
            raise ToolInputError("operands must be decimal literals") from error
        result = values[0]
        for value in values[1:]:
            if operation == "ADD":
                result += value
            elif operation == "SUBTRACT":
                result -= value
            elif operation == "MULTIPLY":
                result *= value
            else:
                if value == 0:
                    raise ToolInputError("division by zero is not allowed")
                result /= value
        return format(result.normalize(), "f")

    def convert(self, value: str, from_unit: str, to_unit: str, *, timezone: str | None = None) -> str:
        try:
            amount = Decimal(value)
        except (InvalidOperation, ValueError) as error:
            raise ToolInputError("value must be a decimal literal") from error
        if timezone is not None:
            try:
                ZoneInfo(timezone)
            except ZoneInfoNotFoundError as error:
                raise ToolInputError("timezone must be an IANA zone name") from error
        try:
            converted = self._units.Quantity(amount, from_unit).to(to_unit).magnitude
        except Exception as error:  # Pint exposes several version-specific error subclasses.
            raise ToolInputError("unsupported or incompatible units") from error
        return format(Decimal(str(converted)).normalize(), "f")
