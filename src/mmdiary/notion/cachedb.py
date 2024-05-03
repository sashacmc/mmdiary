#!/usr/bin/python3

import argparse
import atexit
import os
import sqlite3
import threading

from notion_client import Client
from notion_client.helpers import iterate_paginated_api

SCHEMA = '''
CREATE TABLE IF NOT EXISTS existing_pages (
    "filename" TEXT,
    "processtime" TEXT,
    "bid" TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS existing_pages_filename ON existing_pages (filename);
'''


class CacheDB:
    def __init__(self, filename):
        self.__conn = sqlite3.connect(os.path.expanduser(filename), check_same_thread=False)

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
            res = c.execute('SELECT filename, bid FROM existing_pages')
            return res.fetchall()

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
            c.execute('DELETE FROM existing_pages WHERE filename=?', (filename,))

    def __get_prop(self, row, name, default=""):
        try:
            rt = row["properties"][name]["rich_text"]
            if len(rt) != 0:
                return rt[0]["plain_text"]
            return ""
        except IndexError:
            print(f"Property '{name}' not found in {row}")
            return default

    def sync_existing_pages(self, notion_api, database_ids):
        self.clean_existing_pages()

        res = []
        for database_id in set(database_ids):
            res += iterate_paginated_api(
                notion_api.databases.query,
                database_id=database_id,
            )

        duplicates = ""

        for r in res:
            source = self.__get_prop(r, "source")
            processtime = self.__get_prop(r, "processtime")
            rid = r["id"]
            if self.check_existing_pages(source) is not None:
                duplicates += f"\n{source}: {rid}"

            self.add_existing_page(source, processtime, rid)

        if duplicates != "":
            raise UserWarning(f"Duplicate items in collection: {duplicates}")


def args_parse():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-a',
        '--action',
        help='Action',
        required=True,
        choices=[
            'clean',
            'list',
            'remove',
            'sync',
        ],
    )
    parser.add_argument(
        '-d',
        '--database',
        help='Database file',
        default=os.getenv("NOTION_CACHE_DB_FILE"),
    )
    parser.add_argument('-f', '--file', help='File name')
    return parser.parse_args()


def main():
    args = args_parse()
    db = CacheDB(args.database)

    if args.action == 'clean':
        db.clean_existing_pages()
    if args.action == 'list':
        for f in db.list_existing_pages():
            print(f)
    elif args.action == 'remove':
        db.remove_from_existing_pages(args.file)
    elif args.action == 'sync':
        db.sync_existing_pages(
            Client(auth=os.getenv("NOTION_API_KEY")),
            (os.getenv("NOTION_AUDIO_DB_ID"), os.getenv("NOTION_VIDEO_DB_ID")),
        )


if __name__ == '__main__':
    main()
