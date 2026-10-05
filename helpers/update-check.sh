#!/bin/sh
# Before a system upgrade (no root needed): DKMS drivers (NVIDIA and others)
# rebuild against the headers of every installed kernel; upgrading without
# them leaves the next boot without a driver.
if pacman -Qq 2>/dev/null | grep -q -- '-dkms$'; then
    for kernel in $(pacman -Qqo /usr/lib/modules/*/vmlinuz 2>/dev/null | sort -u); do
        if ! pacman -Q "$kernel-headers" >/dev/null 2>&1; then
            echo "Update stopped: $kernel-headers is not installed and the DKMS drivers need it." >&2
            echo "Install it first: pacman -S $kernel-headers" >&2
            exit 3
        fi
    done
fi
exit 0
