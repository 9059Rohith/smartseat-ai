"""Transactional restaurant operations and camera-driven table transitions."""
from contextlib import contextmanager
import hashlib
import hmac
import json
from pathlib import Path
import secrets
import sqlite3
from threading import RLock
import time
from datetime import datetime, timezone


class Conflict(ValueError):
    pass


class Missing(LookupError):
    pass


SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS cameras (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, kind TEXT NOT NULL,
 source TEXT NOT NULL, entrance TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS tables (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, capacity INTEGER NOT NULL,
 camera INTEGER REFERENCES cameras(id), zone TEXT NOT NULL, created REAL NOT NULL,
 state TEXT NOT NULL DEFAULT 'available', people INTEGER NOT NULL DEFAULT 0,
 since REAL NOT NULL, greeted REAL, vision INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS visits (
 id INTEGER PRIMARY KEY, table_id INTEGER NOT NULL REFERENCES tables(id),
 started REAL NOT NULL, greeted REAL, ended REAL, cleaned REAL, party_size INTEGER
);
CREATE UNIQUE INDEX IF NOT EXISTS open_visit ON visits(table_id) WHERE ended IS NULL;
CREATE TABLE IF NOT EXISTS queue (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL, size INTEGER NOT NULL, joined REAL NOT NULL,
 status TEXT NOT NULL DEFAULT 'waiting', table_id INTEGER REFERENCES tables(id),
 called REAL, seated REAL
);
CREATE TABLE IF NOT EXISTS reservations (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL, size INTEGER NOT NULL,
 table_id INTEGER NOT NULL REFERENCES tables(id), start REAL NOT NULL,
 end REAL NOT NULL, status TEXT NOT NULL DEFAULT 'booked'
);
CREATE TABLE IF NOT EXISTS events (
 id INTEGER PRIMARY KEY, at REAL NOT NULL, kind TEXT NOT NULL,
 table_id INTEGER REFERENCES tables(id), detail TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS events_time ON events(at);
CREATE TABLE IF NOT EXISTS users (
 name TEXT PRIMARY KEY COLLATE NOCASE, secret TEXT NOT NULL, role TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
 digest TEXT PRIMARY KEY, name TEXT NOT NULL REFERENCES users(name), expires REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS surface_checks (
 table_id INTEGER PRIMARY KEY REFERENCES tables(id), at REAL NOT NULL,
 state TEXT NOT NULL, items TEXT NOT NULL
);
"""


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1)
    return f"{salt}:{digest.hex()}"


class Store:
    def __init__(self, path, *, enter=4, leave=9, greet=300):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.enter, self.leave, self.greet = enter, leave, greet
        self.lock = RLock()
        self.pending = {}
        self.last = {}
        self.observed = set()
        with self.db() as db:
            db.executescript(SCHEMA)

    @contextmanager
    def db(self, write=False):
        with self.lock:
            db = sqlite3.connect(self.path, timeout=5)
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            try:
                if write:
                    db.execute("BEGIN IMMEDIATE")
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise
            finally:
                db.close()

    @staticmethod
    def rows(db, sql, params=()):
        return [dict(row) for row in db.execute(sql, params)]

    @staticmethod
    def one(db, sql, params=()):
        row = db.execute(sql, params).fetchone()
        if row is None:
            raise Missing("That record no longer exists.")
        return dict(row)

    @staticmethod
    def event(db, now, kind, table=None, detail=""):
        db.execute("INSERT INTO events(at,kind,table_id,detail) VALUES (?,?,?,?)",
                   (now, kind, table, detail))

    def add_camera(self, name, kind, source):
        with self.db(True) as db:
            return db.execute("INSERT INTO cameras(name,kind,source) VALUES (?,?,?)",
                              (name, kind, source)).lastrowid

    def camera(self, camera_id):
        with self.db() as db:
            return self.one(db, "SELECT * FROM cameras WHERE id=?", (camera_id,))

    def camera_config(self, camera_id):
        with self.db() as db:
            camera = self.one(db, "SELECT * FROM cameras WHERE id=?", (camera_id,))
            tables = self.rows(db, "SELECT id,name,zone,state FROM tables WHERE camera=?", (camera_id,))
            for table in tables:
                table["zone"] = json.loads(table["zone"])
            return json.loads(camera["entrance"]), tables

    def set_entrance(self, camera_id, zone):
        with self.db(True) as db:
            self.one(db, "SELECT id FROM cameras WHERE id=?", (camera_id,))
            db.execute("UPDATE cameras SET entrance=? WHERE id=?", (json.dumps(zone), camera_id))

    def add_table(self, name, capacity, camera, zone, now=None, *, vision=True):
        now = time.time() if now is None else now
        with self.db(True) as db:
            return db.execute(
                "INSERT INTO tables(name,capacity,camera,zone,created,since,vision) VALUES (?,?,?,?,?,?,?)",
                (name, capacity, camera, json.dumps(zone), now, now, vision)).lastrowid

    def edit_table(self, table_id, name, capacity, camera, zone, vision):
        with self.db(True) as db:
            table = self.one(db, "SELECT * FROM tables WHERE id=?", (table_id,))
            if (camera != table["camera"] or capacity < table["capacity"]) and table["state"] != "available":
                raise Conflict("Clear this table before changing its camera or reducing its capacity.")
            largest = db.execute("SELECT max(size) FROM reservations WHERE table_id=? AND status='booked'",
                                 (table_id,)).fetchone()[0]
            if largest and capacity < largest:
                raise Conflict("A future reservation needs more seats at this table.")
            db.execute("UPDATE tables SET name=?,capacity=?,camera=?,zone=?,vision=? WHERE id=?",
                       (name, capacity, camera, json.dumps(zone), vision, table_id))
            db.execute('DELETE FROM surface_checks WHERE table_id=?',(table_id,))
            self.observed.discard(table_id)
            self.pending.pop(table_id, None)

    def _start(self, db, table_id, now, size=None):
        db.execute("UPDATE tables SET state='occupied', since=?, greeted=NULL WHERE id=?", (now, table_id))
        db.execute("INSERT INTO visits(table_id,started,party_size) VALUES (?,?,?)", (table_id, now, size))
        self.event(db, now, "occupied", table_id)

    def _end(self, db, table_id, now):
        db.execute("UPDATE tables SET state='cleaning', since=?, people=0 WHERE id=?", (now, table_id))
        db.execute("UPDATE visits SET ended=max(started,?) WHERE table_id=? AND ended IS NULL", (now, table_id))
        self.event(db, now, "cleaning", table_id)

    def table_action(self, table_id, action, now=None):
        now = time.time() if now is None else now
        with self.db(True) as db:
            row = self.one(db, "SELECT * FROM tables WHERE id=?", (table_id,))
            state = row["state"]
            if action == "occupy" and state == "available":
                self._check_table(db, table_id, 1, now)
                self._start(db, table_id, now)
            elif action == "greet" and state in ("occupied", "waiting") and row["greeted"] is None:
                db.execute("UPDATE tables SET state='occupied',greeted=? WHERE id=?", (now, table_id))
                db.execute("UPDATE visits SET greeted=? WHERE table_id=? AND ended IS NULL", (now, table_id))
                self.event(db, now, "greeted", table_id)
            elif action == "depart" and state in ("occupied", "waiting"):
                self._end(db, table_id, now)
            elif action == "clean" and state == "cleaning":
                db.execute("UPDATE tables SET state='available',since=?,greeted=NULL WHERE id=?", (now, table_id))
                db.execute("""UPDATE visits SET cleaned=? WHERE id=(
                           SELECT id FROM visits WHERE table_id=? ORDER BY id DESC LIMIT 1)""", (now, table_id))
                self.event(db, now, "cleaned", table_id)
            else:
                raise Conflict("That action is no longer available for this table.")
            self.pending.pop(table_id, None)

    def camera_offline(self, camera_id):
        with self.db(True) as db:
            db.execute("UPDATE tables SET people=0 WHERE camera=?", (camera_id,))
            db.execute("UPDATE surface_checks SET state='unknown',items='[]' WHERE table_id IN (SELECT id FROM tables WHERE camera=?)",(camera_id,))
            for row in db.execute("SELECT id FROM tables WHERE camera=?", (camera_id,)):
                self.pending.pop(row[0], None)
                self.observed.discard(row[0])
            self.last.pop(camera_id, None)

    def observe(self, camera_id, counts, now=None, entries=0):
        now = time.time() if now is None else now
        with self.db(True) as db:
            last = self.last.get(camera_id)
            if last is not None and now <= last:
                return
            self.last[camera_id] = now
            if entries:
                self.event(db, now, "entry", detail=str(entries))
            for row in db.execute("SELECT * FROM tables WHERE camera=?", (camera_id,)).fetchall():
                table_id = row["id"]
                if table_id not in counts:
                    continue
                self.observed.add(table_id)
                count = counts[table_id]
                db.execute("UPDATE tables SET people=? WHERE id=?", (count, table_id))
                target = None
                if row["vision"]:
                    if row["state"] == "available" and count and not self._hold(db, table_id, now):
                        target = "occupied"
                    elif row["state"] in ("occupied", "waiting") and not count:
                        target = "cleaning"
                if target is None:
                    self.pending.pop(table_id, None)
                    continue
                candidate = self.pending.get(table_id)
                if not candidate or candidate[0] != target or last is None or now - last > 3:
                    self.pending[table_id] = (target, now)
                    continue
                if now - candidate[1] >= (self.enter if target == "occupied" else self.leave):
                    if target == "occupied":
                        self._start(db, table_id, now, count)
                    else:
                        self._end(db, table_id, now)
                    self.pending.pop(table_id, None)

    def observe_surfaces(self,camera_id,checks,now,*,expected_zones):
        with self.db(True) as db:
            valid={r['id']:json.loads(r['zone']) for r in db.execute('SELECT id,zone FROM tables WHERE camera=?',(camera_id,))}
            for key,check in checks.items():
                if key not in valid or expected_zones.get(key)!=valid[key]:continue
                db.execute('''INSERT INTO surface_checks VALUES(?,?,?,?)
                    ON CONFLICT(table_id) DO UPDATE SET at=excluded.at,state=excluded.state,items=excluded.items
                    WHERE excluded.at>surface_checks.at''',
                    (key,now,check['state'],json.dumps(check['items'])))

    def tick(self, now=None):
        now = time.time() if now is None else now
        with self.db(True) as db:
            for row in db.execute("SELECT id FROM tables WHERE state='occupied' AND greeted IS NULL AND since<=?",
                                  (now - self.greet,)).fetchall():
                db.execute("UPDATE tables SET state='waiting' WHERE id=?", (row["id"],))
                self.event(db, now, "service_due", row["id"])
            db.execute("""UPDATE queue SET status='waiting', table_id=NULL, called=NULL
                          WHERE status='called' AND called<=?""", (now - 600,))
            db.execute("UPDATE reservations SET status='no_show' WHERE status='booked' AND end<=?", (now,))

    @staticmethod
    def _hold(db, table_id, now, party=None, reservation=None):
        return db.execute(
            """SELECT 1 FROM queue WHERE table_id=? AND status='called' AND called>? AND id!=?
               UNION ALL
               SELECT 1 FROM reservations WHERE table_id=? AND status='booked' AND start<=? AND end>? AND id!=?
               LIMIT 1""", (table_id, now - 600, party or -1, table_id, now + 900, now, reservation or -1)).fetchone()

    def _check_table(self, db, table_id, size, now, party=None, reservation=None):
        row = self.one(db, "SELECT * FROM tables WHERE id=?", (table_id,))
        if row["capacity"] < size or row["state"] != "available":
            raise Conflict("Choose an available table with enough seats.")
        if self._hold(db, table_id, now, party, reservation):
            raise Conflict("This table is held for a different party.")

    def add_party(self, name, size, now=None):
        now = time.time() if now is None else now
        with self.db(True) as db:
            party = db.execute("INSERT INTO queue(name,size,joined) VALUES (?,?,?)", (name, size, now)).lastrowid
            self.event(db, now, "party_joined")
            return party

    def seat(self, party_id, table_id, now=None, call=False):
        now = time.time() if now is None else now
        with self.db(True) as db:
            party = self.one(db, "SELECT * FROM queue WHERE id=?", (party_id,))
            if party["status"] not in ("waiting", "called"):
                raise Conflict("This party has already left the waitlist.")
            self._check_table(db, table_id, party["size"], now, party=party_id)
            if call:
                db.execute("UPDATE queue SET status='called',table_id=?,called=? WHERE id=?",
                           (table_id, now, party_id))
                self.event(db, now, "table_ready", table_id)
            else:
                db.execute("UPDATE queue SET status='seated',table_id=?,seated=? WHERE id=?",
                           (table_id, now, party_id))
                self._start(db, table_id, now, party["size"])
                self.event(db, now, "party_seated", table_id)

    def cancel_party(self, party_id):
        with self.db(True) as db:
            result = db.execute("UPDATE queue SET status='cancelled' WHERE id=? AND status IN ('waiting','called')",
                                (party_id,))
            if not result.rowcount:
                raise Conflict("This party is no longer waiting.")

    def reserve(self, name, size, table_id, start, end, now=None):
        now = time.time() if now is None else now
        if end <= start or start < now - 60:
            raise Conflict("Choose a future start and a valid duration.")
        with self.db(True) as db:
            table = self.one(db, "SELECT * FROM tables WHERE id=?", (table_id,))
            if table["capacity"] < size:
                raise Conflict("This table cannot fit the party.")
            if db.execute("""SELECT 1 FROM reservations WHERE table_id=? AND status='booked'
                             AND start<? AND end>?""", (table_id, end, start)).fetchone():
                raise Conflict("This table already has an overlapping reservation.")
            if start <= now + 900 and (table["state"] != "available" or self._hold(db, table_id, now)):
                raise Conflict("This table is busy or held.")
            result = db.execute("""INSERT INTO reservations(name,size,table_id,start,end)
                                   VALUES (?,?,?,?,?)""", (name, size, table_id, start, end))
            self.event(db, now, "reserved", table_id)
            return result.lastrowid

    def reservation_action(self, reservation, action, now=None):
        now = time.time() if now is None else now
        with self.db(True) as db:
            row = self.one(db, "SELECT * FROM reservations WHERE id=?", (reservation,))
            if row["status"] != "booked" or row["end"] <= now:
                raise Conflict("This reservation is no longer active.")
            if action == "seat":
                if now < row["start"] - 900:
                    raise Conflict("Seating opens 15 minutes before the reservation.")
                self._check_table(db, row["table_id"], row["size"], now, reservation=reservation)
                self._start(db, row["table_id"], now, row["size"])
                status = "seated"
            else:
                status = "cancelled"
            db.execute("UPDATE reservations SET status=? WHERE id=?", (status, reservation))
            self.event(db, now, f"reservation_{status}", row["table_id"])

    def snapshot(self, now=None):
        now = time.time() if now is None else now
        with self.db() as db:
            tables = self.rows(db, "SELECT * FROM tables ORDER BY id")
            parties = self.rows(db, "SELECT * FROM queue WHERE status IN ('waiting','called') ORDER BY joined,id")
            for table in tables:
                surface=db.execute('SELECT at,state,items FROM surface_checks WHERE table_id=?',(table['id'],)).fetchone()
                table['surface']=(dict(at=surface['at'],state=surface['state'],items=json.loads(surface['items']))
                    if surface and 0<=now-surface['at']<=5 else dict(at=None,state='unknown',items=[]))
                table["zone"] = json.loads(table["zone"])
                table["held"] = bool(self._hold(db, table["id"], now))
                table["display"] = ("reserved" if table["held"] and table["state"] == "available" else table["state"])
                table["observed"] = (table["id"] in self.observed
                                     and now - self.last.get(table["camera"], 0) <= 5)
                if table["camera"] is not None and table["vision"] and not table["observed"]:
                    table["display"] = "unknown"
            for party in parties:
                party["suggested"] = [
                    table["id"] for table in sorted(tables, key=lambda row: (row["capacity"], row["id"]))
                    if table["display"] == "available" and table["capacity"] >= party["size"]
                    and not self._hold(db, table["id"], now, party=party["id"])
                ]
            return dict(now=now, tables=tables, queue=parties,
                        cameras=self.rows(db, "SELECT id,name,kind,entrance FROM cameras ORDER BY id"),
                        reservations=self.rows(db, """SELECT reservations.*,tables.name AS table_name
                            FROM reservations JOIN tables ON table_id=tables.id
                            WHERE end>? ORDER BY start LIMIT 250""", (now - 86400,)),
                        events=self.rows(db, """SELECT events.*,tables.name AS table_name
                            FROM events LEFT JOIN tables ON table_id=tables.id
                            ORDER BY events.id DESC LIMIT 30"""))

    def report(self, start, end, timezone_offset=0):
        def average(values):
            return round(sum(values) / len(values), 1) if values else None

        with self.db() as db:
            tables = self.rows(db, "SELECT id,name,created FROM tables WHERE created<? ORDER BY id", (end,))
            visits = self.rows(db, """SELECT * FROM visits WHERE started<? AND coalesce(ended,?)>=?""",
                               (end, end, start))
            entries = self.rows(db, "SELECT detail FROM events WHERE kind='entry' AND at>=? AND at<?", (start, end))
            waits = self.rows(db, "SELECT seated-joined AS seconds FROM queue WHERE seated>=? AND seated<?",
                              (start, end))
            cleaning = self.rows(db, "SELECT cleaned AS at,cleaned-ended AS seconds FROM visits WHERE cleaned>=? AND cleaned<?",
                                 (start, end))
            closed = [v for v in visits if v["ended"] is not None and start <= v["ended"] < end]
            greeted = [v for v in visits if v["greeted"] is not None and start <= v["greeted"] < end]
            buckets = {}
            occupied_total, capacity_total = 0, 0
            for table in tables:
                relevant = [v for v in visits if v["table_id"] == table["id"]]
                occupied = sum(max(0, min(v["ended"] or end, end) - max(v["started"], start)) for v in relevant)
                capacity = end - max(table["created"], start)
                table.update(seconds=round(occupied), occupancy=round(100 * occupied / capacity, 1) if capacity else 0,
                             turnover=sum(v["table_id"] == table["id"] for v in closed))
                occupied_total += occupied
                capacity_total += capacity
            offset=timezone_offset*60
            for visit in visits:
                if start <= visit["started"] < end:
                    hour = int((visit["started"]+offset)//3600)*3600-offset
                    buckets[hour] = buckets.get(hour, 0) + 1
            day_start=int((start+offset)//86400)*86400-offset
            daily=[]
            while day_start<end:
                left,right=max(day_start,start),min(day_start+86400,end)
                seated=[v for v in visits if left<=v['started']<right]
                occupied=sum(max(0,min(v['ended'] or right,right)-max(v['started'],left)) for v in visits)
                capacity=sum(max(0,right-max(t['created'],left)) for t in tables)
                daily.append(dict(date=datetime.fromtimestamp(day_start+offset,timezone.utc).date().isoformat(),
                    start=left,end=right,seatings=len(seated),guests=sum(v['party_size'] or 0 for v in seated),
                    unknown_party_size=sum(v['party_size'] is None for v in seated),
                    occupied_seconds=round(occupied),occupancy=round(100*occupied/capacity,1) if capacity else 0,
                    cleaned=sum(left<=row['at']<right for row in cleaning),
                    turnover=sum(v['ended'] is not None and left<=v['ended']<right for v in visits)))
                day_start+=86400
            seated=[v for v in visits if start<=v['started']<end]
            return dict(start=start, end=end, tables=tables, daily=daily,timezone_offset=timezone_offset,
                        seatings=len(seated),guests=sum(v['party_size'] or 0 for v in seated),cleaned=len(cleaning),
                        footfall=sum(int(row["detail"]) for row in entries),
                        occupancy=round(100 * occupied_total / capacity_total, 1) if capacity_total else 0,
                        turnover=len(closed), dining=average([v["ended"] - v["started"] for v in closed]),
                        response=average([v["greeted"] - v["started"] for v in greeted]),
                        wait=average([w["seconds"] for w in waits]), cleaning=average([w["seconds"] for w in cleaning]),
                        hourly=[dict(hour=h, visits=n) for h, n in sorted(buckets.items())])

    def add_user(self, name, password, role):
        with self.db(True) as db:
            db.execute("INSERT INTO users VALUES (?,?,?)", (name, hash_password(password), role))

    def users_exist(self):
        with self.db() as db:
            return bool(db.execute("SELECT 1 FROM users LIMIT 1").fetchone())

    def login(self, name, password):
        with self.db(True) as db:
            user = db.execute("SELECT * FROM users WHERE name=?", (name,)).fetchone()
            encoded = user["secret"] if user else hash_password("invalid", "0" * 32)
            valid = hmac.compare_digest(hash_password(password, encoded.split(":")[0]), encoded)
            if not user or not valid:
                return None
            token = secrets.token_urlsafe(32)
            now = time.time()
            db.execute("DELETE FROM sessions WHERE expires<=?", (now,))
            db.execute("INSERT INTO sessions VALUES (?,?,?)", (hashlib.sha256(token.encode()).hexdigest(),
                                                               user["name"], now + 43200))
            return token

    def session(self, token):
        if not token or len(token) > 100:
            return None
        with self.db() as db:
            row = db.execute("""SELECT users.name,users.role FROM sessions JOIN users USING(name)
                                WHERE digest=? AND expires>?""",
                             (hashlib.sha256(token.encode()).hexdigest(), time.time())).fetchone()
            return dict(row) if row else None

    def logout(self, token):
        with self.db(True) as db:
            db.execute("DELETE FROM sessions WHERE digest=?", (hashlib.sha256(token.encode()).hexdigest(),))

