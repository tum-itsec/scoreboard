#!/bin/bash

# Podman's logs API apparently only captures stdout, not stderr.
# Since we merge stdout and stderr anyway, might as well merge it here already
# and not fuss with the Podman API any further.
{
	if [[ "$1" == *.zip ]]; then
		unzip "$1"
		exec /usr/bin/python3 -u ./pwn.py
	else
		exec /usr/bin/python3 -u "$1"
	fi
} 2>&1
