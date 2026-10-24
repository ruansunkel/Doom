#!/usr/bin/env bash
# Native development checks; no game prefix is changed.
set -euo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$project_root"
if [[ "$(uname -s)" != Darwin ]]; then
  echo 'Run the development checks on the macOS host.' >&2
  exit 2
fi
# shellcheck source=independent/scripts/host-env.sh
source "$project_root/independent/scripts/host-env.sh"
if [[ ! -x .venv/bin/ruff ]] || ! .venv/bin/python -c 'import sys; assert sys.platform == "darwin"' 2>/dev/null; then
  echo 'First run: python3 independent/scripts/setup-host-dev.py' >&2
  exit 1
fi
command -v shellcheck >/dev/null || { echo 'ShellCheck is missing; rerun setup-host-dev.py.' >&2; exit 1; }

shell_files=()
while IFS= read -r path; do shell_files+=("$path"); done < <(
  .venv/bin/python - <<'PY'
from pathlib import Path
for path in sorted(Path('independent/scripts').glob('*.sh')):
    print(path)
PY
)
for path in "${shell_files[@]}"; do bash -n "$path"; done
shellcheck --external-sources "${shell_files[@]}"
.venv/bin/ruff check .
.venv/bin/python - <<'PY'
import ast
from pathlib import Path
for directory in ('independent/scripts', 'independent/tests'):
    for path in Path(directory).rglob('*.py'):
        ast.parse(path.read_text(), filename=str(path))
print("Python syntax checks passed.")
PY
.venv/bin/python -m pytest -q independent/tests
printf 'Host development checks passed.\n'
