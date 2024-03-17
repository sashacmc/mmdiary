#!/usr/bin/python3

import os
import argparse
import json
import cachedb

from notion.client import NotionClient

JSON_EXT = ".json"
CACHE_DB_FILE = "~/.notion_upload.sqlite3"


class Verifier(object):
    def __init__(self, dryrun):
        self.__dryrun = dryrun
        self.__cache = cachedb.CacheDB(CACHE_DB_FILE)
        self.__notion = NotionClient(token_v2=os.getenv("NOTION_TOKEN"))

        if len(self.__cache.list_existing_pages()) == 0:
            print("Empty cache, exit")

    def load_json(self, file):
        with open(file, "r") as f:
            return json.load(f)

    def check_json(self, data):
        if "source" not in data:
            return

        for f in ("caption", "recordtime", "processtime", "source"):
            if len(data.get(f, "").strip()) == 0:
                raise Exception(f"empty {f}")

        if data["caption"].startswith("С вами был Игорь Негода"):
            raise Exception(f"caption: negoda")

        if data["caption"] == "Редактор субтитров А.":
            raise Exception(f"caption: redactor")

    def get_source_file(self, in_file, src_file):
        return os.path.join(os.path.dirname(in_file), src_file)

    def process(self, file):
        data = self.load_json(file)
        try:
            self.check_json(data)
        except Exception as ex:
            source = self.get_source_file(file, data["source"])
            uploaded = self.__cache.check_existing_pages(data["source"])

            print(file, str(ex))
            print(source)
            print(uploaded)

            if self.__dryrun:
                print()
                return

            if uploaded is not None:
                self.__cache.remove_from_existing_pages(data["source"])
                block = self.__notion.get_block(uploaded[1])
                block.remove()
                print("removed from notion")

            os.unlink(source)
            os.unlink(file)
            print("removed from fs")

            print()

    def process_list(self, fileslist):
        for fname in fileslist:
            self.process(fname)


def __scan_files(inpath):
    res = []
    for root, dirs, files in os.walk(inpath):
        for fname in files:
            if os.path.splitext(fname)[1] == JSON_EXT:
                res.append(os.path.join(root, fname))

    res.sort()
    return res


def args_parse():
    parser = argparse.ArgumentParser()
    parser.add_argument('inpath', help='Input path')
    parser.add_argument('-d', '--dryrun', help='Dry run', action='store_true')
    return parser.parse_args()


def main():
    args = args_parse()

    fileslist = []
    if os.path.isfile(args.inpath):
        fileslist = (args.inpath,)
    elif os.path.isdir(args.inpath):
        fileslist = __scan_files(args.inpath)

    vf = Verifier(args.dryrun)
    vf.process_list(fileslist)


if __name__ == '__main__':
    main()
