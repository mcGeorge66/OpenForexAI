[Back to Config](ui.config.en.md)

# Snapshot Config

Use `Snapshot Config` to define what data is collected, interpreted, and
forwarded into a snapshot-driven agent run.

Current major capabilities:

- select a snapshot profile
- select the execute context agent
- create a new empty profile
- update the current profile
- save a modified copy as a new profile
- delete a profile
- configure tool-backed snapshot blocks
- configure decision payload behavior
- configure decision semantics
- run an execute preview

This page is not only a schema editor. It is also a practical design surface
for the exact runtime snapshot consumed by an agent cycle.

Suggested screenshots:
- [Snapshot Config editor](image/ui-15-snapshot-config-editor.png)
- [Snapshot execute preview dialog](image/ui-16-snapshot-execute-preview.png)

## Reference Documents

For the full configuration reference, transformer scripts, and helper
functions, see:

- [Snapshot Config Guide](snapshot-config-guide.en.md)
- [Snapshot Transformers](snapshot-transformers.en.md)
- [Snapshot Helper Functions](snapshot-helper-functions.en.md)

## Helper Config

The `Helper Config` page lets you edit `config/snapshot_helpers.py` — the
optional Python helper functions available inside snapshot transform scripts.

The editor performs a backend Python syntax check before saving.
