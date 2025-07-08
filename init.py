#!/usr/bin/env python3
import os

if not os.path.exists("flags.key"):
    with open("flags.key", "wb") as f:
        f.write(os.getrandom(32))

if not os.path.exists("app-secret.key"):
    with open("app-secret.key", "wb") as f:
        f.write(os.getrandom(16))

if not os.path.exists("join.key"):
    with open("join.key", "wb") as f:
        f.write(os.getrandom(8))

if not os.path.exists("attendance.key"):
    with open("attendance.key", "wb") as f:
        f.write(os.getrandom(8))