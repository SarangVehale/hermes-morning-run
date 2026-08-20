"""End-of-run maintenance pass.

Handles:
  - Log rotation: gzip and delete morning-run-*.log files older than 30 days
  - State backups: snapshot ~/.hermes/state/*.json into the vault under
    `.hermes-backups/state-YYYY-MM-DD.tar.gz` so a vault clone restores them
  - Stub age audit: count concept-stub files >30 days old still empty
  - Broken-link audit: find dangling wikilinks in today's-touched files

Invoke: `python -m morning.maintenance`. Runs after the commit step of
morning-run.sh."""
from __future__ import annotations

import datetime
import gzip
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

from . import config, vault


LOG_DIR = Path.home() / ".hermes" / "logs"
LOG_RETENTION_DAYS = 30
BACKUP_DIR = vault.VAULT / ".hermes-backups"
BACKUP_RETENTION = 14  # keep last N daily snapshots

# Second-location vault backup. rsync to here at end of every morning run with
# --link-dest hardlink snapshots (space-efficient — only changed files take
# new disk space).
#
# Priority order for destination:
#   1. HERMES_VAULT_BACKUP env var (for quick overrides + systemd units)
#   2. `maintenance.vault_backup_root` in ~/.hermes/morning-config.yaml
#   3. ~/backups/vault-ai (built-in default)
#
# Tip: when an external drive is mounted, set the config to that path:
#   maintenance:
#     vault_backup_root: /mnt/external/backups/vault-ai
def _vault_backup_root() -> Path:
    return Path(
        os.environ.get("HERMES_VAULT_BACKUP")
        or config.get("maintenance", "vault_backup_root", default=str(Path.home() / "backups" / "vault-ai"))
    )


def _vault_backup_retention() -> int:
    return int(config.get("maintenance", "vault_backup_retention", default=30))


# -- Log rotation --------------------------------------------------------------

def rotate_logs() -> tuple[int, int]:
    """Gzip morning-run-*.log files older than 1 day; delete .log.gz older
    than LOG_RETENTION_DAYS. Returns (gzipped, deleted)."""
    if not LOG_DIR.exists():
        return (0, 0)
    today = datetime.date.today()
    gzipped = 0
    deleted = 0
    for f in LOG_DIR.glob("morning-run-*.log"):
        try:
            d = datetime.date.fromisoformat(f.stem.split("-", 2)[2])
        except (IndexError, ValueError):
            continue
        if d >= today:
            continue
        gz = f.with_suffix(".log.gz")
        with f.open("rb") as src, gzip.open(gz, "wb") as dst:
            shutil.copyfileobj(src, dst)
        f.unlink()
        gzipped += 1
    for f in LOG_DIR.glob("morning-run-*.log.gz"):
        try:
            d = datetime.date.fromisoformat(f.name.split("-", 2)[2].split(".")[0])
        except (IndexError, ValueError):
            continue
        if (today - d).days > LOG_RETENTION_DAYS:
            f.unlink()
            deleted += 1
    # Same treatment for weekly logs.
    for f in LOG_DIR.glob("weekly-recap-*.log"):
        try:
            d = datetime.date.fromisoformat(f.stem.split("-", 2)[2])
        except (IndexError, ValueError):
            continue
        if d >= today:
            continue
        gz = f.with_suffix(".log.gz")
        with f.open("rb") as src, gzip.open(gz, "wb") as dst:
            shutil.copyfileobj(src, dst)
        f.unlink()
        gzipped += 1
    return (gzipped, deleted)


# -- State backups -------------------------------------------------------------

def rsync_vault_backup() -> tuple[Path | None, str]:
    """Rsync the vault to a second location with hardlink snapshots.

    Layout: VAULT_BACKUP_ROOT/YYYY-MM-DD/<vault contents>
    `--link-dest=../latest` reuses unchanged files from the previous snapshot
    via hardlink, so 30 days of snapshots cost roughly 1 vault's worth of disk
    plus the deltas.

    Returns (snapshot_path, message). snapshot_path is None on skip/error."""
    if shutil.which("rsync") is None:
        return None, "rsync not installed — skipping vault backup"
    backup_root = _vault_backup_root()
    # Don't auto-create the destination if its parent doesn't exist — that's
    # the "external drive not mounted" signal. Better to skip noisily than
    # quietly create a directory on the wrong filesystem.
    if not backup_root.parent.exists():
        return None, f"backup root parent missing: {backup_root.parent} (external drive unmounted?)"
    backup_root.mkdir(parents=True, exist_ok=True)
    today = vault.now_ist().date().isoformat()
    today_dir = backup_root / today
    if today_dir.exists():
        # Already backed up today — refresh (overwrite). Cheap.
        pass
    latest_link = backup_root / "latest"
    cmd = [
        "rsync", "-a",
        "--delete",
        "--exclude=.git/",                        # vault git history is in GitHub
        "--exclude=.hermes-backups/",             # avoid backup-of-backup loops
        "--exclude=.hermes-reading-log.json",     # per-device, regen on demand
        "--exclude=.obsidian/workspace*.json",    # per-device UI state
        "--exclude=.obsidian/cache/",
    ]
    if latest_link.exists():
        cmd += [f"--link-dest={latest_link.resolve()}"]
    cmd += [str(vault.VAULT) + "/", str(today_dir) + "/"]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=300)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        return None, f"rsync failed: {e}"
    # Update `latest` symlink.
    if latest_link.is_symlink() or latest_link.exists():
        latest_link.unlink()
    latest_link.symlink_to(today, target_is_directory=True)
    # Prune old snapshots.
    snaps = sorted(
        (p for p in backup_root.iterdir() if p.is_dir() and not p.is_symlink()),
        reverse=True,
    )
    pruned = 0
    retention = _vault_backup_retention()
    for old in snaps[retention:]:
        shutil.rmtree(old, ignore_errors=True)
        pruned += 1
    return today_dir, f"snapshot at {today_dir}, pruned {pruned} old"


