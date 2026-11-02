#!/usr/bin/env bash
set -euo pipefail

out_dir="${1:-}"

if [[ -z "$out_dir" ]]; then
    echo "Usage: $0 <build-out-directory>" >&2
    exit 2
fi

if [[ ! -d "$out_dir" ]]; then
    echo "AXP output directory not found: $out_dir" >&2
    exit 1
fi

out_dir="$(realpath -- "$out_dir")"

mapfile -d '' axp_files < <(
    find "$out_dir" -type f -name '*.axp' -printf '%T@\t%p\0' | sort -z -nr
)

if (( ${#axp_files[@]} == 0 )); then
    echo "No .axp files found under: $out_dir" >&2
    exit 1
fi

for entry in "${axp_files[@]}"; do
    path="${entry#*$'\t'}"
    stat --printf='%y\t%s bytes\t%n\n' "$path"
done
