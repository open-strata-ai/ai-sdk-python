"""Application layer (②): Agent orchestration use cases.

Re-exports :class:`AgentSpec` (defined in the domain models for cross-language
consistency) and provides the thin :class:`Agent` runtime wrapper.
"""

from __future__ import annotations

from typing import Any, Dict

from openstrata_sdk.domain.models import AgentHandle, AgentSpec
from openstrata_sdk.domain.ports import AgentRuntime


class Agent:
    """Loads an :class:`AgentSpec` onto a runtime and runs it (DESIGN §4.1)."""

    def __init__(self, runtime: AgentRuntime, spec: AgentSpec) -> None:
        self._runtime = runtime
        self._spec = spec
        self._handle: AgentHandle = runtime.load(spec)

    @property
    def handle(self) -> AgentHandle:
        return self._handle

    def run(self, input: Dict[str, Any]) -> Dict[str, Any]:
        return self._runtime.run(self._handle, input)


__all__ = ["Agent", "AgentSpec"]
