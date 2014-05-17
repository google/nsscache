#!/bin/sh

# This script returns one or more authorized keys for use by SSH, by extracting
# them from a local cache file /etc/sshkey.cache.
#
# Ensure this script is mentioned in the sshd_config like so:
#
# AuthorizedKeysCommand /path/to/nsscache/authorized-keys-command.sh

awk -F: -v name="$1" '$0 ~ name {print $2}' /etc/sshkey.cache | \
    tr -d "[']" | \
    sed -e 's/, /\n/g'
