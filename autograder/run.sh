#!/bin/bash

if [[ "$1" == *.zip ]]; then
	unzip "$1"
	exec /usr/bin/python3 ./pwn.py
else
	exec /usr/bin/python3 "$1"
fi
