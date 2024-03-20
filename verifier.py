#!/usr/bin/python3

import os
import argparse
import json
import cachedb

from notion.client import NotionClient

JSON_EXT = ".json"
CACHE_DB_FILE = "~/.notion_upload.sqlite3"


class Verifier(object):
    def __init__(self, dryrun, force, sync):
        self.__dryrun = dryrun
        self.__force = force
        self.__sync_local = True if sync in ('all', 'local') else False
        self.__sync_notion = True if sync in ('all', 'notion') else False
        self.__cache = cachedb.CacheDB(CACHE_DB_FILE)
        self.__notion = NotionClient(token_v2=os.getenv("NOTION_TOKEN"))

        self.__local_sources = {}

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
            raise Exception("caption: negoda")

        if data["caption"] == "Редактор субтитров А.":
            raise Exception("caption: redactor")

        local_source = self.__local_sources.get(data["source"], None)
        if local_source is not None:
            raise Exception(f"duplicate source: {local_source}")
        self.__local_sources[data["source"]] = data

    def get_source_file(self, in_file, src_file):
        return os.path.join(os.path.dirname(in_file), src_file)

    def ask_for_delete(self):
        if self.__dryrun:
            return False

        if self.__force:
            return True
        r = ""
        while r not in ("y", "n"):
            r = input("Remove files [Y/n]? ").lower()
            if r == "":
                r = "y"
        return r == "y"

    def delete_from_notion(self, source, bid):
        self.__cache.remove_from_existing_pages(source)
        block = self.__notion.get_block(bid)
        block.remove()
        print("removed from notion")

    def delete_from_fs(self, source, file):
        if os.path.isfile(source):
            os.unlink(source)
        else:
            print(f"File {source} don't exists")
        os.unlink(file)
        print("removed from fs")

    def process(self, file):
        data = self.load_json(file)
        uploaded = self.__cache.check_existing_pages(data.get("source", ""))
        source = self.get_source_file(file, data.get("source", ""))
        try:
            self.check_json(data)
        except Exception as ex:
            print(str(ex))
            print(file)
            print(source)
            print("notion:", uploaded)
            if self.ask_for_delete():
                if uploaded is not None:
                    self.delete_from_notion(data["source"], uploaded[1])
                self.delete_from_fs(source, file)
            print()

        if not self.__sync_notion:
            return

        if uploaded is None:
            print("Deleted from notion:")
            print(file)
            print(source)
            if self.ask_for_delete():
                self.delete_from_fs(source, file)
            print()

    def process_list(self, fileslist):
        self.__local_sources = {}
        for fname in fileslist:
            self.process(fname)

        if not self.__sync_local:
            return

        for source, bid in self.__cache.list_existing_pages():
            if source not in self.__local_sources:
                print("Deleted local:")
                print("notion:", source, bid)
                if self.ask_for_delete():
                    self.delete_from_notion(source, bid)


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
    parser.add_argument(
        '-s',
        '--sync',
        help='Sync (check for deleted)',
        choices=[
            'all',
            'notion',
            'local',
        ],
    )
    parser.add_argument(
        '-f',
        '--force',
        help='Force (remove without confirmation)',
        action='store_true',
    )
    return parser.parse_args()


def main():
    args = args_parse()

    fileslist = []
    if os.path.isfile(args.inpath):
        fileslist = (args.inpath,)
    elif os.path.isdir(args.inpath):
        fileslist = __scan_files(args.inpath)

    vf = Verifier(args.dryrun, args.force, args.sync)
    vf.process_list(fileslist)


if __name__ == '__main__':
    main()
