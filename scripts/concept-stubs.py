#!/usr/bin/env python3
"""
concept-stubs.py — Scan the vault for dangling wikilinks and create empty
stub files for each one. Stubs contain frontmatter only; no AI content.

Run at the end of the morning workflow (after Hermes has written today's
notes). Routes stubs to the right folder based on heuristics:

- 04 People/    — names that look like people (FirstName LastName, etc.)
- 06 Research/  — arXiv IDs (arXiv:NNNN.NNNNN)
- 07 References/ — everything else (concepts, tools, companies, places)

Idempotent: if a stub already exists, skip it.
"""

import argparse
import re
import datetime
from pathlib import Path
from typing import Set, Tuple

WIKILINK = re.compile(r"\[\[([^\]|#]+?)(?:\|[^\]]+)?\]\]")

ARXIV_PATTERN = re.compile(r"^arXiv[ :]?\d{4}\.\d{4,5}(v\d+)?$", re.IGNORECASE)
PERSON_PATTERN = re.compile(r"^[A-Z][a-zà-ÿ]+(?:[\s'-][A-Z][a-zà-ÿ]+){1,3}$")

# Reject wikilink targets that are obviously malformed (partial matches against
# unbalanced source content). These would produce un-openable filenames.
INVALID_CHARS = re.compile(r"[\[\]/\\<>:\"|*?]")


def _is_valid_target(target: str) -> bool:
    if not target or len(target) > 120:
        return False
    if INVALID_CHARS.search(target):
        return False
    if target.endswith(".md") or target.endswith("—") or target.endswith("-"):
        return False
    if "  " in target:  # double space — usually a tokenisation artifact
        return False
    return True


def find_all_wikilinks(vault: Path) -> Set[str]:
    """Return every wikilink target referenced anywhere in the vault."""
    targets = set()
    for md in vault.rglob("*.md"):
        if any(part.startswith(".") for part in md.parts):
            continue
        try:
            text = md.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for m in WIKILINK.finditer(text):
            target = m.group(1).strip()
            if target:
                targets.add(target)
    return targets


def find_existing_notes(vault: Path) -> Set[str]:
    """Set of all existing note basenames (without .md)."""
    existing = set()
    for md in vault.rglob("*.md"):
        if any(part.startswith(".") for part in md.parts):
            continue
        existing.add(md.stem)
    return existing


def classify(target: str) -> str:
    """Decide which folder a stub for this target belongs in."""
    if ARXIV_PATTERN.match(target):
        return "06 Research"
    if PERSON_PATTERN.match(target):
        return "04 People"
    return "07 References"


def create_stub(vault: Path, target: str, folder: str, source: str = "") -> bool:
    """Create an empty stub. Returns True if created, False if exists."""
    stub_path = vault / folder / f"{target}.md"
    if stub_path.exists():
        return False
    stub_path.parent.mkdir(parents=True, exist_ok=True)
    today = datetime.date.today().isoformat()
    content = "---\n"
    content += f"created: {today}\n"
    content += f"updated: {today}\n"
    content += "unread: true\n"
    content += "stub: true\n"
    if source:
        content += f"first_referenced_in: \"[[{source}]]\"\n"
    content += "---\n\n"
    # Body is genuinely empty. User fills it from real sources.
    stub_path.write_text(content, encoding="utf-8")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", required=True, type=Path,
                    help="path to the vault root")
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args()

    vault = args.vault.expanduser().resolve()
    if not (vault / ".obsidian").exists():
        print(f"WARNING: {vault} doesn't look like an Obsidian vault "
              f"(.obsidian/ not found). Continuing anyway.")

    wikilinks = find_all_wikilinks(vault)
    existing = find_existing_notes(vault)

    dangling = wikilinks - existing
    if args.verbose:
        print(f"Found {len(wikilinks)} wikilinks, "
              f"{len(existing)} existing notes, "
              f"{len(dangling)} dangling.")

    created_count = 0
    by_folder = {"04 People": 0, "06 Research": 0, "07 References": 0}
    # Cap stub creation per run to avoid landing hundreds at once after a long
    # gap. Lift the cap if the vault catches up.
    STUB_CAP = 80
    for target in sorted(dangling):
        if created_count >= STUB_CAP:
            break
        if not _is_valid_target(target):
            continue
        # Skip wikilinks that point to existing files in any subdir.
        # NOTE: previously used `any(rglob(...))` over a generator, which was
        # always truthy — that meant this check skipped EVERY target. Now we
        # materialize each rglob result.
        already_elsewhere = False
        for sub in ("01 Updates", "02 Daily", "03 Meetings", "05 Projects", "08 Summaries"):
            if next((vault / sub).rglob(f"{target}.md"), None) is not None:
                already_elsewhere = True
                break
        if already_elsewhere:
            continue
        folder = classify(target)
        if create_stub(vault, target, folder):
            created_count += 1
            by_folder[folder] += 1
            if args.verbose:
                print(f"  created: {folder}/{target}.md")

    print(f"concept-stubs: created {created_count} new stubs "
          f"(People: {by_folder['04 People']}, "
          f"Research: {by_folder['06 Research']}, "
          f"References: {by_folder['07 References']})")


if __name__ == "__main__":
    main()
