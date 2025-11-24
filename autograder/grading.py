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
INTERVAL = int(os.environ.get("AUTOGRADER_INTERVAL", 30))
TIMEOUT = int(os.environ.get("AUTOGRADER_TIMEOUT", 150))
MAX_LINES = 100
SIZE_LIMIT_REPLY = 8 * 1024
SIZE_LIMIT_TOTAL = 100 * 1024 * 1024
# Max chunks returned by Docker's logs() before giving up.
# Prevents (malicious or accidental) DoS by printing too many log messages.
# Each chunk seems to be exactly 1 line for the most part.
MAX_CHUNKS = 100000

logging.getLogger().setLevel(logging.INFO)
logging.getLogger().addHandler(logging.StreamHandler())

print(f"Using {HOST} as Scoreboard API")
print(f"Using {IMAGE_NAME} as Docker image")

# Cleanup in case previous runs got stuck / crashed
for c in docker_client.containers.list(all=True, filters={"label": f"autograding-{IMAGE_NAME}-autokill"}):
    print(f"Cleaning up stale container {c.id} / {c.name} from previous run")
    c.remove(force=True)

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
                name=f"autograding-{IMAGE_NAME}-{s['id']}-{os.getrandom(16).hex()}",
                labels={f"autograding-{IMAGE_NAME}-autokill": "1"},
                user=f"{os.getuid()}:{os.getgid()}",
                working_dir="/mnt",
                mounts=mnts,
                network_mode="host",
                detach=True,
                init=True)
            try:
                try:
                    state = c.wait(timeout=TIMEOUT)
                    killed_by_timeout = False
                except requests.exceptions.ConnectionError:
                    killed_by_timeout = True
                    logging.info(f"Terminated testing of submission {s['id']}")
                    try:
                        c.kill()
                    except docker.errors.APIError:
                        # happens if container dies between wait and kill (that does happen in practice!)
                        # We can just ignore it because of the c.remove() in the finally later.
                        # However, still remember to actually kill the container so that logs() later on doesn't block indefinitely.
                        print("race!")
                        c.kill()

                # read logs
                print("Reading logs...")
                total_len = 0
                total_chunks = 0
                buf = b""
                for chunk in c.logs(stream=True):
                    total_chunks += 1
                    total_len += len(chunk)
                    if total_chunks > MAX_CHUNKS or total_len > SIZE_LIMIT_TOTAL:
                        buf += b"\n\n[Output way too long! Giving up trying to seek to the end; arbitrary middle part of output will be shown.]"
                        print(f"Giving up reading logs; too long: total_len {total_len}, total_chunks {total_chunks}")
                        break
                    buf += chunk
                    # avoid storing / concatenating log content beyond what we'll ever need
                    if len(buf) > SIZE_LIMIT_REPLY:
                        buf = buf[-SIZE_LIMIT_REPLY:]

                # truncate log
                print("Truncating logs and assembling final output...")
                if len(buf) > SIZE_LIMIT_REPLY:
                    buf = buf[-SIZE_LIMIT_REPLY:]
                buf = b"".join(buf.splitlines(keepends=True)[-MAX_LINES:])

                # assemble final output string
                output = buf.decode(errors="replace")
                # this handles both MAX_LINES as well as SIZE_LIMIT_REPLY
                if len(buf) != total_len:
                    output = "[Log truncated]\n\n[...]" + output
                if killed_by_timeout:
                    output = f"[Execution took more than {TIMEOUT} seconds, aborting - flags will not count]\n\n" + output
            finally:
                print("Removing container...")
                # force=True should not be necessary, but better safe than sorry
                c.remove(force=True)

            print("Sending response...")
            # flag = flag_regex.search(output)
            answer = {
                    "output": output,
                    "force_fail": killed_by_timeout
            }
            # print(output)
            r = requests.post(f"{HOST}/autograde/{s['id']}?APIKEY={APIKEY}", data=answer)
            if r.status_code != 200:
                logging.error(f"Scoreboard answered with invalid statuscode to download request: {r.status_code} Server broken?")
            print(f"Response: {r.text}")
        finally:
            print("Cleaning up tmpdir...")
            shutil.rmtree(sandbox_dir)
        print(f"done with submission {s['id']}!")
    time.sleep(INTERVAL)
