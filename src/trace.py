"""Journal lisible, à la fois dans la console et dans l'interface."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class TraceEvent(BaseModel):
    kind: str
    message: str
    debug: dict[str, Any] | None = None
    duration_ms: float | None = None


class Trace(BaseModel):
    debug: bool = False
    events: list[TraceEvent] = Field(default_factory=list)

    def add(
        self,
        kind: str,
        message: str,
        *,
        duration_ms: float | None = None,
        debug: dict[str, Any] | None = None,
    ) -> None:
        event = TraceEvent(kind=kind, message=message, duration_ms=duration_ms, debug=debug)
        self.events.append(event)
        print(_format(event), flush=True)
        if self.debug and duration_ms is not None:
            print(f"[DEBUG] {kind} duration_ms={duration_ms:.0f}", flush=True)
        if self.debug and debug:
            for key, value in debug.items():
                if key == "request":
                    continue
                print(f"[DEBUG] {key}={value}", flush=True)

    def lines(self) -> list[str]:
        return [_format(event) for event in self.events]


def _format(event: TraceEvent) -> str:
    if event.kind == "SQL":
        return f"[SQL]\n{event.message}"
    return f"[{event.kind}] {event.message}"
