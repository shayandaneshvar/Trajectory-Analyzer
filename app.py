"""Trajectory Analyzer — step-by-step trajectory visualizer.

First step of the project: load a single agent trajectory and let the user
scroll through it with role-colour-coded blocks, plus a sticky top ribbon of
per-step rectangles that jump to any step in the page.

Run with::

    streamlit run app.py
"""

from __future__ import annotations

import html
import json
from collections import Counter

import streamlit as st

import analysis as A
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
      /* Fixed vertical navigator pinned to the right edge of the viewport. */
      .side-ribbon {
        position: fixed;
        right: 6px;
        top: 70px;
        max-height: calc(100vh - 90px);
        overflow-y: auto;
        z-index: 1000;
        display: flex;
        flex-direction: column;
        gap: 3px;
        padding: 6px 4px;
        background: rgba(20,22,30,0.85);
        border: 1px solid rgba(128,128,128,0.35);
        border-radius: 6px;
        backdrop-filter: blur(2px);
      }
      .side-ribbon .side-title {
        font-size: 9px; text-align: center; color: #aaa;
        text-transform: uppercase; letter-spacing: .5px; margin-bottom: 2px;
      }
      .side-cell {
        width: 34px;
        text-decoration: none;
        border-radius: 4px;
        overflow: hidden;
        border: 1px solid rgba(128,128,128,0.4);
        color: inherit !important;
        transition: box-shadow .15s ease;
      }
      .side-cell:hover { outline: 2px solid #fff; }
      .side-cell .ribbon-num { padding: 0; font-size: 10px; }
      .side-cell .ribbon-bars { height: 6px; transition: height .15s ease; }
      /* The step currently in view: same width, ~3x taller and highlighted. */
      .side-cell.active {
        border: 2px solid #ffffff;
        box-shadow: 0 0 10px rgba(255,255,255,0.6);
      }
      .side-cell.active .ribbon-num { font-size: 13px; font-weight: 700; padding: 4px 0; }
      .side-cell.active .ribbon-bars { height: 34px; }

      /* Assigned-category chips: laid out side by side, ✕ shown on hover. */
      [class*="st-key-chiprow__"] { flex-wrap: wrap !important; gap: 8px !important;
                                    margin: 4px 0 10px 0; }
      [class*="st-key-chip__"] {
        background: transparent;
        border: none !important;
        padding: 0 0 0 4px !important;
        align-items: center !important;
        gap: 0 !important;
        width: auto !important;
      }
      [class*="st-key-chip__"] p { margin: 0 !important; }
      [class*="st-key-chip__"] .stButton button {
        opacity: 0; min-height: 0; height: 22px; padding: 0 6px;
        border: none; background: transparent; color: #ff8a80;
        transition: opacity .12s ease;
      }
      [class*="st-key-chip__"]:hover .stButton button { opacity: 1; }

      .legend { display: flex; flex-wrap: wrap; gap: 14px; margin: 4px 0 2px 0; }
      .legend-item { display: flex; align-items: center; gap: 6px; font-size: 13px; }
      .legend-swatch { width: 14px; height: 14px; border-radius: 3px; }

      .block { border-left: 5px solid #888; border-radius: 4px;
               padding: 6px 12px; margin: 8px 0; background: rgba(128,128,128,0.06); }
      .block-title { font-weight: 600; font-size: 13px; margin-bottom: 4px;
                     text-transform: uppercase; letter-spacing: .3px; }
      .block pre { white-space: pre-wrap; word-break: break-word; margin: 0;
                   font-size: 12.5px; }
      /* Reasoning sub-rectangle inside the assistant block. */
      .reasoning-box {
        border: 1px dashed rgba(46,125,50,0.6); border-radius: 4px;
        background: rgba(46,125,50,0.10);
        padding: 6px 8px; margin-bottom: 8px;
      }
      .reasoning-label {
        font-size: 10px; text-transform: uppercase; letter-spacing: .4px;
        color: #66bb6a; margin-bottom: 3px;
      }
      .reasoning-box pre { font-style: italic; opacity: .9; }
      .assistant-msg { font-size: 12.5px; }
      /* Tool call / response containers: colored left border + hover ✨ button. */
      [class*="st-key-toolcall__"], [class*="st-key-toolresp__"] {
        border-radius: 4px; padding: 6px 12px; margin: 8px 0;
        background: rgba(128,128,128,0.06);
      }
      [class*="st-key-toolcall__"] { border-left: 5px solid #2196f3; }
      [class*="st-key-toolresp__"] { border-left: 5px solid #e53935; }
      [class*="st-key-toolcall__"] .stButton button,
      [class*="st-key-toolresp__"] .stButton button {
        opacity: 0; transition: opacity .12s ease;
        min-height: 0; padding: 0 6px; border: none; background: transparent;
      }
      [class*="st-key-toolcall__"]:hover .stButton button,
      [class*="st-key-toolresp__"]:hover .stButton button { opacity: 1; }
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


def render_side_ribbon(traj: T.Trajectory) -> None:
    """A fixed vertical copy of the ribbon that stays visible while scrolling."""
    cells = ['<div class="side-title">steps</div>']
    for step in traj.steps:
        roles = step.roles or [T.ROLE_SYSTEM]
        bars = "".join(
            f'<span style="background:{ROLE_COLORS[r]}"></span>' for r in roles
        )
        tip = f"Step {step.index + 1}: " + ", ".join(ROLE_LABELS[r] for r in roles)
        cells.append(
            f'<a class="side-cell" href="#{step_anchor(step.index)}" title="{html.escape(tip)}">'
            f'<div class="ribbon-num">{step.index + 1}</div>'
            f'<div class="ribbon-bars">{bars}</div></a>'
        )
    st.markdown(
        f'<div class="side-ribbon">{"".join(cells)}</div>',
        unsafe_allow_html=True,
    )
    _inject_scrollspy()


def _inject_scrollspy() -> None:
    """Highlight the side-ribbon cell of the step currently in view.

    Streamlit sanitizes <script> in markdown, so we run JS inside a
    components iframe and reach into the parent document (same origin) to
    track scroll position and toggle the `.active` class.
    """
    st.iframe(
        """
        <script>
        const doc = window.parent.document;
        function update() {
            const steps = Array.from(doc.querySelectorAll('[id^="step-"]'));
            if (!steps.length) return;
            let active = steps[0].id;
            for (const el of steps) {
                if (el.getBoundingClientRect().top <= 140) active = el.id;
                else break;
            }
            doc.querySelectorAll('.side-cell').forEach(a => {
                a.classList.toggle('active', a.getAttribute('href') === '#' + active);
            });
        }
        const root = window.parent;
        let ticking = false;
        function onScroll() {
            if (ticking) return;
            ticking = true;
            root.requestAnimationFrame(() => { update(); ticking = false; });
        }
        root.addEventListener('scroll', onScroll, true);
        root.addEventListener('resize', onScroll, true);
        setInterval(update, 400);
        update();
        </script>
        """,
        height=1,
    )


def render_legend() -> None:
    items = "".join(
        f'<div class="legend-item"><span class="legend-swatch" '
        f'style="background:{ROLE_COLORS[r]}"></span>{ROLE_LABELS[r]}</div>'
        for r in T.ROLE_ORDER
    )
    st.markdown(f'<div class="legend">{items}</div>', unsafe_allow_html=True)


def render_block(block: T.Block, key: str = "") -> None:
    if block.role == T.ROLE_ASSISTANT:
        render_assistant_block(block)
        return
    if block.role in (T.ROLE_TOOL_CALL, T.ROLE_TOOL_RESPONSE):
        render_tool_block(block, key)
        return

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


def render_assistant_block(block: T.Block) -> None:
    """Assistant block: reasoning (italic sub-box) on top, message below."""
    color = ROLE_COLORS[T.ROLE_ASSISTANT]
    reasoning = (block.meta or {}).get("reasoning", "")

    parts = [
        f'<div class="block-title" style="color:{color}">assistant</div>'
    ]
    if reasoning:
        parts.append(
            '<div class="reasoning-box">'
            '<div class="reasoning-label">reasoning</div>'
            f'<pre>{html.escape(reasoning)}</pre></div>'
        )
    if block.body:
        parts.append(f'<pre class="assistant-msg">{html.escape(block.body)}</pre>')

    st.markdown(
        f'<div class="block" style="border-left-color:{color}">{"".join(parts)}</div>',
        unsafe_allow_html=True,
    )


def _try_json(text: str):
    """Return a parsed JSON object/array if ``text`` is JSON, else None."""
    stripped = text.strip()
    if not stripped or stripped[0] not in "{[":
        return None
    try:
        return json.loads(stripped)
    except ValueError:
        return None


def render_tool_block(block: T.Block, key: str) -> None:
    """Tool call / response block with a hover ✨ button to beautify content."""
    color = ROLE_COLORS[block.role]
    prefix = "toolcall" if block.role == T.ROLE_TOOL_CALL else "toolresp"
    state_key = f"beautify::{key}"
    beautified = st.session_state.get(state_key, False)

    with st.container(key=f"{prefix}__{key}"):
        head, btn = st.columns([12, 1], vertical_alignment="center")
        head.markdown(
            f'<div class="block-title" style="color:{color}">'
            f'{html.escape(block.title)}</div>',
            unsafe_allow_html=True,
        )
        if btn.button("✨" if not beautified else "↩",
                      key=f"btn::{state_key}",
                      help="Beautify (easy-to-read)" if not beautified else "Show raw"):
            st.session_state[state_key] = not beautified
            st.rerun()

        if beautified:
            obj = _try_json(block.body)
            if obj is not None:
                st.json(obj)
            else:
                st.code(block.body)
        elif block.role == T.ROLE_TOOL_RESPONSE:
            st.markdown(
                f'<div class="response-box"><pre>{html.escape(block.body)}</pre></div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(f'<pre>{html.escape(block.body)}</pre>', unsafe_allow_html=True)


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
    for i, block in enumerate(step.blocks):
        render_block(block, key=f"{step.index}_{i}")


def render_header(traj: T.Trajectory) -> None:
    if traj.reward is None:
        badge = "❔ no reward"
    elif traj.reward >= 1.0:
        badge = "✅ PASS (reward = 1)"
    elif traj.reward <= 0.0:
        badge = "❌ FAIL (reward = 0)"
    else:
        badge = f"⚠️ reward = {traj.reward}"

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
# Sidebar loader: a path field + a selectable list of discovered instances
# --------------------------------------------------------------------------- #
def sidebar_loader() -> str | None:
    """Render the loader and return the chosen trajectory path (or None)."""
    st.sidebar.header("Load trajectory")
    default = "samples"
    raw_path = st.sidebar.text_input(
        "Path (file, instance folder, or a folder of instances)",
        value=st.session_state.get("traj_base_path", default),
        help="Sub-folders that contain a trajectory will be listed below to select.",
    )
    st.session_state["traj_base_path"] = raw_path

    if not raw_path.strip():
        st.sidebar.info("Enter a path to discover trajectories.")
        return None

    try:
        instances = T.discover_instances(raw_path)
    except Exception as exc:
        st.sidebar.error(str(exc))
        return None

    if not instances:
        st.sidebar.warning("No trajectory found under this path.")
        return None

    # Filters only make sense when several instances were discovered.
    if len(instances) > 1:
        instances = _apply_filters(instances)
        if not instances:
            st.sidebar.warning("No trajectories match the current filters.")
            return None

    st.sidebar.caption(f"Showing {len(instances)} trajectory folder(s):")
    choice = st.sidebar.radio(
        "Select a trajectory",
        options=range(len(instances)),
        format_func=lambda i: _instance_label(instances[i]),
        label_visibility="collapsed",
        key="traj_choice",
    )
    return instances[choice][1]


@st.cache_data(show_spinner=False)
def _reward_for(path: str) -> float | None:
    return T.quick_reward(path)


def _reward_badge(path: str) -> str:
    r = _reward_for(path)
    if r is None:
        return "❔"
    return "✅" if r >= 1.0 else "❌"


def _instance_label(instance: tuple[str, str]) -> str:
    name, path = instance
    return f"{_reward_badge(path)} {name}"


def _parse_filter_list(raw: str) -> list[str]:
    """Parse a custom filter: a JSON list (``[\"a\", \"b\"]``) or comma-separated."""
    raw = raw.strip()
    if not raw:
        return []
    try:
        value = json.loads(raw)
        if isinstance(value, list):
            return [str(x).strip() for x in value if str(x).strip()]
    except ValueError:
        pass
    return [s.strip() for s in raw.split(",") if s.strip()]


def _evalhub_key(name: str) -> str:
    """Normalize an EvalHub name to ``Company__Repo`` (drops the random suffix)."""
    return "__".join(name.split("__")[:2]).lower()


def _apply_filters(instances: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Custom substring filter first, then the pass/fail status filter."""
    # 1) Custom filter (applied first).
    custom_raw = st.sidebar.text_input(
        "Custom filter",
        key="custom_filter",
        placeholder='e.g. huggingface, conan  or  ["huggingface", "conan"]',
        help="Match folders whose name contains any of these substrings.",
    )
    exclude = st.sidebar.toggle(
        "Exclude matches",
        key="custom_filter_exclude",
        help="Off: include matches. On: exclude matches.",
    )
    evalhub = st.sidebar.toggle(
        "EvalHub names",
        value=True,
        key="custom_filter_evalhub",
        help="Treat entries as EvalHub names (Company__Repo__Random); the "
             "random suffix is ignored when matching.",
    )
    subs = _parse_filter_list(custom_raw)
    if subs:
        if evalhub:
            targets = {_evalhub_key(s) for s in subs}

            def matches(name: str) -> bool:
                return _evalhub_key(name) in targets
        else:
            lowered = [s.lower() for s in subs]

            def matches(name: str) -> bool:
                return any(s in name.lower() for s in lowered)

        instances = [(n, p) for (n, p) in instances
                     if matches(n) != exclude]

    # 2) Pass/fail status filter (applied after the custom filter).
    status = st.sidebar.pills(
        "Status",
        ["✅ Passed", "❌ Failed"],
        selection_mode="multi",
        default=[],
        key="status_filter",
        help="No selection shows all.",
    )
    if status:
        want_pass = "✅ Passed" in status
        want_fail = "❌ Failed" in status

        def keep(path: str) -> bool:
            r = _reward_for(path)
            if r is None:
                return False
            passed = r >= 1.0
            return (passed and want_pass) or ((not passed) and want_fail)

        instances = [(n, p) for (n, p) in instances if keep(p)]

    return instances


# --------------------------------------------------------------------------- #
# Failure categorization (tag from the top of the viewer page)
# --------------------------------------------------------------------------- #
def render_tagging(analysis_file, entry_key: str) -> None:
    data = A.load_analysis(analysis_file)
    current = A.get_categories_for(data, entry_key)
    catalog = A.load_categories()
    catalog_ids = [A.category_id(c) for c in catalog]
    assigned_ids = {c.get("id") for c in current}

    with st.container(border=True):
        st.markdown("##### 🏷️ Categories for this trajectory")

        # Currently assigned categories: horizontal chips, each with an ✕ that
        # appears on hover (native buttons → removal handled in-session).
        pending_key = f"pending_rm::{entry_key}"
        if current:
            with st.container(horizontal=True, key=f"chiprow__{entry_key}"):
                for i, item in enumerate(current):
                    cid = item.get("id", "")
                    note = item.get("notes", "")
                    with st.container(horizontal=True, width="content",
                                      key=f"chip__{entry_key}__{i}"):
                        if note:
                            st.markdown(
                                f'<code title="{html.escape(note, quote=True)}" '
                                f'style="cursor:help">{html.escape(cid)}</code>',
                                unsafe_allow_html=True,
                            )
                        else:
                            st.markdown(f"`{cid}`")
                        if st.button("✕", key=f"x__{entry_key}__{i}",
                                     help="remove"):
                            st.session_state[pending_key] = cid
                            st.rerun()
        else:
            st.caption("No categories assigned yet.")

        pending = st.session_state.get(pending_key)
        if pending:
            c1, c2, c3 = st.columns([6, 1, 1])
            c1.markdown(f"Remove **`{pending}`**?")
            if c2.button("Confirm", key=f"confirm::{entry_key}", type="primary"):
                A.remove_category(analysis_file, entry_key, pending)
                st.session_state.pop(pending_key, None)
                st.rerun()
            if c3.button("Cancel", key=f"cancel::{entry_key}"):
                st.session_state.pop(pending_key, None)
                st.rerun()

        tab_existing, tab_new = st.tabs(["Assign existing", "Create new"])

        with tab_existing:
            available = [cid for cid in catalog_ids if cid not in assigned_ids]
            if not available:
                st.caption("No more existing categories to assign — create one →")
            else:
                sel = st.selectbox(
                    "Category", available, key=f"sel::{entry_key}",
                    help=A.category_descriptions().get(
                        available[0], "") if available else "",
                )
                notes = st.text_input("Notes (optional)", key=f"note::{entry_key}")
                if st.button("Add category", key=f"add::{entry_key}"):
                    A.assign_category(analysis_file, entry_key, sel, notes.strip())
                    st.rerun()

        with tab_new:
            st.caption("Type is `fail` for now. Id will be `fail:<short name>`.")
            new_name = st.text_input("Short name", key=f"new_name::{entry_key}",
                                     placeholder="e.g. wrong_test_setup")
            new_desc = st.text_area("Description", key=f"new_desc::{entry_key}",
                                    placeholder="What does this failure category mean?")
            new_notes = st.text_input("Notes (optional)", key=f"new_note::{entry_key}")
            if st.button("Create & assign", key=f"create::{entry_key}"):
                if not new_name.strip():
                    st.warning("Please enter a short name.")
                else:
                    cid = A.add_category(new_name, new_desc, type_=A.DEFAULT_TYPE)
                    A.assign_category(analysis_file, entry_key, cid, new_notes.strip())
                    st.rerun()

        st.caption(f"Stored in `{analysis_file}` under key `{entry_key}`.")


# --------------------------------------------------------------------------- #
# Pages
# --------------------------------------------------------------------------- #
def trajectory_viewer_page() -> None:
    inject_css()
    chosen = sidebar_loader()
    if chosen is None:
        st.info("Pick a trajectory from the sidebar to begin.")
        return

    try:
        traj = T.load_trajectory(chosen)
    except Exception as exc:  # surface load errors plainly
        st.error(f"Could not load trajectory: {exc}")
        return

    render_header(traj)

    base = st.session_state.get("traj_base_path", "")
    analysis_file, entry_key = A.analysis_target(base, chosen, traj.path)
    render_tagging(analysis_file, entry_key)

    render_legend()
    render_ribbon(traj)
    render_side_ribbon(traj)

    if not traj.steps:
        st.warning("This trajectory has no steps.")
        return

    for step in traj.steps:
        render_step(step)


def categories_page() -> None:
    st.header("🏷️ Categories")

    catalog = A.load_categories()
    st.subheader("Catalog")
    if not catalog:
        st.info("No categories defined yet.")
    else:
        st.table([{"id": A.category_id(c), "description": c.get("description", "")}
                  for c in catalog])

    with st.expander("➕ Add a new category"):
        st.caption("Type is `fail` for now. Id will be `fail:<short name>`.")
        name = st.text_input("Short name", key="catpage_name",
                             placeholder="e.g. wrong_test_setup")
        desc = st.text_area("Description", key="catpage_desc",
                            placeholder="What does this failure category mean?")
        if st.button("Create category", key="catpage_create"):
            if not name.strip():
                st.warning("Please enter a short name.")
            else:
                A.add_category(name, desc, type_=A.DEFAULT_TYPE)
                st.rerun()

    base = st.session_state.get("traj_base_path", "")
    st.subheader("Assignments")
    if not base.strip():
        st.caption("Load a path in the Trajectory Viewer to see assignments.")
        return

    st.caption(f"Scanning `{base}` for `{A.ANALYSIS_FILENAME}` files.")
    assignments = A.collect_assignments(base)
    if not assignments:
        st.info("No trajectories have been categorized under this path yet.")
        return

    descriptions = A.category_descriptions()
    for cat_id in sorted(assignments):
        folders = assignments[cat_id]
        with st.expander(f"`{cat_id}`  ·  {len(folders)} trajectory(ies)"):
            desc = descriptions.get(cat_id)
            if desc:
                st.caption(desc)
            for item in folders:
                line = f"- **{item['folder']}**"
                if item.get("notes"):
                    line += f" — {item['notes']}"
                st.markdown(line)


def summary_page() -> None:
    st.header("📊 Summary")

    # Select the path here; data comes from traj-analysis.json files under it
    # joined with the category descriptions from resources/categories.json.
    base = st.text_input(
        "Path to a folder of trajectories",
        value=st.session_state.get("traj_base_path", "samples"),
        help="Scans this path for traj-analysis.json files.",
    )
    st.session_state["traj_base_path"] = base
    if not base.strip():
        st.info("Enter a path to summarize.")
        return

    # Flatten all assignments under the selected path into per-(name, tag) rows.
    assignments = A.collect_assignments(base)
    rows = [{"cat": cat_id, **item}
            for cat_id, items in assignments.items() for item in items]
    if not rows:
        st.info("No tagged samples under this path yet.")
        return

    descriptions = A.category_descriptions()

    # "Fail switch and all": filter the included samples by pass/fail status.
    status = st.pills(
        "Status", ["✅ Passed", "❌ Failed"],
        selection_mode="multi", default=[], key="summary_status",
        help="No selection shows all.",
    )
    if status:
        want_pass = "✅ Passed" in status
        want_fail = "❌ Failed" in status

        def keep(path: str) -> bool:
            r = _reward_for(path)
            if r is None:
                return False
            passed = r >= 1.0
            return (passed and want_pass) or ((not passed) and want_fail)

        rows = [r for r in rows if keep(r["path"])]

    if not rows:
        st.warning("No samples match the filter.")
        return

    # Top-N tags by frequency (most repeated first).
    counts = Counter(r["cat"] for r in rows)
    top_n = st.number_input(
        "Top N tags", min_value=1, max_value=len(counts),
        value=min(10, len(counts)), step=1,
    )
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:int(top_n)]
    top_tags = [{"tag": c, "count": n, "description": descriptions.get(c, "")}
                for c, n in ranked]
    st.subheader("Top tags")
    st.dataframe(top_tags, width="stretch", hide_index=True)

    # Detail table: which sample has which tag, with descriptions and notes.
    st.subheader(f"Tagged samples ({len(rows)} rows)")
    table = sorted(
        ({"name": r["folder"], "status": _reward_badge(r["path"]),
          "tag": r["cat"], "description": descriptions.get(r["cat"], ""),
          "note": r.get("notes", "")}
         for r in rows),
        key=lambda x: (x["name"], x["tag"]),
    )
    st.dataframe(table, width="stretch", hide_index=True)

    # Export the data shown above to out/summaries/<datetime>.json.
    st.subheader("Export")
    exp_name = st.text_input("Experiment name", key="export_exp_name")
    exp_desc = st.text_area("Description", key="export_exp_desc")
    if st.button("Export summary"):
        payload = {
            "meta": {
                "experiment_name": exp_name,
                "description": exp_desc,
                "source_path": base,
                "status_filter": status,
            },
            "top_tags": top_tags,
            "samples": table,
        }
        out_path = A.export_summary(payload)
        st.success(f"Saved summary to `{out_path}`")


# --------------------------------------------------------------------------- #
# Main: top navigation bar. Add new capabilities as extra st.Page entries.
# --------------------------------------------------------------------------- #
def main() -> None:
    st.set_page_config(page_title="Trajectory Analyzer", layout="wide")
    A.ensure_default_categories()
    pages = [
        st.Page(
            trajectory_viewer_page,
            title="Trajectory Viewer",
            icon="🛰️",
            default=True,
        ),
        st.Page(categories_page, title="Categories", icon="🏷️"),
        st.Page(summary_page, title="Summary", icon="📊"),
        # Future capabilities go here, e.g.:
        # st.Page(comparison_page, title="Compare", icon="⚖️"),
    ]
    st.navigation(pages, position="top").run()


if __name__ == "__main__":
    main()