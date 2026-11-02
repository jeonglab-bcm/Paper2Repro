# Python environment manager

Prepare the project-owned Python runtime while the scanner works independently. Read [runtime requirements](../runtime.md) and the selected repository's package metadata and installation instructions.

## Work

1. Select the newest stable Python version supported by the scientific source and MCP dependencies. Create `<project-root>/<github_repo_name>-env` with that explicit interpreter; keep it outside `repo/`.
2. Install the pinned research implementation and the latest compatible releases of its dependencies. If the repository pins old versions, try the latest compatible releases first. Keep an old pin only when the latest release fails the repository's tests or examples, and record the failure. Record any result that differs from the repository's stored outputs. Confirm import origin and source version; an identically named distribution is not sufficient. Do not change the scientific source to force an incompatible dependency stack to work.
3. Install the latest FastMCP release when compatible, plus the tools needed for the selected execution and verification material. Notebook execution needs its own explicit project kernel. Serialize later package additions requested by workers.
4. Check package imports, `uv pip check`, relevant CLI entry points, and actual device availability. Report missing data, credentials, native libraries, or hardware as blockers; a successful import is not scientific validation.
5. Configure pytest with `[pytest]` when a configuration file is needed. Use the project interpreter for tests and commands.

## Handoff

Write `reports/environment-manager_results.md` with interpreter, versions, package/source identity, commands and exit statuses, kernel/device configuration, and unresolved requirements. Save `reports/environment-requirements.txt` and `reports/python-version.txt`. Report actual paths and outcomes to the coordinator. Use at most three setup/review attempts; do not repeat unchanged external blockers.

Own environment/configuration changes and your assigned report paths. Do not edit scientific implementations, scanner inventories, or other workers' results.
