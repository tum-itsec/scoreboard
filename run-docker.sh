#!/bin/bash

set -e
set -o pipefail

. /venv/bin/activate

if ! [ -e /app/config.py ]
then
	if ! [ -e /data/config.py ]
	then
		echo "You need to place a config.py in /data or /app" >&2
		exit 1
	fi
	ln -s /data/config.py /app/config.py || { echo "Couldn't link config.py from /data; bind-mount /app/config.py yourself" >&2; exit 1; }
fi

( cd /data && python3 /app/app.py upgrade-db; )

exec /run.sh --chdir /data "$@"
