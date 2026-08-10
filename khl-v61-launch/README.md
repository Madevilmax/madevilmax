# KHL Predictive Index v6.1 server launch

This directory is intentionally isolated from the existing repository application.

## One-command transfer into the real maxkhl directory

On the server, after fetching this branch:

```bash
bash khl-v61-launch/install.sh /opt/maxkhl
```

If maxkhl lives elsewhere, replace `/opt/maxkhl` with its actual repository root.

The installer reconstructs and validates the launch-pack archive and extracts it into the target repository.

Then run Codex from the target repository:

```bash
cd /opt/maxkhl
codex "Read CODEX_SERVER_IMPLEMENTATION.md. Audit the current maxkhl repository first, implement safely, do not break production, and keep LIVE_MODEL_V61=false."
```

Do not enable `LIVE_MODEL_V61` until migrations, replay/backtest, build/tests and Publication Guard pass.
