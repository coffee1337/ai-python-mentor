#!/usr/bin/env bash
set -euo pipefail
export BACKUP_MODE=restore
exec bash "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/backup.sh" "$@"
