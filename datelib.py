#!/usr/bin/python3

import os
import logging
import audiolib
import sqlite3

SCHEMA = '''
CREATE TABLE IF NOT EXISTS files (
    "date" TEXT,
    "filename" TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS files_filename ON files (filename);

CREATE TABLE IF NOT EXISTS dates (
    "date" TEXT,
    "url" TEXT,
    "processed" INTEGER
);

CREATE UNIQUE INDEX IF NOT EXISTS dates_date ON dates (date);
'''


class DateLib(object):
    def __init__(self, scan_paths, db_file):
        self.__conn = sqlite3.connect(os.path.expanduser(db_file))
        self.__conn.executescript(SCHEMA)

        self.__scan_paths = scan_paths

    def check_file(self, filename):
        c = self.__conn.cursor()
        res = c.execute(
            "SELECT date FROM files\
                         WHERE filename=?",
            (filename,),
        )
        return len(res.fetchall()) != 0

    def add_file(self, date, filename):
        c = self.__conn.cursor()
        c.execute("begin")
        try:
            c.execute(
                "INSERT \
                 INTO files (date, filename) \
                 VALUES (?, ?)",
                (date, filename),
            )
            # TODO: check for update
            c.execute(
                "INSERT OR REPLACE \
                 INTO dates (date, processed) \
                 VALUES (?, ?)",
                (date, False),
            )
            c.execute("commit")
        except Exception:
            c.execute("rollback")
            logging.exception("add_file failed")

    def scan(self):
        for path in self.__scan_paths:
            al = audiolib.AudioLib(path)
            for af in al.get_processed():
                fname = af.name()
                if not self.check_file(fname):
                    prop = af.prop()
                    date = prop.time().strftime("%Y-%m-%d")
                    self.add_file(date, fname)


def main():
    scan_paths = "/mnt/multimedia/NEW/Video/".split(":")
    db_file = "test.sqlite3"
    lib = DateLib(scan_paths, db_file)
    lib.scan()


if __name__ == "__main__":
    main()
