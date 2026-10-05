#!/bin/sh
# Full system upgrade, run through pkexec by Glue Apps.
set -eu

# DKMS drivers (NVIDIA and others) rebuild against the headers of every
# installed kernel; upgrading without them leaves the next boot without a driver.
if pacman -Qq 2>/dev/null | grep -q -- '-dkms$'; then
    for kernel in $(pacman -Qqo /usr/lib/modules/*/vmlinuz 2>/dev/null | sort -u); do
        if ! pacman -Q "$kernel-headers" >/dev/null 2>&1; then
            echo "Update stopped: $kernel-headers is not installed and the DKMS drivers need it." >&2
            echo "Install it first: pacman -S $kernel-headers" >&2
            exit 3
        fi
    done
fi

# --ask inverts the default answer of two questions --noconfirm says no to,
# which aborted the whole update: 4 = remove a package that conflicts (a
# split or merge upstream, the answer is always yes) and 16 = skip the
# packages that cannot be upgraded this time. pacman still stops if a
# removal would break a dependency.
if [ "${GLUE_APPS_DRY_RUN:-0}" = 1 ]; then
    echo 'pacman -Syu --noconfirm --ask=20'
    exit 0
fi

exec pacman -Syu --noconfirm --ask=20
