"""Parse ATIF-style agent trajectories into a structure that's easy to render.

A trajectory file (``agent/trajectory.json``) looks like::

    {
      "schema_version": "ATIF-v1.6",
      "session_id": "...",
      "agent": {"name": "opencode", "version": "...", "model_name": "..."},
      "steps": [ {step}, ... ],
      "final_metrics": {...}
    }

Each *step* may contain reasoning, an assistant message, one or more tool
calls, and the observations (tool responses) produced by those calls. We flatten
each step into an ordered list of typed *blocks* so the UI can colour-code them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# Logical roles a block can have. The UI maps each to a colour.
ROLE_SYSTEM = "system"
ROLE_REASONING = "reasoning"
ROLE_ASSISTANT = "assistant"
ROLE_TOOL_CALL = "tool_call"
ROLE_TOOL_RESPONSE = "tool_response"

ROLE_ORDER = [
    ROLE_SYSTEM,
    ROLE_REASONING,
    ROLE_ASSISTANT,
    ROLE_TOOL_CALL,
    ROLE_TOOL_RESPONSE,
]


@dataclass
class Block:
    """A single coloured segment within a step."""

    role: str
    title: str            # short label, e.g. "tool call: read"
    body: str             # full text content (already plain text)
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class Step:
    index: int            # 0-based position in the trajectory
    step_id: Any          # original step_id from the file
    timestamp: str | None
    model_name: str | None
    source: str | None
    metrics: dict[str, Any]
    blocks: list[Block]

    @property
    def roles(self) -> list[str]:
        """Distinct roles present in this step, in canonical order."""
        present = {b.role for b in self.blocks}
        return [r for r in ROLE_ORDER if r in present]


@dataclass
class Trajectory:
    path: Path
    schema_version: str | None
    session_id: str | None
    agent_name: str | None
    agent_version: str | None
    model_name: str | None
    steps: list[Step]
    final_metrics: dict[str, Any]
    # sibling metadata (best-effort)
    reward: float | None = None
    instance_name: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Path resolution
# --------------------------------------------------------------------------- #
def resolve_trajectory_path(raw: str) -> Path:
    """Resolve a user-supplied path to an actual ``trajectory.json`` file.

    Accepts the file itself, an instance folder, or the (often doubly-nested)
    outer folder. Searches for ``agent/trajectory.json`` underneath.
    """
    p = Path(raw).expanduser()
    if not p.exists():
        raise FileNotFoundError(f"Path does not exist: {p}")

    if p.is_file():
        return p

    # Common direct location.
    direct = p / "agent" / "trajectory.json"
    if direct.is_file():
        return direct

    # Otherwise search (handles the doubled-folder nesting seen in samples/).
    matches = sorted(p.rglob("trajectory.json"))
    matches = [m for m in matches if m.parent.name == "agent"] or matches
    if not matches:
        raise FileNotFoundError(f"No trajectory.json found under: {p}")
    return matches[0]


# --------------------------------------------------------------------------- #
# Sibling metadata (reward, config, result)
# --------------------------------------------------------------------------- #
def _instance_root(traj_path: Path) -> Path:
    """Best guess at the instance folder, i.e. the parent of ``agent/``."""
    if traj_path.parent.name == "agent":
        return traj_path.parent.parent
    return traj_path.parent


def _load_sibling_metadata(traj_path: Path, traj: Trajectory) -> None:
    root = _instance_root(traj_path)

    reward_file = root / "verifier" / "reward.txt"
    if reward_file.is_file():
        try:
            traj.reward = float(reward_file.read_text().strip())
        except (ValueError, OSError):
            pass

    result_file = root / "result.json"
    if result_file.is_file():
        try:
            result = json.loads(result_file.read_text())
            traj.instance_name = result.get("task_name")
            ar = result.get("agent_result") or {}
            traj.extra["n_input_tokens"] = ar.get("n_input_tokens")
            traj.extra["n_output_tokens"] = ar.get("n_output_tokens")
            vr = (result.get("verifier_result") or {}).get("rewards") or {}
            if traj.reward is None and "reward" in vr:
                traj.reward = vr.get("reward")
        except (ValueError, OSError):
            pass

    if traj.instance_name is None:
        traj.instance_name = root.name


# --------------------------------------------------------------------------- #
# Step flattening
# --------------------------------------------------------------------------- #
def _stringify(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, indent=2, ensure_ascii=False)


def _format_arguments(args: Any) -> str:
    if isinstance(args, dict):
        return json.dumps(args, indent=2, ensure_ascii=False)
    return _stringify(args)


def _observations_by_call_id(observation: Any) -> dict[str, str]:
    """Map a tool_call id -> its response text, from a step's observation."""
    out: dict[str, str] = {}
    if not isinstance(observation, dict):
        return out
    for res in observation.get("results", []) or []:
        if not isinstance(res, dict):
            continue
        call_id = res.get("source_call_id")
        content = res.get("content")
        out[call_id] = _stringify(content) if content is not None else ""
    return out


