# Agent Notes

## Repo Layout

- `setup/` — one-time repo bootstrap (not a skill): `guide.md` (agentic-install
  guide), `install.sh` (deterministic clean-adds installer), and `templates/`.
  When editing the bootstrap, keep `install.sh` clean-adds-only (never edit,
  merge, or overwrite existing target files) and keep the raw URLs in `guide.md`
  and `install.sh` pointing at `jedzill4/repo-setup` on `main`.
- `skills/` — actual installed skills (`journalist`, `handoff`).

## Skill Development

After creating or editing any skill under `skills/`, validate its `SKILL.md`
before committing:

```bash
tessl skill review <SKILL.md>
```

Run it against each changed skill (e.g. `tessl skill review skills/productivity/journalist/SKILL.md`)
and resolve the reported issues before publishing.
