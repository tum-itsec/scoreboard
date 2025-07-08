#!/usr/bin/env python3
import requests
import json
import os
import re
import subprocess
import time
import logging
import tempfile
import sys
import shutil
from landlock import Ruleset, FSAccess

HOST = os.environ.get("SCOREBOARD_URL", "http://scoreboard.sec.in.tum.de")
APIKEY = os.environ.get("SCOREBOARD_APIKEY")
INTERVAL = 30

logging.getLogger().setLevel(logging.INFO)
logging.getLogger().addHandler(logging.StreamHandler())

print(f"Using {HOST} as Scoreboard API")

while True:
    logging.info("Asking the scoreboard for more submissions to check")
    r = requests.get(f"{HOST}/autograde?APIKEY={APIKEY}")
    if r.status_code != 200:
        logging.error(f"Scoreboard answered with invalid statuscode: {r.status_code} Server broken?")
        time.sleep(INTERVAL)
        continue

    submissions = r.json()

    # server_data = {"flag_regex": "flag{[^}]*}", "submissions": [{"id": 1}]}
    logging.info(f"Got {len(submissions)} new submissions from scoreboard")

    # flag_regex = re.compile(server_data["flag_regex"].encode()) # We need a bytes regex

    for s in submissions:
        logging.info(f"Testing submission ID {s['id']} filename {s['filename']}")
        r = requests.get(f"{HOST}/autograde/{s['id']}?APIKEY={APIKEY}")
        print("Forking...")
        # We cannot use tempfile.TemporaryDirectory here as we fork and sandbox ourselves afterwards.
        # Both parent and child will try to clean up the tempdir when TemporaryDirectory goes out of context.
        sandbox_dir = tempfile.mkdtemp(prefix="sandbox_")
        child_pid = os.fork()
        if child_pid == 0:

            # Set current dir to sandbox dir
            os.chdir(sandbox_dir)

            # Use Landlock to sandbox ourselves
            rs = Ruleset()
            rs.allow(".")
            rs.allow("/bin", rules=FSAccess.READ_DIR | FSAccess.READ_FILE | FSAccess.EXECUTE)
            rs.allow("/usr", rules=FSAccess.READ_DIR | FSAccess.READ_FILE | FSAccess.EXECUTE)
            rs.allow("/dev", rules=FSAccess.READ_DIR | FSAccess.READ_FILE | FSAccess.WRITE_FILE)
            rs.apply()

            # Write the file contents here... We are already sandboxed, so nothing evil should happen (fingers crossed)
            with open(sandbox_dir + "/" + os.path.basename(s["filename"]), "wb") as f:
                print(r.content)
                f.write(r.content)

            # Execute python script WITH resetting env -> we might leak API keys to subprocess otherwise
            output = subprocess.run(["/usr/bin/python3", s['filename']], stderr=subprocess.STDOUT, stdout=subprocess.PIPE, env={})
            print(f"Got output: {output}")
            # flag = flag_regex.search(output)
            answer = {
                "output": output.stdout,
            }
            print("Answer:", answer)
            r = requests.post(f"{HOST}/autograde/{s['id']}?APIKEY={APIKEY}", data=answer)
            print(r.json())
            sys.exit(0)
        else:
            print(f"Waiting for child {child_pid}")
            os.waitpid(child_pid, 0)
            shutil.rmtree(sandbox_dir)
            print("Done waiting for child")
    time.sleep(INTERVAL)
