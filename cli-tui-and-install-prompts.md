---

## CLI: Interactive TUI + Install-Time Prompts

**Goal:** `rtap` with no arguments launches a polished arrow-key TUI menu (rich/questionary) exposing every capability. Every menu action also has a direct subcommand equivalent for scripting/automation. Installation prompts for LLM provider and container startup.

### 1. Default TUI behavior
- Running `rtap` with zero arguments launches an interactive arrow-key menu (questionary `select`/`checkbox` style), not a help text dump
- Menu top-level options should map 1:1 to the subcommands below (ingest, score, generate campaign plan, manage tenants/engagements, view status, etc. — agent should enumerate actual existing subcommands first, not assume a list)
- Each menu item, once selected, should prompt for any required args (e.g. file path for ingest, org_id/engagement_id) via questionary prompts, not require the user to already know CLI flag syntax
- Use `rich` for all output formatting (tables, progress bars, colored status) consistent with whatever's already in use elsewhere in the CLI

### 2. Direct subcommand parity
- Every TUI menu action must also work as a direct Typer subcommand, e.g.:
  - `rtap ingest bloodhound <file.zip> --org-id <id> --engagement-id <id>`
  - `rtap score attack-paths --org-id <id> --engagement-id <id>`
  - `rtap plan generate --org-id <id> --engagement-id <id>`
- The TUI should call the same underlying functions as the subcommands — not duplicate logic. Verification: trace one menu action through to confirm it calls the identical function the subcommand calls, not a parallel implementation.

### 3. Install-time prompts
On first run / fresh install (detect via absence of a config file, e.g. `~/.config/rtap/config.toml` or repo-local equivalent — agent should check what config mechanism already exists before inventing a new one):
- Prompt: **LLM provider** — "Gemini (via OpenRouter, requires API key)" vs. "Ollama (offline, local)"
  - If Gemini: prompt for and store the OpenRouter API key (never print it back, store securely — check existing patterns for secrets handling, e.g. `.env` vs OS keyring)
  - If Ollama: check if Ollama is installed/reachable locally; if not, print instructions rather than failing silently
- Prompt: **Start containers now?** (yes/no) — if yes, run the equivalent of `./run.sh up` and wait for healthy status before continuing; if no, print the manual command to run later

### Required verification
- Real terminal session showing: fresh-install flow end-to-end (both LLM provider branches), TUI menu rendering and successfully invoking at least one real action (e.g. ingest), and a direct subcommand producing identical output/state to the same action taken via TUI
- Not acceptable: a description of the menu structure without an actual run showing it rendering and working

---
