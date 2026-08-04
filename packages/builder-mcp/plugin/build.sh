#!/usr/bin/env bash
# Build the Claude Cowork upload bundle: dist/cornell-builder.plugin
#
# A .plugin is a zip of the plugin directory's *contents* -- .claude-plugin/ and
# .mcp.json must sit at the archive root, not under a wrapper folder.
#
# Unlike the Node connectors in the systemsbot suite there are no node_modules to
# vendor: this plugin's MCP server is fetched at launch by uvx from the public repo
# (SPEC-PLUGIN.md P2), so the bundle is just manifests, the skill, and docs.
#
# Works in Git Bash on Windows and in Linux CI. Requires: zip.
set -euo pipefail

cd "$(dirname "$0")"
NAME="cornell-builder"
DIST="dist"

command -v zip >/dev/null 2>&1 || {
  echo "error: 'zip' not found. On Windows use Git Bash; in CI apt-get install zip." >&2
  exit 1
}

# Fail before packaging rather than shipping a bundle that cannot load.
for required in .claude-plugin/plugin.json .claude-plugin/marketplace.json .mcp.json skills/builder-mcp/SKILL.md; do
  [ -f "$required" ] || { echo "error: missing required file: $required" >&2; exit 1; }
done

if command -v claude >/dev/null 2>&1; then
  echo "==> validating manifests"
  claude plugin validate . --strict
else
  echo "warning: 'claude' not on PATH; skipping manifest validation" >&2
fi

# Keep plugin.json and the marketplace entry on the same version.
VERSION=$(python -c "import json;print(json.load(open('.claude-plugin/plugin.json'))['version'])")
echo "==> packaging ${NAME} v${VERSION}"

rm -rf "$DIST"
mkdir -p "$DIST"

zip -rq "$DIST/${NAME}.plugin" \
  .claude-plugin .mcp.json skills README.md SPEC-PLUGIN.md \
  -x '*.DS_Store' '*.git*' '*/__pycache__/*'

# A bundle whose manifests are not at the archive root silently fails to load,
# so prove their placement rather than assuming it.
echo "==> verifying archive layout"
unzip -l "$DIST/${NAME}.plugin" | sed -n '1,40p'
unzip -l "$DIST/${NAME}.plugin" | grep -q ' \.claude-plugin/plugin.json$' \
  || { echo "error: plugin.json is not at the archive root" >&2; exit 1; }

if command -v sha256sum >/dev/null 2>&1; then
  ( cd "$DIST" && sha256sum "${NAME}.plugin" > "${NAME}.plugin.sha256" )
  echo "==> checksum: $(cat "$DIST/${NAME}.plugin.sha256")"
fi

echo "==> done: $DIST/${NAME}.plugin"
echo "    Upload via customize menu -> + next to Personal plugins -> Add -> Upload plugin,"
echo "    then fully quit and reopen Claude."
