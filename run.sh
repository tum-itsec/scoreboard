#!/bin/sh

gunicorn \
	--worker-class gevent \
	--workers 4 \
	--worker-connections 1000 \
	--bind 0.0.0.0:8000 \
	--no-control-socket \
	app:app \
	"$@"
