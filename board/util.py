import hashlib
from functools import wraps
import sqlite3
import os
import time
import re
from flask import session, g, redirect, flash, current_app, request
import binascii
import struct
import enum
from Crypto.Cipher import AES

FLAG_BODY_REGEX = r"\{([0-9a-fA-F]{36})\}"

def pw_hash(pw, salt):
    return hashlib.pbkdf2_hmac(hash_name="sha512", password=pw, salt=salt, iterations=10000)[:32]

ADMIN_ROLES = [1]
TUTOR_ROLES = [1,2]

def is_admin():
    if session.get("user-role") in ADMIN_ROLES:
        return True
    else:
        return False

def is_tutor():
    if session.get("user-role") in TUTOR_ROLES:
        return True
    else:
        return False

class BenchmarkingWrapper:
    def __init__(self, obj, config, id_prefix="", time_add=None):
        self.obj = obj
        if len(config) == 3:
            self.wrap_funcs, self.wrap_objs, self.ignored = config
        else:
            # use length-2 config to not warn about unknown attrs and instead just silently hand them out without changes
            self.wrap_funcs, self.wrap_objs = config
            self.ignored = None
        # urandom instead of simple global counter because gunicorn parallelizes the entire app,
        # so a simple counter wouldn't be unique, and even hash values possibly would be deterministic
        self.id = id_prefix + os.urandom(4).hex()
        self.time = 0
        self.time_add = time_add or (lambda t: None)

    def __getattr__(self, attrname):
        attr = getattr(self.obj, attrname)

        subconfig = self.wrap_objs.get(attrname)

        def t(a):
            self.time += a
            self.time_add(a)

        if attrname in self.wrap_funcs:
            def bla(*args, **kwargs):
                result = self.bm(attr, *args, **kwargs)
                if subconfig:
                    return BenchmarkingWrapper(result, subconfig, self.id + "_", t)
                return result
            return bla

        if subconfig:
            return BenchmarkingWrapper(attr, subconfig, self.id + "_", t)

        if self.ignored is not None and attrname not in self.ignored:
            print(f"BM WARNING: Unknown attr {attrname}; handing out original. Source: {self.id}")

        return attr

    def bm(self, func, *args, **kwargs):
        start = time.monotonic()
        result = func(*args, **kwargs)
        end = time.monotonic()
        t = end - start
        self.time += t
        self.time_add(t)
        print(f"BM {self.id} {func.__name__:8}: {t:f}, total {self.time:f}{f': {args}' if args else ''}")
        return result

    # these two for some reason aren't caught by __getattr__
    def __iter__(self): return self.__getattr__("__iter__")()
    def __next__(self): return self.__getattr__("__next__")()

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = sqlite3.connect(current_app.config["DATABASE"], isolation_level=None)
        db.row_factory = sqlite3.Row
        if current_app.config.get("BENCHMARK_DB"):
            import time
            bm_conf_cursor = (["execute", "fetchall", "fetchone", "__iter__"], {"__iter__": (["__next__"], {}, []), "execute": ([], {}, [])}, [])
            bm_conf_db = (["execute", "cursor", "close"], {"cursor": bm_conf_cursor, "execute": bm_conf_cursor}, [])
            db = BenchmarkingWrapper(db, bm_conf_db)
        g._database = db
    return db

def get_team_from_db():
    cur = get_db().cursor()
    cur.execute("SELECT * FROM team_members tm LEFT JOIN teams t ON t.team_id = tm.team_id WHERE member_id = ? and t.deleted is null", (session["user-id"],))
    res = cur.fetchone()
    if res:
        return res["team_id"]
    else:
        return None

def get_team_members(team_id):
    cur = get_db().cursor()
    cur.execute("SELECT member_id FROM team_members WHERE team_id = ?", (team_id,))
    for row in cur:
        yield row["member_id"]

def get_user_name(user_id):
    cur = get_db().cursor()
    cur.execute("SELECT u.vorname || ' ' || u.nachname as name FROM users u WHERE u.id = ?", (user_id,))
    res = cur.fetchone()
    if res:
        return res["name"]
    else:
        return None

def generate_teamname(name, team_id):
    return name if name else f"Team {team_id}"

