#!/usr/bin/python3

import os
import argparse
import json

from notion.client import NotionClient

import cachedb

JSON_EXT = ".json"
CACHE_DB_FILE = "~/.notion_upload.sqlite3"


class Verifier:
    def __init__(self, dryrun, force, sync):
        self.__dryrun = dryrun
        self.__force = force
        self.__sync_local = sync in ('all', 'local')
        self.__sync_notion = sync in ('all', 'notion')
        self.__cache = cachedb.CacheDB(CACHE_DB_FILE)
        self.__notion = NotionClient(token_v2=os.getenv("NOTION_TOKEN"))

        self.__local_sources = {}

        if len(self.__cache.list_existing_pages()) == 0:
            print("Empty cache, exit")

    def load_json(self, file):
        with open(file, "r", encoding="utf-8") as f:
            return json.load(f)

    def save_json(self, file, cont):
        with open(file, "w", encoding="utf-8") as f:
            json.dump(cont, f, ensure_ascii=False, indent=2)

    def check_caption(self, caption, text):
        if caption.startswith("С вами был Игорь Негода"):
            raise UserWarning("caption: negoda")
        if caption == "Редактор субтитров А.":
            raise UserWarning("caption: redactor")
        if caption == "Благодарю за внимание!" and caption == text:
            raise UserWarning("caption: vnimanie")
        if caption == "Фондю любит тебя!" and caption == text:
            raise UserWarning("caption: fondu")
        if caption == "Ставьте лайк и подписывайтесь!" and caption == text:
            raise UserWarning("caption: like")
        if caption == "Спасибо за просмотр!" and caption == text:
            raise UserWarning("caption: view")

    def check_json(self, data):
        if "source" not in data:
            return

        for f in ("caption", "recordtime", "processtime", "source"):
            if len(data.get(f, "").strip()) == 0:
                raise UserWarning(f"empty {f}")

        self.check_caption(data["caption"], data["text"])

        local_source = self.__local_sources.get(data["source"], None)
        if local_source is not None:
            raise UserWarning(f"duplicate source: {local_source}")
        self.__local_sources[data["source"]] = data

    def get_source_file(self, in_file, src_file):
        return os.path.join(os.path.dirname(in_file), src_file)

    def ask_for_delete(self):
        return self.ask_for("Delete files")

    def ask_for_cleanup(self):
        return self.ask_for("Cleanup file")

    def ask_for(self, action):
        if self.__dryrun:
            return False

        if self.__force:
            return True
        r = ""
        while r not in ("y", "n"):
            r = input(f"{action} [Y/n]? ").lower()
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

    def cleanup_json(self, data, file):
        data["caption"] = ""
        data["text"] = ""
        self.save_json(file, data)
        print("cleaned")

    def process(self, file):
        data = self.load_json(file)
        tp = data["type"]
        if tp == "audio":
            self.process_audio(file, data)
        elif tp == "video":
            self.process_video(file, data)
        else:
            print(f"Unsupported type: '{tp}' in file: {file}")

    def process_audio(self, file, data):
        uploaded = self.__cache.check_existing_pages(data.get("source", ""))
        source = self.get_source_file(file, data.get("source", ""))
        try:
            self.check_json(data)
        except UserWarning as ex:
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

    def process_video(self, file, data):
        source = self.get_source_file(file, data.get("source", ""))
        try:
            self.check_caption(data["caption"], data["text"])
        except UserWarning as ex:
            print(str(ex))
            print(file)
            print(source)
            print(data["text"])
            if self.ask_for_cleanup():
                self.cleanup_json(data, file)
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
    for root, _, files in os.walk(inpath):
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
