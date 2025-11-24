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
import docker
import re
import zipfile

docker_client = docker.from_env()

HOST = os.environ.get("SCOREBOARD_URL", "https://scoreboard.sec.in.tum.de")
APIKEY = os.environ.get("SCOREBOARD_APIKEY")
IMAGE_NAME = os.environ.get("AUTOGRADER_IMAGE", "grader")
INTERVAL = 30
TIMEOUT = 150

logging.getLogger().setLevel(logging.INFO)
logging.getLogger().addHandler(logging.StreamHandler())

print(f"Using {HOST} as Scoreboard API")
print(f"Using {IMAGE_NAME} as Docker image")

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
        if r.status_code != 200:
            logging.error(f"Scoreboard answered with invalid statuscode to download request: {r.status_code} Server broken?")
            break

        filename = os.path.basename(s['filename'])
        if not filename.endswith(".py") and not filename.endswith(".zip"):
            logging.info(f"Skipping submission {s['id']}: {filename}")
            continue

        sandbox_dir = tempfile.mkdtemp(prefix="sandbox_")
        try:
            filename = filename.replace("\x00", "")
            filename = filename.replace("/", "").replace("\\", "") # Should not be necessary, but better safe than sorry

            with open(sandbox_dir + "/" + filename, "wb") as f:
               f.write(r.content)

            mnts = []
            mnts.append(docker.types.Mount("/mnt", sandbox_dir, type="bind"))
            c = docker_client.containers.run(IMAGE_NAME, ['/run.sh', filename],
                user=f"{os.getuid()}:{os.getgid()}",
                working_dir="/mnt",
                mounts=mnts,
                network_mode="host",
                detach=True,
                init=True)
            try:
                state = c.wait(timeout=TIMEOUT)
                buf = b""
                SIZE_LIMIT = 8 * 1024
                for chunk in c.logs(stream=True):
                    buf += chunk
                    if len(buf) > SIZE_LIMIT:
                        buf = buf[:SIZE_LIMIT]
                        buf += b"\n\n[Log truncated]"
                        break
                output = buf.decode(errors="replace")
            except requests.exceptions.ConnectionError:
                logging.info(f"Terminated testing of submission {s['id']}")
                output = f"Execution took more than {TIMEOUT} secondes, aborting..."
                c.kill()
            c.remove()

            # flag = flag_regex.search(output)
            answer = {
                    "output": "\n".join(output.splitlines()[-100:]),
            }
            # print(output)
            r = requests.post(f"{HOST}/autograde/{s['id']}?APIKEY={APIKEY}", data=answer)
            print(r.text)
            if r.status_code != 200:
                logging.error(f"Scoreboard answered with invalid statuscode to download request: {r.status_code} Server broken?")
        finally:
            shutil.rmtree(sandbox_dir)
    time.sleep(INTERVAL)
