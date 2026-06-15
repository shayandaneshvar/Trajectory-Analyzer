"""Trajectory failure-categorization storage.

Two pieces of state:

* **Category catalog** — the master list of category *definitions*, stored once
  for the whole project in ``resources/categories.json``. Each category is
  ``{"type", "name", "description"}`` and is identified by ``"type:name"``
  (e.g. ``"fail:wrong_test_setup"``).

* **Assignments** — which folder was tagged with which categories (plus optional
  notes), stored in a ``traj-analysis.json`` that lives either next to a parent
  run's ``result.json`` or inside an individual instance folder.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent
RESOURCES_DIR = PROJECT_ROOT / "resources"
CATEGORIES_FILE = RESOURCES_DIR / "categories.json"
SUMMARIES_DIR = PROJECT_ROOT / "out" / "summaries"

ANALYSIS_FILENAME = "traj-analysis.json"
ANALYSIS_SCHEMA = "traj-analysis-v1"

DEFAULT_TYPE = "fail"

# Seed categories. These exist in code only to populate categories.json the
# first time (or to backfill any that are missing). At runtime the catalog is
# always read from categories.json — these are never merged in on read.
DEFAULT_CATEGORIES: list[dict[str, Any]] = [
    {"type": "fail", "name": "prompts_user",
     "description": "asks user to put some sort of input to continue"},
    {"type": "fail", "name": "adds_env_var",
     "description": "adds an environment variable necessary to be used in order to "
                    "run the project, which the benchmark doesn't know about"},
    {"type": "fail", "name": "truncated",
     "description": "truncated early and stopped generation halfway"},
    {"type": "fail", "name": "empty_tool_call",
     "description": "tool call called doesn't have any body"},
    {"type": "fail", "name": "confident_without_checking",
     "description": "doesn't check the generated code and assumes it works correctly"},
    {"type": "fail", "name": "empty_tool_response",
     "description": "tool response is empty"},
    {"type": "fail", "name": "uses_git_after_done",
     "description": "uses git after being done with the task for additional "
                    "unnecessary actions"},
]


# --------------------------------------------------------------------------- #
# Category catalog
# --------------------------------------------------------------------------- #
def category_id(cat: dict[str, Any]) -> str:
    return f"{cat.get('type', DEFAULT_TYPE)}:{cat.get('name', '')}"


def load_categories() -> list[dict[str, Any]]:
    """Read the full catalog from categories.json (the single source of truth)."""
    if not CATEGORIES_FILE.is_file():
        return []
    try:
        data = json.loads(CATEGORIES_FILE.read_text())
    except (ValueError, OSError):
        return []
    return data.get("categories", []) if isinstance(data, dict) else []


def save_categories(categories: list[dict[str, Any]]) -> None:
    RESOURCES_DIR.mkdir(parents=True, exist_ok=True)
    CATEGORIES_FILE.write_text(
        json.dumps({"categories": categories}, indent=2, ensure_ascii=False)
    )


def ensure_default_categories() -> None:
    """Backfill categories.json with any seed categories it's missing."""
    categories = load_categories()
    existing = {category_id(c) for c in categories}
    changed = False
    for default in DEFAULT_CATEGORIES:
        if category_id(default) not in existing:
            categories.append(dict(default))
            existing.add(category_id(default))
            changed = True
    if changed or not CATEGORIES_FILE.is_file():
        save_categories(categories)


def add_category(name: str, description: str, type_: str = DEFAULT_TYPE) -> str:
    """Add a category to the catalog (idempotent by id). Returns its id."""
    name = name.strip()
    type_ = (type_ or DEFAULT_TYPE).strip()
    if not name:
        raise ValueError("Category name cannot be empty.")

    categories = load_categories()
    new = {"type": type_, "name": name, "description": description.strip()}
    new_id = category_id(new)
    for existing in categories:
        if category_id(existing) == new_id:
            if description.strip():
                existing["description"] = description.strip()
            save_categories(categories)
            return new_id
    categories.append(new)
    save_categories(categories)
    return new_id


def category_descriptions() -> dict[str, str]:
    return {category_id(c): c.get("description", "") for c in load_categories()}


# --------------------------------------------------------------------------- #
# Where the traj-analysis.json lives + the key for this trajectory
# --------------------------------------------------------------------------- #
def _instance_root(traj_path: Path) -> Path:
    """Folder that contains the trajectory (parent of ``agent/``)."""
    tp = Path(traj_path)
    if tp.name == "trajectory.json" and tp.parent.name == "agent":
        return tp.parent.parent
    return tp.parent


