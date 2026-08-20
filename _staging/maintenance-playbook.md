# Maintenance playbook — vault-ai daily briefing

Post-deployment reference. Every operation you'll realistically need.

## Where things live

| Thing | Path |
|---|---|
| Vault | `~/vault-ai/` (also at `github.com/YOUR_GH_USER/vault-ai` once pushed) |
| Vault conventions for agent | `~/vault-ai/HERMES.md` (read on every agent run) |
| Watchlist (creators) | `~/vault-ai/_watchlist.yaml` |
| Tool watchlist (GitHub repos) | `~/vault-ai/_tools.yaml` |
| Tasks file | `~/vault-ai/📋 Tasks.md` |
| Stream notes (per-skill specs) | `~/vault-ai/01 Updates/*.md` |
| Morning + weekly scripts | `~/scripts/morning-run.sh`, `~/scripts/weekly-recap.sh` |
| Hermes config | `~/.hermes/config.yaml` (4 model + 8 MCP) |
| Hermes persona | `~/.hermes/SOUL.md` (points at HERMES.md) |
| Hermes skills | `~/.hermes/skills/` |
| Hermes logs | `~/.hermes/logs/agent.log` and `~/.hermes/logs/morning-run-YYYY-MM-DD.log` |
| MCP OAuth tokens | `~/.hermes/mcp-tokens/*.json` |
| Cloud Console OAuth client | `vault-ai` project, OAuth client `vault-ai-hermes` |
| Bundle (source-of-truth specs) | `~/Development/hermes-vault-setup/` |
| HP-side systemd units | `/etc/systemd/system/hermes-{morning,weekly}.{service,timer}` |
| ROG-side systemd units | `~/.config/systemd/user/llama-server-{primary,fast}.service` (on rog) |

## Day-to-day — nothing

Wake up. Open Obsidian. Read the dashboard. That's it. The morning run at 05:55 IST has already populated everything.

When you tick checkboxes (emails done, events attended, tasks closed), Obsidian Git auto-pushes them up within ~10 min on phone or desktop. They survive the next morning run because the morning script doesn't touch those checkboxes — it only adds new entries.

## Common operations

### Manually fire a morning run

If you skipped a day (computer was off, internet was out, you want to re-run after editing a callout):

```
DRY_RUN=1 ~/scripts/morning-run.sh   # to test without push
~/scripts/morning-run.sh             # full real run (commits + pushes + suspends ROG)
```

Both stream output to `~/.hermes/logs/morning-run-$(date +%Y-%m-%d).log`. Tail it from a second terminal:

```
tail -f ~/.hermes/logs/morning-run-$(date +%Y-%m-%d).log
```

### Manually fire a weekly recap

```
~/scripts/weekly-recap.sh
```

### Skip a day (disable timer temporarily)

Traveling, taking a break, etc.:

```
sudo systemctl stop hermes-morning.timer
```

Resume:

```
sudo systemctl start hermes-morning.timer
```

To skip permanently and turn the system off:

```
sudo systemctl disable --now hermes-morning.timer hermes-weekly.timer
ssh rog "systemctl --user disable --now llama-server-primary.service llama-server-fast.service"
```

### See whether the timer is going to fire

```
systemctl list-timers 'hermes-*' --no-pager
```

Shows next-fire times and last-fire times for both morning and weekly.

### Add a new YouTube creator to the watchlist

Open `~/vault-ai/_watchlist.yaml`. Add a YAML entry under `youtube:`:

```yaml
  - name: New Creator Name
    channel_id: null   # leave null; agent resolves on next run
```

