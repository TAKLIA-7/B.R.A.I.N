#!/usr/bin/env python3
"""
scripts/sync_obsidian.py

Exports canonical Knowledge Brain records from PostgreSQL into an Obsidian Markdown vault.
Idempotent: notes are overwritten with normalized Markdown and wiki-links.
"""
import os
import sys
import json
import logging

# Ensure project root is in python path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from core.consolidation.obsidian import ObsidianVaultExporter

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("obsidian_sync")

def main():
    exporter = ObsidianVaultExporter()
    print("==================================================")
    print("      Knowledge Brain -> Obsidian Vault Sync      ")
    print("==================================================")
    print(f"Target Vault Path: {exporter.vault_path or 'DISABLED'}\n")

    if not exporter.vault_path:
        print("[!] Obsidian vault path is not configured (OBSIDIAN_VAULT_PATH is empty).")
        print("    Set OBSIDIAN_VAULT_PATH in .env or environment to enable.")
        sys.exit(0)

    result = exporter.sync_from_postgres()

    if result.get("status") == "success":
        print("[+] Sync completed successfully!")
        print(f"    Vault Directory: {result.get('vault_path')}")
        print(f"    Exported Files:  {result.get('exported_files')}")
        counts = result.get("counts", {})
        print(f"    - Memories:      {counts.get('memories', 0)}")
        print(f"    - Tracked Bugs:  {counts.get('bugs', 0)}")
        print(f"    - Verified Fixes:{counts.get('fixes', 0)}")
        print(f"    - Tasks:         {counts.get('tasks', 0)}")
        print(f"    - Projects:      {counts.get('projects', 0)}")
    elif result.get("status") == "skipped":
        print(f"[~] Sync skipped: {result.get('message')}")
    else:
        print(f"[-] Sync failed: {result.get('error')}")
        sys.exit(1)

if __name__ == "__main__":
    main()
