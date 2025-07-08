#!/usr/bin/env python3
import requests
import time
import subprocess
import os
import glob
import json

HOST = "http://scoreboard.sec.in.tum.de"
APIKEY = os.environ.get("SCOREBOARD_APIKEY")

# disk quota limits - if you change these, make sure to edit existing users as well
QUOTA_SOFT_LIMIT = "700M" # you can be over this limit for 14 days (change with setquota -t), and must go below that limit to reset the timer
QUOTA_HARD_LIMIT = "768M" # you cannot be over this limit ever

print("started...")

while True:
    print("round...")
    r = requests.get(f"{HOST}/sshkeys/getkeys?APIKEY={APIKEY}")
    print(r.text)
    try:
        server_data = r.json()
    except json.JSONDecodeError:
        print("invalid json...")
    else:
        system_users = [l.split(b":")[0] for l in subprocess.check_output("getent passwd", shell=True).split(b"\n")]
        for user, keys in server_data.items():
            if user.encode() not in system_users:
                print(f"{user} is missing on the system")
                subprocess.check_call(["/usr/sbin/useradd", "-s", "/bin/bash", "-K", "UMASK=077", "-m", user])
                subprocess.check_call(["/usr/sbin/setquota", "-u", user, QUOTA_SOFT_LIMIT, QUOTA_HARD_LIMIT, "0", "0", "/"])

            with open(f"/etc/ssh/auth-keys/{user}", "w") as f:
                for key in keys:
                    f.write(key + "\n")

        # Delete old keys
        for f in glob.glob("/etc/ssh/auth-keys/*"):
            if os.path.basename(f) not in server_data.keys():
                print(f"Removed user key {f}")
                os.remove(f)

    time.sleep(60)
