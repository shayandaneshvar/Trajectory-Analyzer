"""Trajectory Analyzer — step-by-step trajectory visualizer.

First step of the project: load a single agent trajectory and let the user
scroll through it with role-colour-coded blocks, plus a sticky top ribbon of
per-step rectangles that jump to any step in the page.

Run with::

    streamlit run app.py
"""

from __future__ import annotations

import html

import streamlit as st

import trajectory as T

# --------------------------------------------------------------------------- #
# Colour scheme (one per logical role)
# --------------------------------------------------------------------------- #
ROLE_COLORS = {
    T.ROLE_SYSTEM: "#9e9e9e",        # grey
    T.ROLE_REASONING: "#2e7d32",     # dark green (assistant thinking)
    T.ROLE_ASSISTANT: "#4caf50",     # green
    T.ROLE_TOOL_CALL: "#2196f3",     # blue
    T.ROLE_TOOL_RESPONSE: "#e53935",  # red
}
ROLE_LABELS = {
    T.ROLE_SYSTEM: "System",
    T.ROLE_REASONING: "Reasoning",
    T.ROLE_ASSISTANT: "Assistant",
    T.ROLE_TOOL_CALL: "Tool call",
    T.ROLE_TOOL_RESPONSE: "Tool response",
}

# Tool responses can be huge (file reads); cap them and keep them scrollable.
RESPONSE_MAX_HEIGHT = 320


def step_anchor(index: int) -> str:
    return f"step-{index + 1}"


