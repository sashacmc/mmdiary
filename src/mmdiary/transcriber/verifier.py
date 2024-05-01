#!/usr/bin/python3

import argparse
import json
import logging
import os
from datetime import datetime

from notion.client import NotionClient

from mmdiary.utils import log
from mmdiary.notion import cachedb
from mmdiary.utils.medialib import JSON_EXT, TIME_OUT_FORMAT

DESCRIPTION = """
Verify transcribed file(s).
Check recognized text/caption for neural network hallucination markers.

If sync option specified the script will addionally check sync with notion:
    local - check local files and remove missed files from notion 
    notion - check notion cache and remove missed local files 
    all - include `local` and `notion`

Sync check require following environment variables:
    NOTION_TOKEN - Notion web auth token
    NOTION_CACHE_DB_FILE - Cachedb file
"""

HALLUCINATION_TEXTS = [
    "Игорь Негода",
    "Валерий Курас",
    "Редактор субтитров",
    "Реактор субтитров",
    "Субтитры субтитров",
    "Спасибо за субтитры",
    "Субтитры подготовлены",
    "Субтитры делал",
    "Субтитры сделаны",
    "Благодарю за внимание",
    "Спасибо за внимание",
    "Фондю любит тебя",
    "одпишись на канал",
    "одпишитесь на канал",
    "одпишитесь на наш канал",
    "одписывайтесь на канал",
    "одписывайтесь на наш канал",
    "одписывайтесь на мой канал",
    "одписывайтесь на этот канал",
    "обро пожаловать в наш канал",
    "обро пожаловать на наш канал",
    "обро пожаловать на мой канал",
    "обро пожаловать на канал",
    "тавьте лайк",
    "тавь лайк",
    "Найдите лайки",
    "Спасибо за просмотр",
    "Большое спасибо за просмотр",
    "Благодарю за просмотр",
    "И не забудьте поставить лайк",
    "ФактФронт",
    "ПОДПИСЫВАЕТСЯ",
    "ПРОДОЛЖЕНИЕ",
    "Продолжение в следующей части",
]

RES_OK = 0
RES_TO_UPDATE = 1
RES_TO_DELETE = 2


def has_hall_text(s):
    for hall_text in HALLUCINATION_TEXTS:
        if hall_text in s:
            logging.debug("Has hall_text: %s", s)
            return True
    return False


def clean_wrong_symbols(s):
    res = ''
    for ch in s:
        if (
            ('а' <= ch <= 'я')
            or ('А' <= ch <= 'Я')
            or ch == 'ё'
            or ch == 'Ё'
            or ch in "1234567890+–-—,.;:?!%$«» \n"
        ):
            res += ch

    res = res.strip()

    punct_only = True
    for ch in res:
        if ch not in "+–-—,.;:?!%$«» ":
            punct_only = False
    if punct_only:
        res = ""

    if res != s:
        logging.debug("Has incorrect symbols: '%s'->'%s'", s, res)
    return res


def check_text(text):
    if text == "":
        return text

    src = text.split("\n")
    res = []
    for t in src:
        if not has_hall_text(t):
            s = clean_wrong_symbols(t)
            if s == "":
                logging.debug("Has empty string (was '%s')", t)
            else:
                res.append(s)
    return "\n".join(res)


