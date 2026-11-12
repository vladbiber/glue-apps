#!/bin/sh
set -eu

action=${1-}
name=${2-}
case "$action" in install|remove) ;; *) echo "Invalid action." >&2; exit 2 ;; esac
case "$name" in
    ''|*[!A-Za-z0-9@._+:-]*) echo "Invalid name." >&2; exit 2 ;;
esac

pm=pacman
if ! command -v pacman >/dev/null && command -v apk >/dev/null; then
    pm=apk
fi

if [ "${GLUE_APPS_DRY_RUN:-0}" = 1 ]; then
    printf '%s %s %s\n' "$pm" "$action" "$name"
    exit 0
fi

if [ "$pm" = apk ]; then
    [ "$action" = install ] && exec apk add "$name"
    exec apk del "$name"
fi

if [ "$action" = install ]; then
    exec pacman -S --needed --noconfirm "$name"
fi
exec pacman -Rns --noconfirm "$name"