def analysis_target(base_path: str, chosen_path: str, traj_path: Path) -> tuple[Path, str]:
    """Return ``(analysis_file, entry_key)`` for the loaded trajectory.

    If the loader's base path is a parent run folder (it has a ``result.json``
    next to it), the analysis file lives there and the key is the selected
    instance's folder name. Otherwise it lives inside the folder containing the
    trajectory, keyed by that folder's name.
    """
    base = Path(base_path).expanduser()
    if base.is_dir() and (base / "result.json").is_file():
        return base / ANALYSIS_FILENAME, Path(chosen_path).name

    root = _instance_root(traj_path)
    return root / ANALYSIS_FILENAME, root.name


# --------------------------------------------------------------------------- #
# Assignments (traj-analysis.json)
# --------------------------------------------------------------------------- #
def load_analysis(path: Path) -> dict[str, Any]:
    if Path(path).is_file():
        try:
            data = json.loads(Path(path).read_text())
            if isinstance(data, dict):
                data.setdefault("schema", ANALYSIS_SCHEMA)
                data.setdefault("entries", {})
                return data
        except (ValueError, OSError):
            pass
    return {"schema": ANALYSIS_SCHEMA, "entries": {}}


def save_analysis(path: Path, data: dict[str, Any]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False))


def get_categories_for(data: dict[str, Any], key: str) -> list[dict[str, Any]]:
    entry = data.get("entries", {}).get(key, {})
    return list(entry.get("categories", []))


def assign_category(path: Path, key: str, cat_id: str, notes: str = "") -> None:
    """Add (or update notes for) a category on a folder, then persist."""
    data = load_analysis(path)
    entry = data.setdefault("entries", {}).setdefault(key, {"categories": []})
    for item in entry["categories"]:
        if item.get("id") == cat_id:
            item["notes"] = notes
            break
    else:
        entry["categories"].append({"id": cat_id, "notes": notes})
    save_analysis(path, data)


def remove_category(path: Path, key: str, cat_id: str) -> None:
    data = load_analysis(path)
    entry = data.get("entries", {}).get(key)
    if not entry:
        return
    entry["categories"] = [c for c in entry.get("categories", []) if c.get("id") != cat_id]
    save_analysis(path, data)


# --------------------------------------------------------------------------- #
# Aggregation for the Categories overview page
# --------------------------------------------------------------------------- #
def collect_assignments(base_path: str, max_files: int = 2000) -> dict[str, list[dict[str, Any]]]:
    """Scan ``traj-analysis.json`` files under ``base_path``.

    Returns a mapping ``category_id -> [{"folder", "notes", "file"}, ...]``.
    """
    base = Path(base_path).expanduser()
    by_category: dict[str, list[dict[str, Any]]] = {}
    if not base.exists():
        return by_category

    # (analysis_file, only_folder) pairs. ``only_folder`` restricts which
    # entries we read from that file (used when pointing at a single instance,
    # whose tags live in the parent's traj-analysis.json next to result.json).
    sources: list[tuple[Path, str | None]] = []
    if base.is_file() and base.name == ANALYSIS_FILENAME:
        sources.append((base, None))
    elif base.is_dir():
        for f in sorted(base.rglob(ANALYSIS_FILENAME))[:max_files]:
            sources.append((f, None))
        # Pointed at a single instance? Also read the parent's file, but only
        # this instance's entry.
        parent_file = base.parent / ANALYSIS_FILENAME
        if parent_file.is_file():
            sources.append((parent_file, base.name))

    seen_files: set[Path] = set()
    for f, only_folder in sources:
        data = load_analysis(f)
        fdir = Path(f).parent
        for folder, entry in data.get("entries", {}).items():
            if only_folder is not None and folder != only_folder:
                continue
            marker = (f, folder)
            if marker in seen_files:
                continue
            seen_files.add(marker)
            # Resolve the folder's path: it's the analysis file's own directory
            # (instance case) or a sub-folder of it (parent-run case).
            folder_path = fdir if fdir.name == folder else (fdir / folder)
            for item in entry.get("categories", []):
                cat_id = item.get("id")
                if not cat_id:
                    continue
                by_category.setdefault(cat_id, []).append(
                    {"folder": folder, "notes": item.get("notes", ""),
                     "file": str(f), "path": str(folder_path)}
                )
    return by_category


# --------------------------------------------------------------------------- #
# Summary export
# --------------------------------------------------------------------------- #
def export_summary(payload: dict[str, Any]) -> Path:
    """Write a summary ``payload`` to out/summaries/<datetime>.json.

    Stamps ``payload['meta']['exported_at']`` and names the file by the current
    local datetime. Returns the written path.
    """
    now = datetime.now()
    payload.setdefault("meta", {})["exported_at"] = now.isoformat(timespec="seconds")

    SUMMARIES_DIR.mkdir(parents=True, exist_ok=True)
    path = SUMMARIES_DIR / f"{now.strftime('%Y-%m-%dT%H-%M-%S')}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    return path
