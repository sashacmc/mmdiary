#!/usr/bin/python3

import argparse
import logging
import os
import sqlite3

from mmdiary.utils import log, medialib
from mmdiary.utils.medialib import get_date_from_timestring

PROCESSED_NONE = 0
PROCESSED_IN_PROCESS = 1
PROCESSED_CONVERTED = 2
PROCESSED_UPLOADED = 3

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


class DateLib:
    def __init__(self, scan_paths=None, db_file=None):
        if scan_paths is None:
            scan_paths = list(
                filter(
                    None,
                    os.getenv("VIDEO_LIB_ROOTS").split(":"),
                ),
            )
        if db_file is None:
            db_file = os.getenv("VIDEO_LIB_DB")

        self.__conn = sqlite3.connect(os.path.expanduser(db_file))
        self.__conn.executescript(SCHEMA)

        self.__scan_paths = scan_paths

    def __del__(self):
        self.__conn.commit()

    def check_file(self, filename):
        c = self.__conn.cursor()
        res = c.execute(
            "SELECT date FROM files\
                         WHERE filename=?",
            (filename,),
        )
        res = res.fetchall()
        if len(res) == 0:
            return None
        return res[0][0]

    def add_file(self, date, filename):
        logging.debug("Add: %s to %s", filename, date)
        c = self.__conn.cursor()
        try:
            c.execute(
                "INSERT \
                 INTO dates (date, processed) \
                 VALUES (?, ?) \
                 ON CONFLICT(date) \
                 DO UPDATE \
                 SET processed=?",
                (date, PROCESSED_NONE, PROCESSED_NONE),
            )
            c.execute(
                "INSERT \
                 INTO files (date, filename) \
                 VALUES (?, ?)",
                (date, filename),
            )
        except Exception:
            logging.exception("add_file failed")

    def __set_processed(self, date, processed, url):
        c = self.__conn.cursor()
        c.execute("begin")
        try:
            c = self.__conn.cursor()
            res = c.execute(
                "SELECT processed FROM dates \
                                  WHERE date=? ",
                (date,),
            )
            res = res.fetchall()
            if len(res) != 1:
                raise UserWarning(f"checks processed failed: {res}")
            if res[0][0] == processed:
                c.execute("rollback")
                return False

            if url is None:
                c.execute(
                    "UPDATE dates \
                     SET processed=? \
                     WHERE date=?",
                    (processed, date),
                )
            else:
                c.execute(
                    "UPDATE dates \
                     SET processed=?, url=? \
                     WHERE date=?",
                    (processed, url, date),
                )
            if c.rowcount != 1:
                raise UserWarning(f"set processed failed: {c.rowcount}")

            c.execute("commit")
            return True
        except Exception:
            c.execute("rollback")
            logging.exception("__set_processed failed")
            raise

    def set_not_processed(self, date):
        return self.__set_processed(date, PROCESSED_NONE, None)

    def set_in_progress(self, date):
        return self.__set_processed(date, PROCESSED_IN_PROCESS, None)

    def set_converted(self, date):
        return self.__set_processed(date, PROCESSED_CONVERTED, None)

    def set_uploaded(self, date, url):
        return self.__set_processed(date, PROCESSED_UPLOADED, url)

    def __get_by_state(self, processed):
        c = self.__conn.cursor()
        res = c.execute(
            "SELECT date, url FROM dates \
                              WHERE processed=? \
                              ORDER BY date",
            (processed,),
        )
        return res.fetchall()

    def get_nonprocessed(self):
        return self.__get_by_state(PROCESSED_NONE)

    def get_converted(self):
        return self.__get_by_state(PROCESSED_CONVERTED)

    def get_files_by_date(self, date, for_upload=False):
        c = self.__conn.cursor()
        res = c.execute(
            "SELECT filename FROM files \
                             WHERE date=?",
            (date,),
        )
        afs = [medialib.MediaFile(row[0]) for row in res.fetchall()]
        afs.sort(key=lambda af: af.json()["recordtime"])
        if for_upload:
            afs = list(filter(lambda af: af.json().get("upload", True), afs))
        return afs

    def scan(self):
        for path in self.__scan_paths:
            logging.info("Process: %s", path)
            al = medialib.MediaLib(path)
            for af in al.get_processed():
                fname = af.name()
                if self.check_file(fname) is None:
                    self.add_file(
                        get_date_from_timestring(af.json()["recordtime"]),
                        fname,
                    )

    def disable_video(self, filename):
        date = self.check_file(filename)
        if date is None:
            logging.warning("File not in DB")

        af = medialib.MediaFile(filename)
        data = af.json()
        data["upload"] = False
        af.save_json(data)

        self.set_not_processed(date)


def __args_parse():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-a',
        '--action',
        help='Action',
        required=True,
        choices=[
            'scan',
            'disable_video',
        ],
    )
    parser.add_argument('-f', '--file', help='File name')
    return parser.parse_args()


def main():
    args = __args_parse()
    log.init_logger(level=logging.DEBUG)
    lib = DateLib()

    if args.action == 'scan':
        lib.scan()
    if args.action == 'disable_video':
        lib.disable_video(args.file)


if __name__ == "__main__":
    main()
