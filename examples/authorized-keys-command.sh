#!/bin/sh

# This script returns one or more authorized keys for use by SSH, by extracting
# them from a local cache file /etc/sshkey.cache.
#
# Ensure this script is mentioned in the sshd_config like so:
#
# AuthorizedKeysCommand /path/to/nsscache/authorized-keys-command.sh
# AuthorizedKeysCommandUser nobody

[ -n "$1" ] || exit 0
cache_file="${2:-${NSSCACHE_SSHKEY_CACHE:-/etc/sshkey.cache}}"

exec /usr/bin/python3 -c '
import ast
import os
import sys

target_bytes = os.fsencode(sys.argv[1])
cache_path = os.fsencode(sys.argv[2])
if (
    not target_bytes
    or b":" in target_bytes
    or b"\n" in target_bytes
    or b"\r" in target_bytes
    or b"\x00" in target_bytes
):
    sys.exit(0)
try:
    target_bytes.decode("utf-8")
except UnicodeDecodeError:
    sys.exit(0)

try:
    f = open(cache_path, "rb")
except OSError:
    sys.exit(0)

try:
    with f:
        for raw_line in f:
            raw_line = raw_line.rstrip(b"\r\n")
            if not raw_line or raw_line.startswith(b"#") or b":" not in raw_line:
                continue
            raw_user, raw_val = raw_line.split(b":", 1)
            if raw_user != target_bytes:
                continue
            try:
                val = raw_val.decode("utf-8").strip()
            except UnicodeDecodeError:
                continue
            if not val:
                continue
            if val.startswith("["):
                if not val.endswith("]"):
                    continue
                try:
                    parsed = ast.literal_eval(val)
                except (ValueError, SyntaxError, TypeError, MemoryError, RecursionError):
                    continue
                if not isinstance(parsed, list):
                    continue
                keys = [item for item in parsed if isinstance(item, str)]
            else:
                keys = [val]
            for key in keys:
                key = key.strip()
                if not key or "\n" in key or "\r" in key or "\x00" in key:
                    continue
                sys.stdout.buffer.write(key.encode("utf-8") + b"\n")
    sys.stdout.buffer.flush()
except OSError:
    os._exit(0)
' "$1" "$cache_file"
