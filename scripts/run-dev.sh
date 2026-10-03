#!/bin/sh
# Run Glue Apps straight from the checkout.
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
python_bin=${PYTHON:-python3}

if ! "$python_bin" -c \
    'import gi; gi.require_version("Gtk", "4.0"); gi.require_version("Adw", "1")' \
    >/dev/null 2>&1; then
    echo "PyGObject with GTK 4 and libadwaita is required." >&2
    exit 1
fi

export GLUE_APPS_DATA="$root/data"
export PYTHONPATH="$root${PYTHONPATH:+:$PYTHONPATH}"
exec "$python_bin" -m glue_apps.app "$@"