class Verifier:
    def __init__(self, dryrun, force, sync):
        self.__dryrun = dryrun
        self.__force = force
        self.__sync_local = sync in ('all', 'local')
        self.__sync_notion = sync in ('all', 'notion')
        self.__cache = cachedb.CacheDB(os.getenv("NOTION_CACHE_DB_FILE"))
        self.__notion = NotionClient(token_v2=os.getenv("NOTION_TOKEN"))

        self.__local_sources = {}

        if len(self.__cache.list_existing_pages()) == 0:
            logging.warning("Empty cache")

    def __load_json(self, file):
        with open(file, "r", encoding="utf-8") as f:
            return json.load(f)

    def __save_json(self, file, cont):
        cont["processtime"] = datetime.now().strftime(TIME_OUT_FORMAT)
        with open(file, "w", encoding="utf-8") as f:
            json.dump(cont, f, ensure_ascii=False, indent=2)

    def __check_update_data(self, data):
        res = False
        new_caption = check_text(data["caption"])
        if new_caption != data["caption"]:
            res = True
            data["caption"] = new_caption

        new_text = check_text(data["text"])
        if new_text != data["text"]:
            res = True
            data["text"] = new_text

        return res

    def __check_audio_json(self, data):
        if "source" not in data:
            return RES_OK

        for f in ("recordtime", "processtime", "source"):
            if len(data.get(f, "").strip()) == 0:
                return RES_TO_DELETE

        if self.__check_update_data(data):
            return RES_TO_UPDATE

        local_source = self.__local_sources.get(data["source"], None)
        if local_source is not None:
            logging.warning("duplicate source: %s", local_source)
            return RES_TO_DELETE
        self.__local_sources[data["source"]] = data
        return RES_OK

    def __check_video_json(self, data):
        if self.__check_update_data(data):
            return RES_TO_UPDATE
        return RES_OK

    def __get_source_file(self, in_file, src_file):
        return os.path.join(os.path.dirname(in_file), src_file)

    def __ask_for_delete(self):
        return self.__ask_for("Delete files")

    def __ask_for_cleanup(self):
        return self.__ask_for("Cleanup file")

    def __ask_for(self, action):
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

    def __delete_from_notion(self, source, bid):
        self.__cache.remove_from_existing_pages(source)
        block = self.__notion.get_block(bid)
        block.remove()
        logging.info("removed from notion")

    def __delete_from_fs(self, source, file):
        if os.path.isfile(source):
            os.unlink(source)
        else:
            logging.warning("File %s don't exists", source)
        os.unlink(file)
        logging.info("removed from fs")

    def process(self, file):
        data = self.__load_json(file)
        tp = data["type"]
        if tp == "audio":
            return self.__process_audio(file, data)
        if tp == "video":
            return self.__process_video(file, data)
        logging.warning("Unsupported type: '%s' in file: %s", tp, file)
        return RES_OK

    def __process_audio(self, file, data):
        res = True
        uploaded = self.__cache.check_existing_pages(data.get("source", ""))
        source = self.__get_source_file(file, data.get("source", ""))
        check_res = self.__check_audio_json(data)
        if check_res != RES_OK:
            res = False
            print(file)
            print(source)
            print("notion:", uploaded)
            if check_res == RES_TO_DELETE and self.__ask_for_delete():
                if uploaded is not None:
                    self.__delete_from_notion(data["source"], uploaded[1])
                self.__delete_from_fs(source, file)
            elif check_res == RES_TO_UPDATE and self.__ask_for_cleanup():
                self.__save_json(file, data)
                print("cleaned")

            print()

        if not self.__sync_notion:
            return res

        if uploaded is None:
            print("Deleted from notion:")
            print(file)
            print(source)
            if self.__ask_for_delete():
                self.__delete_from_fs(source, file)
            print()
        return res

    def __process_video(self, file, data):
        res = True
        source = self.__get_source_file(file, data.get("source", ""))
        check_res = self.__check_video_json(data)
        if check_res != RES_OK:
            res = False
            print(file)
            print(source)
            if self.__ask_for_cleanup():
                self.__save_json(file, data)
                print("cleaned")
            print()
        return res

    def process_list(self, fileslist):
        self.__local_sources = {}
        errors = 0
        for fname in fileslist:
            if not self.process(fname):
                errors += 1

        print(f"Processed: {len(fileslist)}, errors: {errors}")

        if not self.__sync_local:
            return

        for source, bid in self.__cache.list_existing_pages():
            if source not in self.__local_sources:
                print("Deleted local:")
                print("notion:", source, bid)
                if self.__ask_for_delete():
                    self.__delete_from_notion(source, bid)


def scan_files(inpath):
    res = []
    for root, _, files in os.walk(inpath):
        for fname in files:
            if os.path.splitext(fname)[1] == JSON_EXT:
                res.append(os.path.join(root, fname))

    res.sort()
    return res


def __args_parse():
    parser = argparse.ArgumentParser(
        description=DESCRIPTION, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument('inpath', nargs="+", help='Input path(s)')
    parser.add_argument(
        '-d', '--dryrun', help='Dry run (just check without any modifications)', action='store_true'
    )
    parser.add_argument('-l', '--logfile', help='Log file', default=None)
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
    args = __args_parse()
    log.init_logger(args.logfile, logging.DEBUG)
    logging.getLogger("urllib3").setLevel(logging.ERROR)

    vf = Verifier(args.dryrun, args.force, args.sync)
    fileslist = []
    for path in args.inpath:
        print(f"Start: {path}")
        if os.path.isfile(path):
            fileslist = (path,)
        elif os.path.isdir(path):
            fileslist = scan_files(path)
        vf.process_list(fileslist)


if __name__ == '__main__':
    main()
