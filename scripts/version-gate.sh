#!/usr/bin/env bash
# primavera-web 7.1.1: `details.version` in cajeta.json is the single source
# of truth and `Primavera.version()` hands consumers a literal copy of it. The
# library declares no filesystem capability and so cannot read its own
# manifest at run time, so the comparison lives here; the test task runs it.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CAJETA="${CAJETA:-cajeta}"
manifest_version="$( cd "$here" && "$CAJETA" info 2>/dev/null \
    | awk '/^[[:space:]]*version:/{print $2; exit}' )"
source_version="$(sed -n 's/.*version()[^"]*"\([^"]*\)".*/\1/p' \
    "$here/src/main/cajeta/dev/cajeta/primavera/Primavera.cajeta" 2>/dev/null | head -1)"
[[ -n "$manifest_version" && -n "$source_version" ]] \
    || { echo "version-gate: could not read both version strings (manifest '$manifest_version', source '$source_version')" >&2; exit 1; }
[[ "$manifest_version" == "$source_version" ]] \
    || { echo "VERSION DRIFT: cajeta.json says $manifest_version, Primavera.version() says $source_version" >&2; exit 1; }
echo ">> version-gate: $manifest_version matches Primavera.version()"