# --------------------------------------------------------------------------- #
# CSS
# --------------------------------------------------------------------------- #
def inject_css() -> None:
    rules = """
    <style>
      .ribbon-wrap {
        position: sticky;
        top: 0;
        z-index: 999;
        background: var(--background-color, #0e1117);
        padding: 8px 0 10px 0;
        border-bottom: 1px solid rgba(128,128,128,0.3);
        margin-bottom: 12px;
      }
      .ribbon {
        display: flex;
        flex-wrap: wrap;
        gap: 4px;
      }
      .ribbon-cell {
        width: 30px;
        text-decoration: none;
        border-radius: 4px;
        overflow: hidden;
        border: 1px solid rgba(128,128,128,0.4);
        font-size: 10px;
        text-align: center;
        color: inherit !important;
      }
      .ribbon-cell:hover { outline: 2px solid #fff; }
      .ribbon-num {
        padding: 1px 0;
        font-weight: 600;
        color: #ddd;
      }
      .ribbon-bars { display: flex; height: 8px; }
      .ribbon-bars span { flex: 1; }
      .legend { display: flex; flex-wrap: wrap; gap: 14px; margin: 4px 0 2px 0; }
      .legend-item { display: flex; align-items: center; gap: 6px; font-size: 13px; }
      .legend-swatch { width: 14px; height: 14px; border-radius: 3px; }

      .block { border-left: 5px solid #888; border-radius: 4px;
               padding: 6px 12px; margin: 8px 0; background: rgba(128,128,128,0.06); }
      .block-title { font-weight: 600; font-size: 13px; margin-bottom: 4px;
                     text-transform: uppercase; letter-spacing: .3px; }
      .block pre { white-space: pre-wrap; word-break: break-word; margin: 0;
                   font-size: 12.5px; }
      .response-box { max-height: %dpx; overflow: auto;
                      background: rgba(0,0,0,0.25); border-radius: 4px; padding: 8px; }
      .step-header { margin-top: 18px; padding-top: 6px;
                     border-top: 2px dashed rgba(128,128,128,0.35); }
    </style>
    """ % RESPONSE_MAX_HEIGHT
    st.markdown(rules, unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def render_ribbon(traj: T.Trajectory) -> None:
    cells = []
    for step in traj.steps:
        roles = step.roles or [T.ROLE_SYSTEM]
        bars = "".join(
            f'<span style="background:{ROLE_COLORS[r]}"></span>' for r in roles
        )
        tip = f"Step {step.index + 1}: " + ", ".join(ROLE_LABELS[r] for r in roles)
        cells.append(
            f'<a class="ribbon-cell" href="#{step_anchor(step.index)}" title="{html.escape(tip)}">'
            f'<div class="ribbon-num">{step.index + 1}</div>'
            f'<div class="ribbon-bars">{bars}</div></a>'
        )
    st.markdown(
        f'<div class="ribbon-wrap"><div class="ribbon">{"".join(cells)}</div></div>',
        unsafe_allow_html=True,
    )


def render_legend() -> None:
    items = "".join(
        f'<div class="legend-item"><span class="legend-swatch" '
        f'style="background:{ROLE_COLORS[r]}"></span>{ROLE_LABELS[r]}</div>'
        for r in T.ROLE_ORDER
    )
    st.markdown(f'<div class="legend">{items}</div>', unsafe_allow_html=True)


def render_block(block: T.Block) -> None:
    color = ROLE_COLORS.get(block.role, "#888")
    body = html.escape(block.body)
    pre_class = "response-box" if block.role == T.ROLE_TOOL_RESPONSE else ""
    inner = f'<pre>{body}</pre>'
    if pre_class:
        inner = f'<div class="{pre_class}"><pre>{body}</pre></div>'
    st.markdown(
        f'<div class="block" style="border-left-color:{color}">'
        f'<div class="block-title" style="color:{color}">{html.escape(block.title)}</div>'
        f'{inner}</div>',
        unsafe_allow_html=True,
    )


def render_step(step: T.Step) -> None:
    anchor = step_anchor(step.index)
    bits = []
    if step.timestamp:
        bits.append(step.timestamp)
    m = step.metrics or {}
    if m.get("prompt_tokens") is not None:
        bits.append(f"in {m['prompt_tokens']} tok")
    if m.get("completion_tokens") is not None:
        bits.append(f"out {m['completion_tokens']} tok")
    sub = "  ·  ".join(str(b) for b in bits)

    st.markdown(
        f'<div class="step-header" id="{anchor}">'
        f'<h3 style="margin-bottom:0">Step {step.index + 1}</h3>'
        f'<div style="font-size:12px;opacity:.7">{html.escape(sub)}</div></div>',
        unsafe_allow_html=True,
    )
    for block in step.blocks:
        render_block(block)


def render_header(traj: T.Trajectory) -> None:
    if traj.reward is None:
        badge = "❔ no reward"
    elif traj.reward >= 1.0:
        badge = "✅ PASS (reward = 1)"
    elif traj.reward <= 0.0:
        badge = "❌ FAIL (reward = 0)"
    else:
        badge = f"⚠️ reward = {traj.reward}"

    st.title("🛰️ Trajectory Analyzer")
    st.markdown(f"### `{traj.instance_name}` — {badge}")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Scaffold", traj.agent_name or "—")
    c2.metric("Steps", len(traj.steps))
    c3.metric("Input tokens", f"{traj.extra.get('n_input_tokens', '—'):,}"
              if isinstance(traj.extra.get("n_input_tokens"), int) else "—")
    c4.metric("Output tokens", f"{traj.extra.get('n_output_tokens', '—'):,}"
              if isinstance(traj.extra.get("n_output_tokens"), int) else "—")

    st.caption(
        f"Model: `{traj.model_name or '—'}`  ·  "
        f"agent `{traj.agent_name or '—'}` v{traj.agent_version or '—'}  ·  "
        f"schema `{traj.schema_version or '—'}`  ·  `{traj.path}`"
    )


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> None:
    st.set_page_config(page_title="Trajectory Analyzer", layout="wide")
    inject_css()

    st.sidebar.header("Load trajectory")
    default = "samples/huggingface__datasets-7170__TUXmHfo"
    raw_path = st.sidebar.text_input(
        "Path to trajectory.json or instance folder",
        value=st.session_state.get("traj_path", default),
        help="Accepts a trajectory.json, an instance folder, or its parent.",
    )
    st.session_state["traj_path"] = raw_path

    if not raw_path.strip():
        st.info("Enter a path in the sidebar to load a trajectory.")
        return

    try:
        traj = T.load_trajectory(raw_path)
    except Exception as exc:  # surface load errors plainly
        st.error(f"Could not load trajectory: {exc}")
        return

    render_header(traj)
    render_legend()
    render_ribbon(traj)

    if not traj.steps:
        st.warning("This trajectory has no steps.")
        return

    for step in traj.steps:
        render_step(step)


if __name__ == "__main__":
    main()