def set_teamidoffset(app):
    if firstTeamnum := app.config.get("START_TEAMNUMBER", 0):
        with app.app_context():
            if (firstTeamnum > 1):
                teamname = "TeamForNumOffset"
                cur = get_db().cursor()

                # Check if a team like this already exists
                cur.execute("SELECT teamname FROM teams where team_id = ?", [firstTeamnum - 1])
                res = cur.fetchone()
                if not res:
                    cur.execute("INSERT INTO teams (team_id, created, deleted, teamname) VALUES (?, ?, ?, ?)", [firstTeamnum - 1, int(time.time()), int(time.time()), teamname])
                    cur.execute("DELETE FROM teams WHERE team_id = ?", [firstTeamnum - 1])
                elif res["teamname"] != teamname:
                    print(f"Teamname offset can not be accouted for as a team with the ID {firstTeamnum - 1} already exists.")
                

def create_team(team_members):
    cur = get_db().cursor()
    # Check if any of them is already in a team
    for i in team_members:
        cur.execute("SELECT COUNT(*) FROM team_members tm LEFT JOIN teams t ON t.team_id = tm.team_id WHERE tm.member_id = ? and t.deleted is null", (i,))
        if cur.fetchone()[0] > 0:
            flash("Eines der neuen Teammitglieder ist bereits in einem anderen Team :(")
            return False

    cur.execute("INSERT INTO teams (created, deleted) VALUES (?,NULL)", (int(time.time()),))
    new_team_id = cur.lastrowid
    for i in team_members:
        cur.execute("INSERT INTO team_members (team_id, member_id) VALUES (?,?)", (new_team_id, i))
    return True

def redirect_to_post_login_url():
    if "post-login-return-url" in session:
        url = session["post-login-return-url"]
        del session["post-login-return-url"]
        return redirect(url)
    else:
        return redirect("/scoreboard")

def login_required(f):
    @wraps(f)
    def login_required_wrapper(*args, **kws):
        if "user-id" not in session:
            session["post-login-return-url"] = request.path
            return redirect("/")
        else:
            return f(*args,**kws)
    return login_required_wrapper

def admin_required(f):
    @wraps(f)
    def admin_required_wrapper(*args, **kws):
        if "user-id" not in session or not is_admin():
            session["post-login-return-url"] = request.path
            return redirect("/")
        else:
            return f(*args,**kws)
    return admin_required_wrapper

def tutor_required(f):
    @wraps(f)
    def tutor_required_wrapper(*args, **kws):
        if "user-id" not in session or not is_tutor():
            session["post-login-return-url"] = request.path
            return redirect("/")
        else:
            return f(*args,**kws)
    return tutor_required_wrapper

def get_flag_key(task_id):
    cur = get_db().cursor()
    cur.execute("SELECT flag_key FROM tasks WHERE task_id = ?", (task_id,))
    r = cur.fetchone()
    if r is None:
        return None
    return r["flag_key"]

def create_flag_key(task_id):
    key = struct.pack('>H', task_id) + os.urandom(32)
    return key

def find_flags(text):
    for m in re.finditer(current_app.config["FLAG_PREFIX"] + FLAG_BODY_REGEX, text):
        yield m.group(0)

def check_flag(flag):
    m = re.match(current_app.config["FLAG_PREFIX"] + FLAG_BODY_REGEX, flag)
    if m:
        raw = bytes.fromhex(m.group(1))
        data, checksum = raw[:-2], raw[-2:]
        for start in range(0, len(data), 2):
            checksum = bytes(a ^ b for a, b in zip(checksum, data[start:start + 2]))
        task_id = struct.unpack(">H", checksum)[0]
        key = get_flag_key(task_id)
        if not key:
            return None
        key_task_id, cipher_key = struct.unpack(">H32s", key)
        if key_task_id != task_id:
            return None # ???
        ci = AES.new(key=cipher_key, mode=AES.MODE_ECB)
        dflag = ci.decrypt(data)
        ftime, stored_task_id, pad = struct.unpack(">QH6s", dflag)
        if pad != b"\0" * 6 or stored_task_id != task_id:
            return None

        cur = get_db().cursor()
        cur.execute("SELECT task_short FROM tasks WHERE task_id=?", (task_id,))
        r = cur.fetchone()
        if not r:
            return None

        if current_app.config["FLAG_VALID_START"]*1e6 < ftime <= current_app.config["FLAG_VALID_END"]*1e6:
            return {"task_id": task_id, "task_short": r["task_short"], "ftime": ftime}
    return None

