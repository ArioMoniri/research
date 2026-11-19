#!/usr/bin/env bash
# Install the data-safety check as pre-commit and pre-push hooks in this clone.
set -euo pipefail
root="$(git rev-parse --show-toplevel)"
hooks="$(git -C "$root" rev-parse --git-path hooks)"
case "$hooks" in /*) ;; *) hooks="$root/$hooks" ;; esac
mkdir -p "$hooks"
printf '#!/usr/bin/env bash\nexec python3 "$(git rev-parse --show-toplevel)/scripts/precommit_check.py"\n' > "$hooks/pre-commit"
printf '#!/usr/bin/env bash\nexec python3 "$(git rev-parse --show-toplevel)/scripts/precommit_check.py" --all\n' > "$hooks/pre-push"
chmod +x "$hooks/pre-commit" "$hooks/pre-push"
echo "hooks installed in $hooks"