Or if you know the channel ID (looks like `UCxxxxxxxxxxxx` — get it from a channel's RSS URL by viewing source on the channel page and grepping for `"channelId":"UC...`), include it directly:

```yaml
  - name: New Creator Name
    channel_id: UC...
```

Commit (Obsidian Git auto-commits within 10 min if you edited from Obsidian, or `cd ~/vault-ai && git add -A && git commit -m "watchlist: add X" && git push`).

Tomorrow's morning run picks it up automatically.

### Add a new GitHub repo to release tracking

Open `~/vault-ai/_tools.yaml`. Add under `tools:`:

```yaml
  - repo: owner/name
    name: Display Name
    reason: why I care
    critical: false   # true if breaking releases would break my morning workflow
```

Commit. Tomorrow's release skill picks it up.

### Add a new Gmail account

1. Add to Hermes config: `~/.hermes/config.yaml`. Add a new entry under `mcp_servers:` modeled on `gmail_work`:
   ```yaml
     gmail_NEW:
       url: https://gmailmcp.googleapis.com/mcp/v1
       auth: oauth
       oauth:
         client_id: <same-as-existing>
         client_secret: <same-as-existing>
       timeout: 300
   ```
2. In Cloud Console: add this email to the OAuth consent screen's Test Users list (if not already).
3. Bootstrap the OAuth `.client.json`:
   ```
   cp ~/.hermes/mcp-tokens/gmail_work.client.json ~/.hermes/mcp-tokens/gmail_NEW.client.json
   ```
4. Run the OAuth grant:
   ```
   python3 ~/scripts/oauth-grant.py gmail_NEW
   ```
   Browser opens, log in as the new account, Allow.
5. Update `📌 Daily Brief.md` callout's email-section list to mention the new account.
6. Verify: `hermes mcp list` should show the new server as ✓ enabled.

Same procedure for adding a new Calendar account (use `calendar_*` prefix, point at `https://calendarmcp.googleapis.com/mcp/v1`, scopes are calendar-readonly).

### Remove a Gmail or Calendar account

1. Delete its entry from `mcp_servers:` in `~/.hermes/config.yaml`.
2. Delete its token files:
   ```
   rm ~/.hermes/mcp-tokens/<name>.{json,client.json,meta.json}
   ```
3. Update the Brief / Triage / Weekly callouts to remove references.
4. Optional: in Cloud Console, revoke the user grant via myaccount.google.com → Security → Third-party apps → vault-ai-hermes.

### Rotate the OAuth client (recommended every 12 months)

1. Cloud Console → APIs & Services → Credentials → existing `vault-ai-hermes` client → Reset secret (or delete and create new).
2. Replace both fields in `~/.hermes/config.yaml`:
   ```
   sed -i \
     -e "s|<old_client_id>|<new_client_id>|g" \
     -e "s|<old_secret>|<new_secret>|g" \
     ~/.hermes/config.yaml
   ```
3. Re-run all OAuth grants (tokens cached with the old client become invalid):
   ```
   for name in gmail_work gmail_personal gmail_iitm gmail_nfsu calendar_work calendar_personal calendar_iitm calendar_nfsu; do
     python3 ~/scripts/oauth-grant.py $name
   done
   ```

### Swap models (primary ↔ small)

For quick verification work on the small Qwen 3B model:

```
~/scripts/hermes-fast       # for interactive TUI
~/scripts/hermes-fast -z "<prompt>"   # for one-shot
```

The wrapper swaps config to point at port 8081 (Qwen 3B) and reverts on exit. **Caveat**: if your shell process gets SIGKILL'd, the trap doesn't fire and config stays in fast mode. Recover with:

```
hermes config set model.default "gemma-4-26B-A4B-it-UD-Q4_K_XL.gguf"
hermes config set model.base_url "http://rog:8080/v1"
```

### Check what model is currently configured

```
grep -E '^  (default|base_url):' ~/.hermes/config.yaml | head -2
```

### Wake / suspend the ROG manually

```
ssh rog "sudo systemctl suspend"     # suspend now
ssh rog "sudo systemctl poweroff"    # full shutdown
```

Wake: just open the lid / press power button. ROG hostname `rog` is an SSH alias from `~/.ssh/config`.

### Re-download a model from HuggingFace

Existing pattern (replace path + model as needed):

```
ssh rog 'export HF_HUB_CACHE=$HOME/models/.cache
~/.local/bin/hf download <repo> --include "<glob>" --local-dir /home/USER/models/<name>'
```

## Troubleshooting

### Timer fires but produces garbage

Read the script log:

```
tail -200 ~/.hermes/logs/morning-run-$(date +%Y-%m-%d).log
```

If the agent confesses "simulated fetches" or "manually completed", it hallucinated — the anti-fabrication rule in HERMES.md and the script prompt is supposed to prevent this, but if it slipped through:

1. **Revert the bad commit**: `cd ~/vault-ai && git reset --hard HEAD~1 && git push --force-with-lease origin main`. Mobile clients will hard-reset on their next pull.
2. **Disable the timer** until you can iterate: `sudo systemctl stop hermes-morning.timer`.
3. **Iterate on the prompt callouts** in `01 Updates/*.md` — strengthen the anti-fabrication directives, add more concrete "you MUST call tool X" wording.
4. **Re-run as dry-run** until you trust the output: `DRY_RUN=1 ~/scripts/morning-run.sh`.

### ROG didn't auto-shut-down after the morning run

The script does `ssh rog "sudo systemctl poweroff"` at the end. If it failed:

- `sudo -n -l` on ROG should show `NOPASSWD: /usr/bin/systemctl suspend, /usr/bin/systemctl poweroff` — if not, sudoers is missing the entry. Re-add per the original Phase 5 setup.
- SSH key auth from HP to ROG must be working. Test: `ssh rog hostname`.

### Morning run starts but ROG model server is unreachable

If you see `WARNING: ROG model server unreachable. Hermes will use its configured fallback.` in the log: ROG is off, suspended, or its `llama-server-primary` user-service crashed.

```
ssh rog "systemctl --user status llama-server-primary"   # see if alive
ssh rog "systemctl --user restart llama-server-primary"  # restart it
```

If the model fails to load after restart, check journal:

```
ssh rog "journalctl --user -u llama-server-primary -n 40 --no-pager"
```

The fallback chain: Hermes will try `fallback_providers` (Ollama hermes3:8b on HP) — usable but slow. Travel days are the design use-case.

### Gmail MCP returns 401 / "auth expired"

OAuth tokens normally refresh automatically using the stored refresh token. If you see persistent auth errors for one server, manually re-grant:

```
python3 ~/scripts/oauth-grant.py gmail_<name>
```

Re-do for any other servers that started failing — Google sometimes revokes refresh tokens if you change account passwords, change recovery settings, or after long periods of inactivity.

### Vault disk usage growing

Stream notes accumulate forever (each day's entry added at the top). The big disk eater is `08 Summaries/` — each YouTube summary is a separate file. Periodically:

```
du -sh ~/vault-ai/{02 Daily,03 Meetings,04 People,05 Projects,06 Research,07 References,08 Summaries}
```

You can manually delete old summaries from `08 Summaries/` — they're regeneratable from the source URLs in their frontmatter. Or archive old daily notes (`02 Daily/<old-year>/`) to a separate location.

### Hermes Agent cron / gateway running unnecessarily

The Hermes Agent itself can run a gateway / cron daemon (`hermes gateway`). We don't use that — the morning workflow is triggered by systemd, not by Hermes's internal cron. If you accidentally enabled it (`hermes gateway install`), check:

```
systemctl --user status hermes-gateway 2>/dev/null
```

If running and you don't want it: `hermes gateway uninstall`.

## When to call this whole thing "broken" and bail

If the morning run produces unusable output 3 days in a row despite iteration, something has shifted upstream (Hermes Agent update, Google MCP API change, model regression). Disable the timer, leave the vault as-is for human use, post in the relevant repo's issues, come back when something has changed.

```
sudo systemctl disable --now hermes-morning.timer hermes-weekly.timer
# Vault is read-only safe; no further automated changes.
```