def snapshot_state() -> Path | None:
    """Tar+gz ~/.hermes/state/ into BACKUP_DIR. Prunes old snapshots."""
    state_dir = vault.STATE_DIR
    if not state_dir.exists():
        return None
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    today = vault.now_ist().date().isoformat()
    out = BACKUP_DIR / f"state-{today}.tar.gz"
    with tarfile.open(out, "w:gz") as tar:
        for p in sorted(state_dir.rglob("*")):
            if p.is_file():
                tar.add(p, arcname=p.relative_to(state_dir))
    # Prune
    snaps = sorted(BACKUP_DIR.glob("state-*.tar.gz"), reverse=True)
    for old in snaps[BACKUP_RETENTION:]:
        old.unlink()
    return out


# -- Stub age audit ------------------------------------------------------------

def stale_stubs() -> list[Path]:
    """List concept-stub files (frontmatter only, no body) older than 30 days."""
    cutoff = vault.now_ist().date() - datetime.timedelta(days=30)
    cutoff_dt = datetime.datetime.combine(cutoff, datetime.time.min)
    out: list[Path] = []
    for root in (vault.VAULT / "07 References", vault.VAULT / "04 People", vault.VAULT / "06 Research"):
        if not root.exists():
            continue
        for md in root.rglob("*.md"):
            try:
                ctime = datetime.datetime.fromtimestamp(md.stat().st_ctime)
            except OSError:
                continue
            if ctime > cutoff_dt:
                continue
            text = vault.read(md)
            fm_end = text.find("\n---\n", 3)
            body = text[fm_end + len("\n---\n"):] if fm_end != -1 else text
            if not body.strip():
                out.append(md)
    return out


# -- Broken-link audit ---------------------------------------------------------

_WIKILINK = re.compile(r"\[\[([^\]|#]+?)(?:\|[^\]]+)?\]\]")


def _strip_prompt_callouts(text: str) -> str:
    """Remove `> [!prompt]-` callout blocks before scanning for wikilinks.
    Those blocks are agent-instruction examples (`[[Note|↗]]`, `[[Name]]`) and
    aren't meant to resolve to real notes."""
    lines = text.splitlines()
    out: list[str] = []
    skipping = False
    for line in lines:
        if line.startswith("> [!prompt]"):
            skipping = True
            continue
        if skipping:
            if line.startswith(">"):
                continue
            skipping = False
        out.append(line)
    return "\n".join(out)


def dangling_wikilinks() -> dict[str, list[Path]]:
    """Map dangling-target → list of files referencing it. Dangling = wikilink
    target with no note file. Concept-stubs.py creates stubs from these on the
    next morning run, so this audit just flags them for visibility."""
    existing: set[str] = set()
    for md in vault.VAULT.rglob("*.md"):
        if any(part.startswith(".") for part in md.parts):
            continue
        existing.add(md.stem)

    placeholder_re = re.compile(r"^(Name|Note|Creator|Source|Title|Topic|date|MM-DD-YY|YYYY-MM-DD)\b", re.IGNORECASE)

    by_target: dict[str, list[Path]] = {}
    for md in vault.VAULT.rglob("*.md"):
        if any(part.startswith(".") for part in md.parts):
            continue
        raw = vault.read(md)
        text = _strip_prompt_callouts(raw)
        for m in _WIKILINK.finditer(text):
            target = m.group(1).strip()
            if not target or target in existing or placeholder_re.match(target):
                continue
            by_target.setdefault(target, []).append(md)
    return by_target


# -- Entry point ---------------------------------------------------------------

def run() -> dict:
    gzipped, log_deleted = rotate_logs()
    snap = snapshot_state()
    backup_path, backup_msg = rsync_vault_backup()
    stubs = stale_stubs()
    dangling = dangling_wikilinks()
    report = {
        "logs_gzipped": gzipped,
        "logs_deleted": log_deleted,
        "state_snapshot": str(snap) if snap else None,
        "vault_backup": str(backup_path) if backup_path else None,
        "vault_backup_msg": backup_msg,
        "stale_stubs_30d": len(stubs),
        "dangling_targets_unique": len(dangling),
        "dangling_top_referenced": [
            {"target": t, "refs": len(srcs)}
            for t, srcs in sorted(dangling.items(), key=lambda kv: -len(kv[1]))[:5]
        ],
    }
    return report


def main() -> int:
    report = run()
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
