#!/usr/bin/env python3
"""
connection-finder.py — End-of-run pass that finds notes the agent could have
wikilinked but didn't. Appends suggestions to today's notes only.

This is a deliberately simple version: pure string matching, no embeddings.
Reasoning:
- Embeddings add a 1-2 GB dependency and a slow first-load.
- For a personal vault of <10k notes, exact-match against existing note
  basenames covers most legitimate missed connections.
- False-positive rate from substring matching is low if we require
  word-boundary matches and skip common-English-word note titles.

If you want to upgrade to semantic matching later, swap this script for one
using sentence-transformers; the integration point in morning-run.sh stays
the same.
"""

import argparse
import re
import datetime
from pathlib import Path
from typing import List, Set

WIKILINK = re.compile(r"\[\[([^\]]+?)\]\]")

# Common words to skip even if they happen to be note titles.
COMMON_WORDS = {
    "the", "and", "or", "with", "from", "into", "for", "this", "that",
    "what", "when", "where", "why", "how", "can", "may", "will", "today",
    "yesterday", "tomorrow", "all", "some", "any", "one", "two", "many",
}


def list_note_basenames(vault: Path) -> List[str]:
    """All note basenames in the vault."""
    names = []
    for md in vault.rglob("*.md"):
        if any(part.startswith(".") for part in md.parts):
            continue
        name = md.stem
        if name.lower() in COMMON_WORDS:
            continue
        if len(name) < 3:
            continue
        names.append(name)
    # Sort by length descending so we match longer names first (e.g.
    # "neutral atoms" before "atoms")
    names.sort(key=len, reverse=True)
    return names


def find_unlinked_mentions(text: str, names: List[str], already_linked: Set[str]) -> List[str]:
    """Return note names mentioned in text but not currently wikilinked."""
    suggestions = []
    # Strip out existing wikilink contents so we don't match inside them.
    stripped = WIKILINK.sub(" ", text)
    for name in names:
        if name in already_linked:
            continue
        # Word-boundary, case-insensitive match
        pattern = r"\b" + re.escape(name) + r"\b"
        if re.search(pattern, stripped, re.IGNORECASE):
            suggestions.append(name)
            already_linked.add(name)  # don't suggest same name twice
    return suggestions


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", required=True, type=Path)
    ap.add_argument("--today-only", action="store_true",
                    help="only process files modified today")
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args()

    vault = args.vault.expanduser().resolve()
    names = list_note_basenames(vault)
    if args.verbose:
        print(f"connection-finder: scanning against {len(names)} note basenames")

    today = datetime.date.today()
    total_appended = 0

    for md in vault.rglob("*.md"):
        if any(part.startswith(".") for part in md.parts):
            continue
        if args.today_only:
            mtime = datetime.date.fromtimestamp(md.stat().st_mtime)
            if mtime != today:
                continue

        try:
            text = md.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        # What's already wikilinked in this file
        already = {m.group(1).strip() for m in WIKILINK.finditer(text)}
        # Also skip the note's own name
        already.add(md.stem)

        # Skip the suggestions section if already appended
        if "## Suggested connections" in text:
            continue

        suggestions = find_unlinked_mentions(text, names, already)
        if not suggestions:
            continue

        # Cap at 5 suggestions per file to avoid noise
        suggestions = suggestions[:5]

        # Append a suggestions section
        addendum = "\n\n## Suggested connections\n\n"
        addendum += "*Notes mentioned but not wikilinked. Add manually if relevant.*\n\n"
        for s in suggestions:
            addendum += f"- [[{s}]]\n"

        with md.open("a", encoding="utf-8") as f:
            f.write(addendum)
        total_appended += 1
        if args.verbose:
            print(f"  appended {len(suggestions)} suggestions to {md.relative_to(vault)}")

    print(f"connection-finder: appended suggestions to {total_appended} file(s)")


if __name__ == "__main__":
    main()
