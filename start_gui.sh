#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

# Prefer an explicit interpreter, then an activated or project environment.
if [[ -n "${AI_CLOSET_PYTHON:-}" ]]; then
    closet_python="$AI_CLOSET_PYTHON"
elif [[ -n "${VIRTUAL_ENV:-}" && -x "$VIRTUAL_ENV/bin/python" ]]; then
    closet_python="$VIRTUAL_ENV/bin/python"
elif [[ -x .venv/bin/python ]]; then
    closet_python="$PWD/.venv/bin/python"
elif [[ -x "$HOME/venvs/vllm/bin/python" ]]; then
    # Support existing installations that keep their environment outside the repo.
    closet_python="$HOME/venvs/vllm/bin/python"
else
    closet_python="python3"
fi
exec "$closet_python" web/app.py
