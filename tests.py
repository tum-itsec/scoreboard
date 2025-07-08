import unittest
import app
import contextlib
import flask
import time
import io
import re
import secrets
import tempfile
import board.util

samplecsv = b"""team;task;points;comment;internal_comment;corrector
1;0;0.5;Test;Test;Fabian
"""

class TestScoreboard(unittest.TestCase):
    def setUp(self):
        dt = time.strptime("2020-12-22-00-00","%Y-%m-%d-%H-%M")
        dts = int(time.mktime(dt))
        st = time.strptime("2020-12-19-00-00","%Y-%m-%d-%H-%M")
        sts = int(time.mktime(st))

        app.app.config["DATABASE"] = ":memory:"
        app.app.config["FLAG_KEY"] = bytes.fromhex("a5ab09c312b98eb0b7da701b967aecf9f4754508f03acb89240872e5ffa552a3")
        app.app.config["FLAG_VALID_START"] = sts
        app.app.config["FLAG_VALID_END"] = dts
        app.app.config["TASK_STATUS_APIKEY"] = secrets.token_hex(16)

        with contextlib.ExitStack() as stack:
            self.appctx = stack.enter_context(app.app.app_context())
            self.addCleanup(stack.pop_all().close)

        app.init_db()
        app.add_user("testa","testa","testa", None, "testa")
        app.add_user("testb","testb","testb", None, "testb")
        app.add_user("testc","testc","testc", None, "testc")
        app.add_user("testd","testd","testd", None, "testd")
        app.add_user("admin","admin","admin", None, "admin")
        app.create_team([3,4])


        cur = app.get_db().cursor()
        # cur.execute("""INSERT INTO tasks (task_short, task_desc, flag_uid, from_date, due_date, needed, max_points, order_num) values (?, ?, ?, ?, ?, ?, ?, ?)""", ("0", "Testtask", 2000, sts, dts, 1, 5, 0))
        flag_key = board.util.create_flag_key(1)
        cur.execute("""INSERT INTO tasks (task_id, task_short, task_long, markdown, markdown_rendered, filename, url, from_date, due_date, needed, order_num, max_points, flag_key) VALUES(1, '1', 'Blabla', 'asdasd', 'asdasd', NULL, NULL, ?, ?, 1, 1, 5, ?)""", (sts, dts, flag_key))
        self.testflag = board.util.generate_flag(1, int(app.app.config["FLAG_VALID_START"]*1e6 + 1000), flag_key)
        cur.execute("""UPDATE users SET role=1 WHERE id = 5""")

    def log_me_in(self, client, username, password):
            return client.post("/alternative-login", data={"email": username, "password": password}, follow_redirects=True)

    def logout(self, client):
        return client.get("/logout")

    def test_login(self):
        with app.app.test_client() as client:
            rv = client.get("/", follow_redirects=True)
            self.assertIn(b"Scoreboard", rv.data)

            rv = self.log_me_in(client, "testa", "testa")
            self.assertIn(b"signed in as testa testa", rv.data)

    def test_team_join(self):
        with app.app.test_client() as client:
            self.log_me_in(client, "testa", "testa")
            rv = client.get("/team")
            
            import re
            code = re.search(b'<p class="teamname">([^<]*)</p>', rv.data).group(1)
            self.logout(client)
            rv = self.log_me_in(client, "testb", "testb")
            rv = client.post("/team/join", data={"join_code": code},follow_redirects=True)
            self.assertIn(b"Team 2", rv.data)

    def test_team_changename(self):
        with app.app.test_client() as client:
            self.log_me_in(client, "testc", "testc")
            rv = client.post("/team/changename", data={"teamname": "foobar"}, follow_redirects=True);
            self.assertIn(b"foobar", rv.data)

    def test_flag_submit_without_team(self):
        with app.app.test_client() as client:
            rv = self.log_me_in(client, "testa", "testa")
            rv = client.post("/flag", data={"flag": "flag{foobar}"}, follow_redirects=True)
            self.assertIn(b"You have to form a team with another student in order to submit flags!", rv.data)

    def test_flag_submit_invalid(self):
        with app.app.test_client() as client:
            rv = self.log_me_in(client, "testc", "testc")
            rv = client.post("/flag", data={"flag": "flag{foobar}"}, follow_redirects=True)
            self.assertIn(b"This does not look like a flag :/", rv.data)
    
    def test_flag_submit(self):
        with app.app.test_client() as client:
            rv = self.log_me_in(client, "testc", "testc")
            rv = client.post("/flag", data={"flag": self.testflag}, follow_redirects=True)
            self.assertIn(b"Looks like a flag", rv.data)

    def test_upload_solution(self):
        with app.app.test_client() as client:
            rv = self.log_me_in(client, "testd", "testd")
            rv = client.get("/abgaben")
            
            rv = client.post("/abgaben/1", data={"fileupload": (io.BytesIO(b"Das ist ein Test"), "test.txt")}, follow_redirects=True)
            rv = client.get("/abgaben/1")
            self.assertEqual(b"Das ist ein Test", rv.data)

    def test_upload_grading_csv(self):
        with app.app.test_client() as client:
            self.log_me_in(client, "admin", "admin")

            # Upload two times to check if duplicates are elimnated
            for i in range(2):
                rv = client.post("/grade-upload", data={"gradefile": (io.BytesIO(samplecsv),"sample.csv")}, follow_redirects=True)
                if i == 0:
                    self.assertIn(b"Neue Benotungen: 1", rv.data)
                else:
                    self.assertIn(b"vorhanden und ignoriert: 1", rv.data)
                changeset = re.search(b'value="([^"]*)" name="changeset"', rv.data).group(1)
                rv = client.post("/grade-upload", data = {"changeset": changeset}, follow_redirects=True)
                self.assertIn(b"Benotung importiert", rv.data)
            self.logout(client)

            self.log_me_in(client, "testc", "testc")
            rv = client.get("/abgaben")
            self.assertIn("Points awarded for the tasks you solved so far: <b>0.5 of 5.0 points</b>".encode(), rv.data)

    def test_flagcheck(self):
        with app.app.test_client() as client:
            self.log_me_in(client, "admin", "admin")
            rv = client.get("/flagcheck")
            self.assertEqual(rv.status_code, 200)

    def test_teamoverview(self):
        with app.app.test_client() as client:
            self.log_me_in(client, "admin", "admin")
            rv = client.get("/teaminfo", follow_redirects=True)
            self.assertEqual(rv.status_code, 200)
            rv = client.get("/teaminfo/1", follow_redirects=True)
            self.assertEqual(rv.status_code, 200)

    def test_sshkeys(self):
        with app.app.test_client() as client:
            rv = self.log_me_in(client, "testd", "testd")
            rv = client.get("/sshkeys")
            self.assertEqual(rv.status_code, 200)

    def test_healthcheck_post(self):
        with app.app.test_client() as client:
            rv = client.post("/tasks/status/update", data={"APIKEY": app.app.config["TASK_STATUS_APIKEY"], "output": self.testflag})
            self.log_me_in(client, "admin", "admin")
            rv = client.get("/tasks/status")
            print(rv.get_json())

if __name__ == "__main__":
    unittest.main()
