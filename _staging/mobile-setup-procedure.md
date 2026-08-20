# Mobile setup — Android + iPad

Held until Phase 10 push lands (mobile clients clone from GitHub; nothing to
clone until the first push).

## Step 0 — GitHub fine-grained PAT (one PAT, used on both devices)

Once on the desktop:

1. Browse to: github.com → Settings (top-right avatar) → **Developer settings**
   → **Personal access tokens** → **Fine-grained tokens** → **Generate new token**
2. Fill in:
   - **Token name**: `vault-ai mobile sync`
   - **Expiration**: 1 year (or whatever cadence suits)
   - **Resource owner**: YOUR_GH_USER
   - **Repository access**: select **Only select repositories** → pick `vault-ai`
   - **Permissions** (under "Repository permissions"):
     - **Contents**: Read and write
     - **Metadata**: Read-only (this auto-selects when you pick Contents)
     - Leave every other permission at "No access"
3. **Generate token** → copy the token immediately (starts with `github_pat_…`).
   You will NOT see it again. Paste it somewhere temporary (or just into your
   Android/iPad clipboard if you can airdrop/keep it visible).

## Step 1 — Android

1. Install **Obsidian** from Google Play Store.
2. Open Obsidian → **Create new vault** → name it `vault-ai`, location: anywhere
   on device storage (default is fine).
3. Inside the new (empty) vault: **Settings → Community plugins**.
   - First time: tap **Turn on community plugins**.
   - Tap **Browse** → search **Obsidian Git** → Install → Enable.
4. Open **Obsidian Git settings**:
   - **Authentication / Git Username**: `YOUR_GH_USER`
   - **Authentication / Personal access token**: paste the PAT from Step 0
   - **Remote URL**: `https://github.com/YOUR_GH_USER/vault-ai.git`
   - **Branch**: `main`
   - **Pull on startup**: **enabled**
   - **Vault backup interval (minutes)**: `10`
   - **Auto pull interval (minutes)**: `10`
   - **Auto push after commit**: **enabled**
   - **Sync method**: `rebase`
5. Run the command: **Obsidian Git: Clone an existing remote repo** (palette
   command — three-dot menu or command-search). Confirm — it overwrites the
   empty vault with the GitHub contents.
6. Pull should complete in seconds. You'll see the seven `01 Updates/` stream
   notes appear.
7. Enable the same plugins as desktop (`flashcards-obsidian`, `unread-dot`,
   `obsidian-git`, `heatmap-calendar`, `templater-obsidian`) — they're already
   present in `.obsidian/plugins/`, just need to be enabled in Settings →
   Community plugins → Installed.

## Step 2 — iPad

Two paths. Path A is the same as Android. Path B (Working Copy) some people
find more reliable on iPadOS.

### Path A — Obsidian Git on iPad

Identical to Android Steps 1–7. Obsidian Git's iPadOS build works the same
way.

### Path B — Working Copy + Obsidian (alternative if Path A fails)

1. Install **Working Copy** from the App Store (free tier supports cloning).
2. In Working Copy: **+ → Clone repository**
   - URL: `https://github.com/YOUR_GH_USER/vault-ai.git`
   - Tap "Authenticate" → choose **HTTPS** → username `YOUR_GH_USER`, password
     = the PAT
   - Clone
3. In Working Copy: long-press the cloned `vault-ai` → **Setup Folder for
   External Access** → **Files**
4. Install **Obsidian** from App Store.
5. Obsidian → **Open folder as vault** → Files → On My iPad → Working Copy
   → vault-ai → Open
6. Vault opens. For sync: pull/commit/push manually via Working Copy when you
   want. (Less automatic than Path A, but more robust on iPadOS.)

## Step 3 — verify both devices

After both mobiles have cloned successfully:

- Edit a test note on the phone (e.g. add a line to `📋 Tasks.md`).
- Wait ≤10 min (or trigger sync manually).
- On the desktop, in `~/vault-ai`: `git fetch && git log --oneline origin/main -3`
  should show the mobile commit.
- Pull on desktop: `git pull --rebase`. The edit should appear.
- Likewise edit on desktop, push, wait, edit-and-pull on phone.

If sync works both directions: mobile setup is done. From here on, the morning
run's daily output appears on your phone by the time you wake up (provided
the morning timer is enabled, which is the Phase 10 gate).

## Troubleshooting

- **Obsidian Git on Android fails to clone**: most common cause is the PAT
  being incomplete or expired. Regenerate the PAT (Step 0) and re-paste.
- **iPad Obsidian Git is "stuck" pulling**: kill the app, re-open. Or switch
  to Path B (Working Copy).
- **Conflicts**: extremely rare given the time-of-day separation (phone edits
  in the evening, desktop morning-run at 05:55, mostly non-overlapping files).
  If they happen: `git pull --rebase` on desktop, resolve, push.
