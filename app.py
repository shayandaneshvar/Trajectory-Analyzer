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
import report as R
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


@st.cache_data(show_spinner=False)
def _inst_stats(path: str) -> dict:
    return A.instance_stats(path)


def _enrich_failures(failures: list) -> list:
    """Attach per-sample steps / input / output tokens to each failure sample."""
    for grp in failures:
        for s in grp["samples"]:
            st_ = _inst_stats(s["path"])
            s["steps"] = st_.get("steps")
            s["input_tokens"] = st_.get("input_tokens")
            s["output_tokens"] = st_.get("output_tokens")
    return failures


def _repo_bars_html(repos: list) -> str:
    """Colored rows: 'Repo name  x% (M/N)' with a bar width = pass rate."""
    rows = []
    for r in repos:
        total = r["total"] or 1
        rate = r["passed"] / total
        pct = round(rate * 100)
        grad = ("linear-gradient(90deg,#2e7d32,#4caf50)" if rate >= 0.6
                else "linear-gradient(90deg,#e65100,#ffab40)" if rate >= 0.3
                else "linear-gradient(90deg,#c62828,#ff5a65)")
        rows.append(
            '<div style="display:flex;align-items:center;gap:12px;margin:5px 0">'
            f'<div style="width:200px;text-align:right;color:#9498b3;font-size:0.85em;'
            'overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'
            f'{html.escape(r["repo"])}</div>'
            '<div style="flex:1;height:26px;background:#222640;border-radius:6px;overflow:hidden">'
            f'<div style="height:100%;width:{max(6, pct)}%;background:{grad};display:flex;'
            'align-items:center;padding-left:8px;color:#fff;font-size:0.8em;font-weight:600;'
            f'border-radius:6px">{pct}% ({r["passed"]}/{r["total"]})</div></div></div>'
        )
    return "".join(rows)


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


def _gather_report_data(base: str):
    """Stats (from result.json), tag rows, and per-sample tags under ``base``."""
    stats = A.load_run_stats(base)
    assignments = A.collect_assignments(base)
    descriptions = A.category_descriptions()

    counts = Counter()
    by_sample: dict[str, dict] = {}
    for cat_id, items in assignments.items():
        for it in items:
            counts[cat_id] += 1
            s = by_sample.setdefault(it["folder"],
                                     {"name": it["folder"], "path": it["path"], "tags": []})
            s["tags"].append(cat_id)

    tag_rows = [{"tag": c, "count": n, "description": descriptions.get(c, "")}
                for c, n in counts.most_common()]
    samples = [{"name": s["name"], "status": _reward_badge(s["path"]),
                "tags": sorted(s["tags"])}
               for s in sorted(by_sample.values(), key=lambda x: x["name"])]

    # Failed trials grouped by failure reason (tag), most common first.
    failures_by_reason = []
    for cat_id, _n in counts.most_common():
        items = assignments[cat_id]
        failures_by_reason.append({
            "tag": cat_id,
            "description": descriptions.get(cat_id, ""),
            "samples": [{"name": it["folder"], "note": it.get("notes", ""),
                         "status": _reward_badge(it["path"]), "path": it["path"]}
                        for it in items],
        })
    return stats, tag_rows, samples, failures_by_reason


