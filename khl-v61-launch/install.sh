#!/usr/bin/env bash
set -euo pipefail

LAUNCH_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$LAUNCH_DIR/.." && pwd)"
TARGET_DIR="${1:-/opt/maxkhl}"
TMP_B64="/tmp/KHL_NoAPI_Server_Launch_Pack_v2.b64"
TMP_ZIP="/tmp/KHL_NoAPI_Server_Launch_Pack_v2.zip"

for part in "$LAUNCH_DIR"/pack.part{01..04}.b64; do
  [[ -f "$part" ]] || { echo "Missing $part" >&2; exit 1; }
done

cat "$LAUNCH_DIR"/pack.part{01..04}.b64 > "$TMP_B64"
base64 -d "$TMP_B64" > "$TMP_ZIP"
unzip -t "$TMP_ZIP" >/dev/null

mkdir -p "$TARGET_DIR"
unzip -o "$TMP_ZIP" -d "$TARGET_DIR"

printf '\nKHL v6.1 launch pack installed into: %s\n' "$TARGET_DIR"
echo 'LIVE_MODEL_V61 remains false in the supplied env template.'
echo
cat <<EOF
Next:
  cd "$TARGET_DIR"
  codex "Read CODEX_SERVER_IMPLEMENTATION.md. Audit the current maxkhl repository first, implement safely, do not break production, and keep LIVE_MODEL_V61=false."

After implementation and validation only:
  sudo bash scripts/install-systemd.sh
EOF