def generate_flag(task_id, time, flag_key):
    key_task_id, cipher_key = struct.unpack(">H32s", flag_key)
    if key_task_id != task_id:
        raise RuntimeError("generate_flag: task_id and flag_key do not match!")

    ci = AES.new(cipher_key, mode=AES.MODE_ECB)
    pad = b"\0" * 6
    data = struct.pack(">QH6s", time, task_id, pad)
    eflag = ci.encrypt(data)
    checksum = struct.pack(">H", task_id)
    for start in range(0, len(data), 2):
        checksum = bytes(a ^ b for a, b in zip(checksum, eflag[start:start + 2]))
    return current_app.config["FLAG_PREFIX"] + "{" + (eflag + checksum).hex() + "}"

def init_db():
    db = get_db()
    cur = db.execute("PRAGMA user_version");
    row = cur.fetchone()
    version = row[0] if row else 0
    cur.close()

    to_run = {}
    for file in os.listdir("db"):
        match = re.match(r"(\d+)\.sql", file)
        if not match:
            continue
        target_version = int(match.group(1))
        if version >= target_version:
            continue
        with open(f"db/{file}") as f:
            to_run[target_version] = f.read()

    if not to_run:
        # Nothing to do
        print(f"Nothing to do, database (version {version}) is up to date")
        return

    new_version = max(to_run)
    if version > 0:
        print(f"Upgrading database from version {version} to version {new_version}")
    else:
        print(f"Creating database (version {new_version})")
    # Check we have _all_ intermediate versions
    expected_keys = list(range(version + 1, new_version + 1))
    for key in expected_keys:
        if key not in to_run:
            raise FileNotFoundError(f"Missing DB upgrade script for version {key}")
        print(f"Executing db script {key}")
        db.executescript(to_run[key])

    # Can't prepare the PRAGMA, unfortunately.
    assert isinstance(new_version, int)
    db.execute(f"PRAGMA user_version = {new_version}")

    db.commit()
    if version > 0:
        print("Database upgraded")
    else:
        print("Database created")

def add_user(email, firstname, name, matrikel, pw):
    salt = os.getrandom(4)
    db_pw = pw_hash(pw.encode(),salt)
    db_pw = salt.hex() + ":" + db_pw.hex()
    cur = get_db().cursor()
    cur.execute("INSERT INTO users (vorname, nachname, email, password, matrikel, role,displayname) VALUES (?,?,?,?,?,0,?)", (firstname, name, email, db_pw, matrikel, f"{firstname} {name}"))

def set_task_status(task_id, ok):
    cur = get_db().cursor()
    cur.execute("SELECT status FROM tasks WHERE task_id=?", (task_id,))
    r = cur.fetchone()
    old_status = r['status']
    if old_status != ok:
        log_event(None, "task_status", f"Task {task_id} changed status from {old_status} to {ok}")

    cur.execute("UPDATE tasks SET last_check_time=strftime('%s','now'), status=? WHERE task_id=?", (ok, task_id))

def get_comments(task_id, team_id):
    comments = []

    cur = get_db().cursor()
    cur.execute("""
        SELECT comment, corrector, points, created_time
        FROM task_grading
        WHERE team_id = ? AND task_id = ?
    """, (team_id, task_id))

    for row in cur:
        comments.append({
            "message": row["comment"],
            "points": row["points"],
            "author": row["corrector"], # NB: This is a string, not a user ID
            "time": row["created_time"],
            "type": "grading"
        })

    cur.execute("""
        SELECT author, text, created_time
        FROM submission_comments
        WHERE team_id = ? AND task_id = ?
    """, (team_id, task_id))

    for row in cur:
        comments.append({
            "message": row["text"],
            "points": None,
            "author": row["author"],
            "time": row["created_time"],
            "type": "comment"
        })

    # Sort by time
    return sorted(comments, key=lambda c: c["time"])

def add_comment(task_id, team_id, author, text):
    cur = get_db().cursor()
    cur.execute("INSERT INTO submission_comments (task_id, team_id, author, text, created_time) VALUES (?, ?, ?, ?, strftime('%s', 'now'))", (task_id, team_id, author, text))

class Category(enum.Enum):
    STUDENT_INCIDENT = "student_incident"
    TASK_STATUS = "task_status"

def log_event(user_id, category, message):
    if isinstance(category, Category):
        category = category.value
    cur = get_db().cursor()
    cur.execute("INSERT INTO logs (time, user_id, category, message) VALUES (strftime('%s','now'),?,?,?)", (user_id, category, message))
