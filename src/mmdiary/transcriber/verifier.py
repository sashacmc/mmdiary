#!/usr/bin/python3
# pylint: disable=too-many-instance-attributes

import argparse
import logging
import os
import re
from datetime import datetime

from notion.client import NotionClient

from mmdiary.utils import medialib, log
from mmdiary.notion import cache

DESCRIPTION = """
Verify transcribed file(s).
Check recognized text/caption for neural network hallucination markers.

If sync option specified the script will addionally check sync with notion:
    local - check local files and remove missed files from notion 
    notion - check notion cache and remove missed local files 
    all - include `local` and `notion`

Optional environment variables:
    MMDIARY_TRANSCRIBE_LANGUAGE - Transcribe language (default: "ru")

Sync check require following environment variables:
    MMDIARY_NOTION_TOKEN - Notion web auth token
    MMDIARY_NOTION_CACHE_FILE - Cache file
"""

HALLUCINATION_TEXTS = {
    "ru": [
        re.compile(r"Игорь Негода"),
        re.compile(r"Валерий Курас"),
        re.compile(r"Валерий Савинский"),
        re.compile(r"Фондю любит тебя"),
        re.compile(r"ФактФронт"),
        re.compile(r"не пропустить новые видео"),
        re.compile(r"Корректор (А|В|Е)\."),
        re.compile(r"[Пп]родолжение в следующей части"),
        re.compile(r"[Рр]е(д)?актор субтитров"),
        re.compile(r"Субтитры субтитров"),
        re.compile(r"Корректор субтитров"),
        re.compile(r"Спасибо за субтитры"),
        re.compile(r"[Сс]убтитры (подготов|делал|сделаны)"),
        re.compile(r"[Бб]лагодарю( (тебя|вас|всех))? за (внимание|просмотр)"),
        re.compile(r"[Сс]пасибо( (тебе|вам|всем))? за (внимание|просмотр)"),
        re.compile(r"[Пп](одписаться|одписывайся|одписывайтесь) на( (мой|наш|этот))? канал"),
        re.compile(r"[Пп](одпишись|одпишитесь|одпишите) на( (мой|наш|этот))? канал"),
        re.compile(r"[Дд]обро пожаловать (на|в)( (мой|наш|этот))? канал"),
        re.compile(r"[Сс]тавь(те)? лайк(и)?"),
        re.compile(r"[Жж]ми(те)? лайк(и)?"),
        re.compile(r"[Пп]остав(ь|те|ить) лайк(и)?"),
        re.compile(r"[Дд](л)?ай(те)? лайк(и)?"),
        re.compile(r"Найдите лайки"),
        re.compile(r"Я не могу это сделать"),
        # exclude all capitalised except some key words
        re.compile(r"^(?!.*(?:МУЗЫКА|СМЕХ|КАШЕЛЬ|ПЕСНЯ|ПОЮТ|ПОЕТ|КРИК))[А-Я\s]{4,}$"),
    ]
}

RES_OK = 0
RES_TO_UPDATE = 1
RES_TO_DELETE = 2


def has_hall_text(s, language):
    if language not in HALLUCINATION_TEXTS:
        return False
    for hall_text in HALLUCINATION_TEXTS[language]:
        if hall_text.search(s) is not None:
            logging.debug("Has hall_text: %s", s)
            return True
    return False


def clean_wrong_symbols(s, language):
    if language != "ru":
        return s
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


def cut_long_words(s):
    lis = []
    words = s.split(" ")
    for w in words:
        lis.append(w[:30])

    res = " ".join(lis)
    if res != s:
        logging.debug("Has long words: '%s'->'%s'", s, res)
    return res


def remove_duplicate_lines(src):
    res = src[0:2]
    for i in range(2, len(src)):
        if src[i] != src[i - 1] or src[i] != src[i - 2]:
            res.append(src[i])
    if res != src:
        logging.debug("Has string duplicates: '%s'->'%s'", src, res)
    return res


def check_text(text, language):
    if text == "":
        return text

    src = text.split("\n")
    res = []
    for t in src:
        if not has_hall_text(t, language):
            s = clean_wrong_symbols(t, language)
            if s == "":
                logging.debug("Has empty string (was '%s')", t)
            else:
                res.append(cut_long_words(s))
    res = remove_duplicate_lines(res)
    return "\n".join(res)


class Verifier:
    def __init__(self, dryrun, force, sync):
        self.__dryrun = dryrun
        self.__force = force
        self.__sync_local = sync in ('all', 'local')
        self.__sync_notion = sync in ('all', 'notion')
        self.__cache = cache.Cache()
        self.__notion = NotionClient(token_v2=os.getenv("MMDIARY_NOTION_TOKEN"))
        self.__language = os.getenv("MMDIARY_TRANSCRIBE_LANGUAGE", "ru")

        self.__local_sources = {}

        if len(self.__cache.list_existing_pages()) == 0:
            logging.warning("Empty cache")

    def __save(self, file, cont):
        cont["processtime"] = datetime.now().strftime(medialib.TIME_OUT_FORMAT)
        file.update_fields(cont)

    def __check_update_data(self, data):
        res = False
        new_caption = check_text(data["caption"], self.__language)
        if new_caption != data["caption"]:
            res = True
            data["caption"] = new_caption

        new_text = check_text(data["text"], self.__language)
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

    def __delete_from_fs(self, file):
        if os.path.isfile(file.name()):
            os.unlink(file.name())
        else:
            logging.warning("File %s don't exists", file.name())
        os.unlink(file.json_name())
        logging.info("removed from fs")

    def process(self, file):
        tp = file.type()
        if tp == "audio":
            return self.__process_audio(file)
        if tp == "video":
            return self.__process_video(file)
        logging.warning("Unsupported type: '%s' in file: %s", tp, file)
        return RES_OK

    def __process_audio(self, file):
        data = file.json()
        res = True
        uploaded = self.__cache.check_existing_pages(data.get("source", ""))
        check_res = self.__check_audio_json(data)
        if check_res != RES_OK:
            res = False
            print(file.json_name())
            print(file.name())
            print("notion:", uploaded)
            if check_res == RES_TO_DELETE and self.__ask_for_delete():
                if uploaded is not None:
                    self.__delete_from_notion(data["source"], uploaded[1])
                self.__delete_from_fs(file)
            elif check_res == RES_TO_UPDATE and self.__ask_for_cleanup():
                self.__save(file, data)
                print("cleaned")

            print()

        if not self.__sync_notion:
            return res

        if uploaded is None:
            print("Deleted from notion:")
            print(file.json_name())
            print(file.name())
            if self.__ask_for_delete():
                self.__delete_from_fs(file)
            print()
        return res

    def __process_video(self, file):
        data = file.json()
        res = True
        check_res = self.__check_video_json(data)
        if check_res != RES_OK:
            res = False
            print(file.json_name())
            print(file.name())
            if self.__ask_for_cleanup():
                self.__save(file, data)
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
            fileslist = (medialib.MediaFile(None, path),)
        elif os.path.isdir(path):
            lib = medialib.MediaLib(path)
            fileslist = lib.get_processed(should_have_file=False)
        vf.process_list(fileslist)


if __name__ == '__main__':
    main()