def report_page() -> None:
    st.header("🔬 Report")

    base = st.text_input(
        "Path to a folder of trajectories",
        value=st.session_state.get("traj_base_path", "samples"),
        help="Stats come from this folder's result.json; categories from your tagging.",
    )
    st.session_state["traj_base_path"] = base
    if not base.strip():
        st.info("Enter a path to build a report.")
        return

    # Parent folder name on top of the page.
    from pathlib import Path as _Path
    st.markdown(f"#### 📁 `{_Path(base).name or base}`")

    stats, tag_rows, samples, failures = _gather_report_data(base)
    compare = A.compare_token_steps(base)
    repos = A.repo_breakdown(base)
    report_data = A.load_report(base)

    # Experiment metadata (persisted in traj-report.json).
    exp = report_data.get("experiment", {})
    c1, c2 = st.columns(2)
    exp_name = c1.text_input("Experiment name", value=exp.get("name", ""),
                             key="report_exp_name")
    exp_desc = c2.text_input("Description", value=exp.get("description", ""),
                             key="report_exp_desc")
    if (exp_name != exp.get("name", "")) or (exp_desc != exp.get("description", "")):
        A.set_report_experiment(base, exp_name, exp_desc)

    # Overview stats.
    st.subheader("Overview")
    pr = stats.get("pass_rate")
    m = st.columns(5)
    m[0].metric("Pass rate", f"{pr * 100:.1f}%" if isinstance(pr, (int, float)) else "—")
    m[1].metric("Total", stats.get("total") if stats.get("total") is not None else "—")
    m[2].metric("Passed", stats.get("passed") if stats.get("passed") is not None else "—")
    m[3].metric("Failed", stats.get("failed") if stats.get("failed") is not None else "—")
    m[4].metric("Errored", stats.get("errors") if stats.get("errors") is not None else "—")
    if stats.get("total") is None:
        st.caption("No result.json found at this path — stats come only from tagging.")

    # Failure-by-tag chart.
    st.subheader("Failure categories by tag")
    if tag_rows:
        st.bar_chart({r["tag"]: r["count"] for r in tag_rows}, horizontal=True)
    else:
        st.caption("No tags assigned under this path yet.")

    # Passed vs failed: tokens & steps.
    st.subheader("Passed vs failed (tokens & steps)")
    p, f = compare["passed"], compare["failed"]
    cc1, cc2 = st.columns(2)
    with cc1:
        st.markdown(f"**✅ Passed ({p['n']})**")
        st.metric("Avg input tokens", f"{p['avg_input']:,}" if p["avg_input"] else "—")
        st.metric("Avg output tokens", f"{p['avg_output']:,}" if p["avg_output"] else "—")
        st.metric("Avg steps", p["avg_steps"] if p["avg_steps"] is not None else "—")
    with cc2:
        st.markdown(f"**❌ Failed ({f['n']})**")
        st.metric("Avg input tokens", f"{f['avg_input']:,}" if f["avg_input"] else "—")
        st.metric("Avg output tokens", f"{f['avg_output']:,}" if f["avg_output"] else "—")
        st.metric("Avg steps", f["avg_steps"] if f["avg_steps"] is not None else "—")

    # Per-repository pass rate, as colored rows.
    st.subheader("Analysis by repository")
    if repos:
        st.markdown(_repo_bars_html(repos), unsafe_allow_html=True)
    else:
        st.caption("No repository data available.")

    # Detailed failed trials by reason: an "All" tab plus one tab per reason,
    # each a table of steps / input tokens / output tokens / note.
    st.subheader("Failed trials by reason")
    if failures:
        _enrich_failures(failures)
        all_rows = [{**s, "tag": g["tag"]} for g in failures for s in g["samples"]]
        labels = [f"All ({len(all_rows)})"] + \
                 [f"{g['tag']} ({len(g['samples'])})" for g in failures]
        tabs = st.tabs(labels)

        def _fail_rows(samples, with_reason=False):
            out = []
            for s in samples:
                row = {"name": s["name"]}
                if with_reason:
                    row["reason"] = s.get("tag", "")
                row.update({
                    "status": s.get("status", ""),
                    "steps": s.get("steps"),
                    "input tokens": s.get("input_tokens"),
                    "output tokens": s.get("output_tokens"),
                    "note": s.get("note", ""),
                })
                out.append(row)
            return out

        with tabs[0]:
            st.dataframe(_fail_rows(all_rows, with_reason=True),
                         width="stretch", hide_index=True)
        for tab, grp in zip(tabs[1:], failures):
            with tab:
                if grp["description"]:
                    st.caption(grp["description"])
                st.dataframe(_fail_rows(grp["samples"]),
                             width="stretch", hide_index=True)
    else:
        st.caption("No tagged failures yet.")

    # Action cards (grouped 3 per row).
    st.subheader("Action items")
    _render_report_cards(base, report_data, tag_rows)

    # Export.
    st.subheader("Export")
    if st.button("Export report (HTML)"):
        from datetime import datetime
        meta = {
            "experiment_name": exp_name,
            "description": exp_desc,
            "source_path": base,
            "model": stats.get("model"),
            "exported_at": datetime.now().isoformat(timespec="seconds"),
        }
        html_text = R.build_report_html(
            meta, stats, tag_rows, A.load_report(base).get("cards", []),
            samples, compare=compare, repos=repos, failures_by_reason=failures)
        out_path = A.export_report_html(html_text)
        st.success(f"Saved report to `{out_path}`")
        st.download_button("Download HTML", data=html_text,
                           file_name=out_path.name, mime="text/html")


def _render_report_cards(base: str, report_data: dict, tag_rows: list) -> None:
    cards = report_data.get("cards", [])
    tag_options = [r["tag"] for r in tag_rows] or A_all_tag_ids()

    # Grouped 3 per row, like the example report.
    for row_start in range(0, len(cards), 3):
        cols = st.columns(3)
        for col, i in zip(cols, range(row_start, min(row_start + 3, len(cards)))):
            card = cards[i]
            prio = card.get("priority", "Medium")
            color = R.PRIORITY_COLORS.get(prio, "#6c72ff")
            with col.container(border=True):
                top, btn = st.columns([10, 1], vertical_alignment="center")
                top.markdown(
                    f"**{card.get('title', 'Untitled')}** "
                    f"<span style='color:{color};font-weight:700'>[{prio}]</span>",
                    unsafe_allow_html=True,
                )
                if btn.button("🗑", key=f"delcard::{base}::{i}", help="Delete card"):
                    A.remove_report_card(base, i)
                    st.rerun()
                tags = " ".join(f"`{t}`" for t in card.get("tags", []))
                if tags:
                    st.markdown(tags)
                if card.get("issue"):
                    st.markdown(card["issue"])
                if card.get("action"):
                    st.markdown(f"💡 **How to address:** {card['action']}")

    with st.expander("➕ Add action card"):
        title = st.text_input("Title", key="newcard_title")
        prio = st.selectbox("Priority", R.PRIORITY_ORDER, key="newcard_prio")
        tags = st.multiselect("Related tags", tag_options, key="newcard_tags")
        issue = st.text_area("Issue", key="newcard_issue",
                             placeholder="What's going wrong?")
        action = st.text_area("How to address", key="newcard_action",
                              placeholder="What to do to fix or mitigate it.")
        if st.button("Add card", key="newcard_add"):
            if not title.strip():
                st.warning("Please enter a title.")
            else:
                A.add_report_card(base, {
                    "title": title.strip(), "priority": prio, "tags": tags,
                    "issue": issue.strip(), "action": action.strip(),
                })
                st.rerun()


def A_all_tag_ids() -> list[str]:
    return [A.category_id(c) for c in A.load_categories()]


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
        st.Page(report_page, title="Report", icon="🔬"),
        # Future capabilities go here, e.g.:
        # st.Page(comparison_page, title="Compare", icon="⚖️"),
    ]
    st.navigation(pages, position="top").run()


if __name__ == "__main__":
    main()