def _flatten_step(index: int, raw: dict[str, Any]) -> Step:
    blocks: list[Block] = []

    reasoning = raw.get("reasoning_content")
    if isinstance(reasoning, str) and reasoning.strip():
        blocks.append(Block(ROLE_REASONING, "reasoning", reasoning))

    tool_calls = raw.get("tool_calls") or []
    obs_map = _observations_by_call_id(raw.get("observation"))

    # Tool calls, each immediately followed by its matched response.
    for tc in tool_calls:
        if not isinstance(tc, dict):
            continue
        fname = tc.get("function_name", "tool")
        call_id = tc.get("tool_call_id")
        args = _format_arguments(tc.get("arguments"))
        blocks.append(
            Block(
                ROLE_TOOL_CALL,
                f"tool call: {fname}",
                args,
                meta={"function_name": fname, "tool_call_id": call_id},
            )
        )
        if call_id in obs_map:
            blocks.append(
                Block(
                    ROLE_TOOL_RESPONSE,
                    f"tool response: {fname}",
                    obs_map.pop(call_id),
                    meta={"function_name": fname, "tool_call_id": call_id},
                )
            )

    # Any observations not matched to a call (rare) — still show them.
    for call_id, content in obs_map.items():
        blocks.append(
            Block(
                ROLE_TOOL_RESPONSE,
                "tool response",
                content,
                meta={"tool_call_id": call_id},
            )
        )

    # Assistant text message (skip the "(tool use)" placeholder).
    message = raw.get("message")
    if isinstance(message, str) and message.strip() and message.strip() != "(tool use)":
        blocks.append(Block(ROLE_ASSISTANT, "assistant", message))
    elif isinstance(message, (dict, list)):
        blocks.append(Block(ROLE_ASSISTANT, "assistant", _stringify(message)))

    return Step(
        index=index,
        step_id=raw.get("step_id", index + 1),
        timestamp=raw.get("timestamp"),
        model_name=raw.get("model_name"),
        source=raw.get("source"),
        metrics=raw.get("metrics") or {},
        blocks=blocks,
    )


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
def load_trajectory(raw_path: str) -> Trajectory:
    traj_path = resolve_trajectory_path(raw_path)
    data = json.loads(traj_path.read_text())

    agent = data.get("agent") or {}
    steps = [
        _flatten_step(i, s)
        for i, s in enumerate(data.get("steps") or [])
        if isinstance(s, dict)
    ]

    traj = Trajectory(
        path=traj_path,
        schema_version=data.get("schema_version"),
        session_id=data.get("session_id"),
        agent_name=agent.get("name"),
        agent_version=agent.get("version"),
        model_name=agent.get("model_name"),
        steps=steps,
        final_metrics=data.get("final_metrics") or {},
    )
    _load_sibling_metadata(traj_path, traj)
    return traj
