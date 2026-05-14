"""Fetch Solidity source for Code4rena cases using the issue body's
"Lines of code" pointer.

c4 issue body convention (verified on a sample): the first markdown section
lists the source URL with a line-range anchor, e.g.

    # Lines of code
    https://github.com/code-423n4/2022-11-paraspace/blob/main/paraspace-core/contracts/misc/NFTFloorOracle.sol#L167-L172

So the algorithm is:
  1. Parse the findings URL → (findings_repo, issue_num)
  2. GET the issue body
  3. Regex-extract the first GitHub blob URL → (source_repo, ref, path, line_start, line_end)
  4. GET the file raw → save as contract_source
  5. Look at lines around (start..end) and find the enclosing `function name(...)`
     → fix `vulnerable_function` when CSV says "Unknown"
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from scripts.source_fetcher import gh_client

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "data" / "contracts" / "raw"

# c4 findings URL: https://github.com/code-423n4/<contest>-findings/issues/<num>
FINDINGS_URL_RE = re.compile(
    r"https://github\.com/(?P<org>code-423n4)/(?P<findings_repo>[^/]+?)-findings/issues/(?P<issue>\d+)"
)

# Source URL inside issue body: accepts any GitHub org/repo, including upstream
# project repos (e.g. https://github.com/Plex-Engineer/lending-market/blob/<sha>/...).
SOURCE_URL_RE = re.compile(
    r"https://github\.com/(?P<org>[^/\s]+)/(?P<repo>[^/\s]+)/blob/(?P<ref>[^/\s]+)/"
    r"(?P<path>[^\s#]+\.sol)(?:#L(?P<start>\d+)(?:[-L]+(?P<end>\d+))?)?"
)

# Enclosing function detection — scan upward for `function NAME(...)`.
# Forgiving: allows multi-line signatures by also matching modifier blocks above.
FUNCTION_DEF_RE = re.compile(
    r"^\s*function\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\(",
    re.MULTILINE,
)


@dataclass
class C4FetchResult:
    incident_id: str
    case_id: str  # full eval_set id (may have _2 suffix)
    status: str = "ok"  # ok | issue_not_found | source_url_not_found | file_404 | unknown_error
    reason: str = ""
    findings_repo: str = ""
    issue_num: int | None = None
    source_repo: str = ""
    source_ref: str = ""
    source_path: str = ""
    line_start: int | None = None
    line_end: int | None = None
    enclosing_function: str = ""
    contract_source_len: int = 0
    contract_source_path: str = ""
    sibling_files: list[str] = field(default_factory=list)


def parse_findings_url(url: str) -> tuple[str, int] | None:
    m = FINDINGS_URL_RE.search(url)
    if not m:
        return None
    return m["findings_repo"], int(m["issue"])


def parse_first_source_url(body: str) -> dict | None:
    """First Solidity blob URL within the issue body."""
    m = SOURCE_URL_RE.search(body)
    if not m:
        return None
    return {
        "org": m["org"],
        "repo": m["repo"],
        "ref": m["ref"],
        "path": m["path"],
        "start": int(m["start"]) if m["start"] else None,
        "end": int(m["end"]) if m["end"] else (int(m["start"]) if m["start"] else None),
    }


def find_enclosing_function(source_text: str, line_no: int) -> str:
    """Return the function name whose definition starts at or above `line_no`.

    Naive: walk upward from line_no, find the first `function X(` line.
    """
    if not source_text or not line_no:
        return ""
    lines = source_text.splitlines()
    # Walk upward
    for i in range(min(line_no - 1, len(lines) - 1), -1, -1):
        m = FUNCTION_DEF_RE.match(lines[i] if i < len(lines) else "")
        if m:
            return m["name"]
    return ""


def gather_siblings_from_tree(tree: tuple[dict, ...], target_path: str, cap: int = 20) -> list[str]:
    """List basenames of .sol files sharing a directory with `target_path`."""
    dir_prefix = "/".join(target_path.split("/")[:-1]) + "/" if "/" in target_path else ""
    sibs: list[str] = []
    for entry in tree:
        if entry.get("type") != "blob":
            continue
        p = entry["path"]
        if not p.endswith(".sol") or p == target_path:
            continue
        # Same-directory only (depth match)
        p_dir = "/".join(p.split("/")[:-1]) + "/" if "/" in p else ""
        if p_dir == dir_prefix:
            sibs.append(p.split("/")[-1])
        if len(sibs) >= cap:
            break
    return sibs


def fetch_one(case: dict) -> tuple[C4FetchResult, Optional[str], list[tuple[str, str]]]:
    """Fetch source for one c4 case.

    Returns (result, primary_source_text, [(sibling_path, sibling_text), ...])
    """
    res = C4FetchResult(
        incident_id=case["incident_id"],
        case_id=case["id"],
    )

    parsed = parse_findings_url(case.get("reference_url", ""))
    if parsed is None:
        res.status = "issue_not_found"
        res.reason = "reference_url not c4 findings format"
        return res, None, []
    findings_repo, issue_num = parsed
    res.findings_repo = findings_repo
    res.issue_num = issue_num

    try:
        issue = gh_client.get_issue("code-423n4", f"{findings_repo}-findings", issue_num)
    except gh_client.GhApiError as e:
        res.status = "issue_not_found"
        res.reason = f"issue API {e.status}: {e.message[:80]}"
        return res, None, []

    src = parse_first_source_url(issue["body"] or "")
    if src is None:
        res.status = "source_url_not_found"
        res.reason = "no GitHub blob URL in issue body"
        return res, None, []

    src_org = src["org"]
    src_repo = src["repo"]
    src_ref = src["ref"]
    src_path = src["path"]
    res.source_repo = f"{src_org}/{src_repo}"
    res.source_ref = src_ref
    res.source_path = src_path
    res.line_start = src["start"]
    res.line_end = src["end"]

    content: str | None = None
    try:
        content = gh_client.get_file_raw(src_org, src_repo, src_path, src_ref)
    except gh_client.GhApiError as primary_err:
        # Fallback: upstream repo may be deleted/private; try c4 contest mirror.
        # c4 mirror = `code-423n4/<contest>` where contest = findings_repo without "-findings".
        fallback_repo = findings_repo  # e.g. "2022-06-canto"
        try:
            fb_default = gh_client.get_default_branch("code-423n4", fallback_repo)
            fb_tree = gh_client.get_repo_tree("code-423n4", fallback_repo, fb_default)
            basename = src_path.split("/")[-1]
            # Score candidates by path suffix match to original path.
            candidates = [t for t in fb_tree
                          if t.get("type") == "blob" and t["path"].endswith("/" + basename)
                          or t["path"] == basename]

            def _suffix_score(p: str) -> int:
                parts_orig = src_path.split("/")
                parts_cand = p.split("/")
                score = 0
                for a, b in zip(reversed(parts_orig), reversed(parts_cand)):
                    if a == b:
                        score += 1
                    else:
                        break
                return score

            candidates.sort(key=lambda t: _suffix_score(t["path"]), reverse=True)
            if candidates:
                fb_path = candidates[0]["path"]
                content = gh_client.get_file_raw(
                    "code-423n4", fallback_repo, fb_path, fb_default
                )
                src_org = "code-423n4"
                src_repo = fallback_repo
                src_ref = fb_default
                src_path = fb_path
                res.source_repo = f"{src_org}/{src_repo} (c4-mirror)"
                res.source_ref = src_ref
                res.source_path = src_path
                res.reason = (
                    f"upstream 404; fell back to c4-mirror code-423n4/{fallback_repo}@{fb_default}"
                )
        except gh_client.GhApiError:
            pass
        if content is None:
            res.status = "file_404"
            res.reason = f"file API {primary_err.status}: {primary_err.message[:80]} (no c4-mirror fallback)"
            return res, None, []

    res.contract_source_len = len(content)

    # Resolve enclosing function (fixes "Unknown" attack_surface)
    if src["end"]:
        res.enclosing_function = find_enclosing_function(content, src["end"]) or find_enclosing_function(content, src["start"])
    elif src["start"]:
        res.enclosing_function = find_enclosing_function(content, src["start"])

    # Siblings via repo tree — same directory only.
    # Uses post-fallback values (src_org/src_repo/src_ref/src_path) so c4-mirror
    # cases read siblings from the mirror, not the dead upstream repo.
    try:
        tree = gh_client.get_repo_tree(src_org, src_repo, src_ref)
        sib_names = gather_siblings_from_tree(tree, src_path, cap=20)
    except gh_client.GhApiError:
        sib_names = []
    sib_texts: list[tuple[str, str]] = []
    dir_prefix = "/".join(src_path.split("/")[:-1])
    for sib_name in sib_names:
        sib_path_full = f"{dir_prefix}/{sib_name}" if dir_prefix else sib_name
        try:
            sib_text = gh_client.get_file_raw(src_org, src_repo, sib_path_full, src_ref)
            sib_texts.append((sib_name, sib_text))
        except gh_client.GhApiError:
            continue
    res.sibling_files = [s[0] for s in sib_texts]

    return res, content, sib_texts


def write_to_raw(
    incident_id: str,
    source_path: str,
    primary_text: str,
    sibling_texts: list[tuple[str, str]],
) -> tuple[str, list[str]]:
    """Write target + siblings under data/contracts/raw/<incident_id>/.

    Returns (target_dest_relpath, [sibling_dest_relpath, ...]).
    """
    case_dir = RAW_DIR / incident_id
    case_dir.mkdir(parents=True, exist_ok=True)
    target_basename = source_path.split("/")[-1]
    target_dst = case_dir / target_basename
    target_dst.write_text(primary_text, encoding="utf-8")
    sib_paths: list[str] = []
    for name, text in sibling_texts:
        dst = case_dir / name
        if dst.exists():
            continue
        dst.write_text(text, encoding="utf-8")
        sib_paths.append(str(dst.relative_to(REPO_ROOT)))
    return str(target_dst.relative_to(REPO_ROOT)), sib_paths
