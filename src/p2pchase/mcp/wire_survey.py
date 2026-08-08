"""Reading a peer's tool surface, and saying whether we can drive it.

Split out of ``tools/wire_check.py`` for the reason ADR-019 gives: the part that
needs a network is a shell, and the part that decides anything is pure and
tested. Only the pure half lives here.

The thing being modelled is the one nobody modelled before 2026-08-08: **an
argument name is part of the wire.** Four interop failures in this league share
that single cause -- gal-roy1 spelling ``negotiate``'s argument ``payload``
where we spelled it ``handshake``; our own client sending ``group_id`` at the
top level where the callee declared one object; imreeyal publishing no ``hello``
at all; imreeyal spelling ``negotiate``'s argument ``message``. Terms get hashed,
signed and compared fourteen ways. The words carrying them were compared never.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolSurface:
    """One published tool: its name and the argument names it will accept."""

    name: str
    arguments: tuple[str, ...] = ()
    required: tuple[str, ...] = ()

    @classmethod
    def from_tool(cls, tool: Any) -> ToolSurface:
        """Read a FastMCP tool description without importing FastMCP.

        The input schema is JSON Schema, so the argument names are the keys of
        ``properties``. A tool that publishes no schema is reported with no
        arguments rather than skipped -- "we could not tell" and "it takes
        nothing" look identical on the wire and both are worth seeing.
        """
        schema = getattr(tool, "inputSchema", None) or getattr(tool, "input_schema", None) or {}
        properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
        required = schema.get("required", []) if isinstance(schema, dict) else []
        return cls(name=str(getattr(tool, "name", tool)),
                   arguments=tuple(sorted(str(key) for key in properties)),
                   required=tuple(sorted(str(key) for key in required)))


@dataclass
class Survey:
    """What we found, and whether it is enough to play."""

    shared: list[ToolSurface] = field(default_factory=list)
    theirs_only: list[ToolSurface] = field(default_factory=list)
    ours_only: list[str] = field(default_factory=list)

    @property
    def drivable(self) -> bool:
        """True when at least one tool we know how to call exists over there.

        Not "all of ours". A reference-v3 peer publishes four names, none of
        them ours except ``negotiate``, and is entirely playable through an
        adapter. Demanding our whole surface would refuse every opponent in the
        league who did not copy our implementation.
        """
        return bool(self.shared)


def compare(surfaces: list[ToolSurface], ours: set[str], interop: set[str]) -> Survey:
    """Split a peer's surface against every name we can drive."""
    drivable = ours | interop
    published = {surface.name: surface for surface in surfaces}
    return Survey(
        shared=[published[name] for name in sorted(published) if name in drivable],
        theirs_only=[published[name] for name in sorted(published) if name not in drivable],
        ours_only=sorted(drivable - set(published)),
    )


def _tool_line(surface: ToolSurface) -> str:
    args = ", ".join(surface.arguments) or "(no arguments published)"
    stars = f"  required: {', '.join(surface.required)}" if surface.required else ""
    return f"    {surface.name:<18} takes {args}{stars}"


def survey_text(url: str, surfaces: list[ToolSurface], ours: set[str],
                interop: set[str]) -> tuple[str, bool]:
    """The human-readable report, and whether the peer is drivable."""
    survey = compare(surfaces, ours, interop)
    lines = [f"  {url}", f"  publishes {len(surfaces)} tools", ""]

    lines.append("  WE CAN DRIVE THESE")
    lines.extend([_tool_line(s) for s in survey.shared] or ["    (none)"])

    if survey.theirs_only:
        lines += ["", "  THEIRS, WHICH WE DO NOT IMPLEMENT",
                  *[_tool_line(s) for s in survey.theirs_only]]
    if survey.ours_only:
        lines += ["", "  OURS, ABSENT FROM THEIR SURFACE",
                  "    " + ", ".join(survey.ours_only)]

    lines += ["", "  " + ("-" * 68), ""]
    if not survey.drivable:
        lines += ["  CANNOT PLAY: not one tool name in common.",
                  "  Nothing about the game terms is wrong -- the two implementations simply",
                  "  cannot address each other. An adapter is needed before a T is named."]
    else:
        lines.append(f"  CAN PLAY: {len(survey.shared)} tool(s) in common.")
        lines += ["  Check the argument names above against what we send. FastMCP matches",
                  "  declared names only, so a wrong spelling is refused by the framework",
                  "  before any handler runs -- and the refusal names the wrong field."]
    return "\n".join(lines), survey.drivable
