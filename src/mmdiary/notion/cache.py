#!/usr/bin/python3

import argparse
import atexit
import os
import pickle

from notion_client import Client
from notion_client.helpers import iterate_paginated_api


class Cache:
    def __init__(self):
        self.__filename = os.path.expanduser(os.getenv("MMDIARY_NOTION_CACHE"))
        self.__data = {}
        self.__load()
        self.__changed = False
        atexit.register(self.__save)

    def __load(self):
        if not os.path.exists(self.__filename):
            self.__data = {}
            return
        with open(self.__filename, "rb") as f:
            self.__data = pickle.load(f)

    def __save(self):
        if not self.__changed:
            return
        with open(self.__filename, "wb") as f:
            pickle.dump(self.__data, f)

    def list_existing_pages(self):
        return [(filename, bid) for filename, (processtime, bid) in self.__data.items()]

    def clean_existing_pages(self):
        self.__data = {}
        self.__changed = True

    def add_existing_page(self, filename, processtime, bid):
        self.__data[filename] = (processtime, bid)
        self.__changed = True

    def check_existing_pages(self, filename):
        return self.__data.get(filename)

    def remove_from_existing_pages(self, filename):
        if filename in self.__data:
            del self.__data[filename]

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
    parser.add_argument('-f', '--file', help='File name')
    return parser.parse_args()


def main():
    args = args_parse()
    db = Cache()

    if args.action == 'clean':
        db.clean_existing_pages()
    if args.action == 'list':
        for f in db.list_existing_pages():
            print(f)
    elif args.action == 'remove':
        db.remove_from_existing_pages(args.file)
    elif args.action == 'sync':
        db.sync_existing_pages(
            Client(auth=os.getenv("MMDIARY_NOTION_API_KEY")),
            (os.getenv("MMDIARY_NOTION_AUDIO_DB_ID"), os.getenv("MMDIARY_NOTION_VIDEO_DB_ID")),
        )


if __name__ == '__main__':
    main()
