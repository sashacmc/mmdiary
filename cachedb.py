#!/usr/bin/python3

import os
import atexit
import sqlite3
import argparse
import threading

SCHEMA = '''
CREATE TABLE IF NOT EXISTS existing_pages (
    "filename" TEXT,
    "processtime" TEXT,
    "bid" TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS existing_pages_filename ON existing_pages (filename);
'''


class CacheDB(object):
    def __init__(self, filename):
        self.__conn = sqlite3.connect(
            os.path.expanduser(filename), check_same_thread=False
        )

        self.__conn.executescript(SCHEMA)
        self.__lock = threading.RLock()
        atexit.register(self.commit)

    def __del__(self):
        self.commit()

    def commit(self):
        with self.__lock:
            self.__conn.commit()

    def rollback(self):
        with self.__lock:
            self.__conn.rollback()

    def list_existing_pages(self):
        with self.__lock:
            self.commit()
            c = self.__conn.cursor()
            res = c.execute('SELECT filename FROM existing_pages')
            return [r[0] for r in res.fetchall()]

    def clean_existing_pages(self):
        with self.__lock:
            self.commit()
            c = self.__conn.cursor()
            c.execute('DELETE FROM existing_pages')
            self.commit()

    def add_existing_page(self, filename, processtime, bid):
        with self.__lock:
            c = self.__conn.cursor()
            c.execute(
                'INSERT OR REPLACE \
                 INTO existing_pages (filename, processtime, bid) \
                 VALUES (?, ?, ?)',
                (filename, processtime, bid),
            )

    def check_existing_pages(self, filename):
        with self.__lock:
            c = self.__conn.cursor()
            res = c.execute(
                'SELECT processtime, bid FROM existing_pages\
                             WHERE filename=?',
                (filename,),
            )
            return res.fetchone()

    def remove_from_existing_pages(self, filename):
        with self.__lock:
            c = self.__conn.cursor()
            c.execute(
                'DELETE FROM existing_pages WHERE filename=?', (filename,)
            )


def args_parse():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-a',
        '--action',
        help='Action',
        required=True,
        choices=[
            'clean_cache',
            'list_cache',
            'remove_from_cache',
        ],
    )
    parser.add_argument('-d', '--database', help='Database file')
    parser.add_argument('-f', '--file', help='File name')
    return parser.parse_args()


def main():
    args = args_parse()
    db = CacheDB(args.database)

    if args.action == 'clean_cache':
        db.clean_existing_pages()
    if args.action == 'list_cache':
        for f in db.list_existing_pages():
            print(f)
    elif args.action == 'remove_from_cache':
        db.remove_from_existing_pages(args.file)


if __name__ == '__main__':
    main()
