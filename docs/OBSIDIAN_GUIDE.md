# Knowledge Brain --- Obsidian Visualization Guide

The Knowledge Brain Obsidian vault is a human-facing, read-only Markdown projection of the canonical knowledge, tasks, decisions, bugs, and fixes stored in PostgreSQL.

PostgreSQL remains the single authoritative source of truth. The Obsidian vault can be deleted and regenerated idempotently at any time.

---

## 1. Opening the Vault in Obsidian

1. Install [Obsidian](https://obsidian.md/) (macOS, Windows, or Linux).
2. Launch Obsidian and select **"Open folder as vault"**.
3. Choose the `obsidian_vault` directory inside your Knowledge Brain repository root:
   ```text
   <path-to-repository>/obsidian_vault
   ```
4. Obsidian will automatically index the vault and display `Home.md` as the dashboard.

---

## 2. Vault Organization

The vault is organized into dedicated folders:

- **`Home.md`**: Master dashboard with live counts of memories, projects, tasks, bugs, and fixes.
- **`Projects/`**: Hub notes for each project linking associated tasks, decisions, and bugs.
- **`Memories/`**: Persistent facts, decisions, and preferences with YAML frontmatter, trust scores, and epistemic states (`asserted | confirmed | disputed`).
- **`Tasks/`**: Agent task definitions with status and project links.
- **`Bugs/`**: Structured defect logs with reproduction symptoms, root cause, and links to verified fixes.
- **`Fixes/`**: Resolution records containing verification test proof outputs and links to resolved bugs.

---

## 3. Interactive Graph View

Obsidian's **Interactive Graph View** visualizes all relationships, cross-links, and entity associations:

1. Press `Ctrl + G` (Windows/Linux) or `Cmd + G` (macOS) to open the Graph View.
2. In the **Filters** menu:
   - Check **Tags** to see hashtags (`#decision`, `#bug/verified`, `#task`, `#bug/open`).
   - Enable **Arrows** to see directionality between bugs, fixes, and memories.
3. In the **Groups** menu, add color coding:
   - `path:Projects` -> Blue
   - `path:Memories` -> Purple
   - `path:Bugs` -> Red
   - `path:Fixes` -> Green
   - `path:Tasks` -> Orange

---

## 4. On-Demand Vault Synchronization

To update or regenerate the vault from PostgreSQL:

```bash
python scripts/sync_obsidian.py
```

### Automation / Scheduled Export
The sync script is completely idempotent and safe to run on a recurring cron job or post-task hook. If PostgreSQL is updated, re-running the script immediately updates the vault without duplicating files or breaking existing note links.

If Obsidian is not running or the vault path is disabled (`OBSIDIAN_VAULT_PATH=""`), the backend continues to operate with zero degradation.
