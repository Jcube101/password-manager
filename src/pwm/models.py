"""
Data model for pwm (see SPEC.md).

Entry dataclass + helpers for serialization.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any


def now_iso() -> str:
    """Return current UTC time as ISO-8601 with Z suffix (no microseconds for simplicity)."""
    dt = datetime.now(timezone.utc).replace(microsecond=0)
    return dt.isoformat().replace("+00:00", "Z")


@dataclass
class Entry:
    id: str
    label: str
    username: str | None = None
    password: str = ""
    url: str | None = None
    notes: str | None = None
    tags: list[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.created_at:
            self.created_at = now_iso()
        if not self.updated_at:
            self.updated_at = self.created_at

    def touch(self) -> None:
        """Update the updated_at timestamp (called on any mutation)."""
        self.updated_at = now_iso()

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # Ensure consistent ordering / types for JSON
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Entry:
        # Be tolerant of missing optional fields
        return cls(
            id=data["id"],
            label=data["label"],
            username=data.get("username"),
            password=data.get("password", ""),
            url=data.get("url"),
            notes=data.get("notes"),
            tags=data.get("tags", []) or [],
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )
