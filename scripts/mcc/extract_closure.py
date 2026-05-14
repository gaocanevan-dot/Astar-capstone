"""BFS the Solidity import graph to compute a Minimal Compilable Closure.

Given a CaseInfo (target_file + project_root), traverse all `import` statements
recursively. Classify each into:

  - project_files   — local .sol files inside project_root (BFS continues)
  - vendored        — imports satisfied by lib/vendored/* (@openzeppelin/...,
                      solady/, solmate/, forge-std/)
  - external        — imports that escape project_root and aren't vendored
                      (typically project's own deeper structure that wasn't
                      copied into raw/, or interfaces in other folders).
                      These become Day-4 stub candidates.

Result is `within_budget` if total .sol files (target + project_files) is
<= MAX_FILES. Materializer (Day 3) refuses to build above-budget closures.

Import forms covered (Solidity 0.5+):
    import "X.sol";
    import "X.sol" as Y;
    import {A, B} from "X.sol";
    import {A as X, B} from "X.sol";
    import * as Y from "X.sol";
"""

from __future__ import annotations

import argparse
import json
import re
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path

MAX_FILES = 10

# Catches the four import variants. The path is in group 1.
IMPORT_RE = re.compile(
    r"""
    ^\s*import
    \s+
    (?:                                      # optional name list / aliases
        \{[^}]*\}\s+from\s+ |                # {A, B} from
        \*\s+as\s+\w+\s+from\s+ |            # * as Y from
        ["'](?P<path2>[^"']+)["']\s+as\s+\w+ |   # "X.sol" as Y
        (?:                                  # plain `import "X.sol";` — handled by trailing match
        )
    )?
    ["'](?P<path1>[^"']+)["']
    """,
    re.MULTILINE | re.VERBOSE,
)

# Vendored import roots — match against the FIRST path segment.
VENDORED_PREFIXES = (
    "@openzeppelin/",
    "@openzeppelin-contracts/",
    "openzeppelin-contracts/",
    "openzeppelin/",
    "solady/",
    "solmate/",
    "forge-std/",
    "ds-test/",
)


@dataclass
class ImportEdge:
    src_file: str          # relative to project_root, e.g. "TBTCSystem.sol"
    import_path: str       # the literal in the source (e.g. "../IFoo.sol")
    resolved_to: str = ""  # relative path under project_root if found
    classification: str = "external"  # project | vendored | external | not_found


@dataclass
class ClosureResult:
    case_id: str
    incident_id: str
    target_relpath: str    # relative to project_root
    project_files: list[str] = field(default_factory=list)  # rel paths, excludes target
    vendored: list[str] = field(default_factory=list)
    external: list[str] = field(default_factory=list)
    edges: list[ImportEdge] = field(default_factory=list)
    size: int = 0          # target + project_files
    within_budget: bool = False
    reasons: list[str] = field(default_factory=list)


def _extract_import_paths(source: str) -> list[str]:
    """Return all bare import-target strings from a Solidity source."""
    paths: list[str] = []
    for m in IMPORT_RE.finditer(source):
        p = m.group("path1") or m.group("path2")
        if p:
            paths.append(p.strip())
    return paths


def _is_vendored(path: str) -> bool:
    return any(path.startswith(pref) for pref in VENDORED_PREFIXES)


def _resolve_relative(import_path: str, src_file_rel: str, project_root: Path) -> Path | None:
    """Resolve `import_path` relative to `src_file_rel` under `project_root`.

    Returns absolute path if file exists, else None.
    """
    src_dir = (project_root / src_file_rel).parent
    candidate = (src_dir / import_path).resolve()
    if candidate.is_file():
        return candidate
    # Fallback: bare filename — search project_root for any .sol with that basename
    if "/" not in import_path:
        basename = import_path
        matches = list(project_root.rglob(basename))
        # Prefer same-dir match, then shallowest
        if matches:
            matches.sort(key=lambda p: (p.parent != src_dir, len(p.parts)))
            return matches[0]
    return None


def extract_closure(target_file: Path, project_root: Path, *, max_files: int = MAX_FILES) -> ClosureResult:
    """BFS over imports starting at `target_file`. Restricted to project_root."""
    target_file = target_file.resolve()
    project_root = project_root.resolve()
    if not target_file.is_file():
        raise FileNotFoundError(target_file)
    if not project_root.is_dir():
        raise FileNotFoundError(project_root)

    target_rel = str(target_file.relative_to(project_root))

    result = ClosureResult(
        case_id="",
        incident_id="",
        target_relpath=target_rel,
    )

    seen_project: set[str] = {target_rel}
    queue: deque[str] = deque([target_rel])
    vendored_set: set[str] = set()
    external_list: list[str] = []

    while queue:
        if len(seen_project) > max_files:
            result.reasons.append(
                f"max_files={max_files} exceeded; truncating BFS at {len(seen_project)} project files"
            )
            break
        cur_rel = queue.popleft()
        cur_abs = project_root / cur_rel
        if not cur_abs.is_file():
            continue
        text = cur_abs.read_text(encoding="utf-8", errors="replace")
        for imp in _extract_import_paths(text):
            edge = ImportEdge(src_file=cur_rel, import_path=imp)
            if _is_vendored(imp):
                edge.classification = "vendored"
                edge.resolved_to = imp
                vendored_set.add(imp.split("/", 1)[0] + "/")  # group by lib root
                result.edges.append(edge)
                continue
            resolved = _resolve_relative(imp, cur_rel, project_root)
            if resolved is None:
                edge.classification = "not_found"
                external_list.append(imp)
                result.edges.append(edge)
                continue
            # Inside project_root?
            try:
                rel = str(resolved.relative_to(project_root))
            except ValueError:
                edge.classification = "external"
                external_list.append(imp)
                result.edges.append(edge)
                continue
            edge.classification = "project"
            edge.resolved_to = rel
            result.edges.append(edge)
            if rel not in seen_project:
                seen_project.add(rel)
                queue.append(rel)

    project_files = sorted(seen_project - {target_rel})
    result.project_files = project_files
    result.vendored = sorted(vendored_set)
    result.external = sorted(set(external_list))
    result.size = 1 + len(project_files)
    result.within_budget = result.size <= max_files
    return result


def main() -> int:
    """CLI: extract_closure for a single case (looked up via case_loader)."""
    from scripts.mcc.case_loader import load_case

    ap = argparse.ArgumentParser(description="MCC extract_closure CLI")
    ap.add_argument("case_id", help="incident_id or row id (e.g. ACF-001, C4-126_2)")
    ap.add_argument("--max-files", type=int, default=MAX_FILES)
    args = ap.parse_args()

    ci = load_case(args.case_id)
    cr = extract_closure(ci.target_file, ci.project_root, max_files=args.max_files)
    cr.case_id = ci.case_id
    cr.incident_id = ci.incident_id

    out = asdict(cr)
    # Trim edges in JSON output (can be 20+; keep them but cap repr)
    out["edges"] = [
        {"src_file": e["src_file"], "import_path": e["import_path"],
         "classification": e["classification"], "resolved_to": e["resolved_to"]}
        for e in out["edges"]
    ]
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
