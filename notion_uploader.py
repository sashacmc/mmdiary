#!/usr/bin/python3

import os
import logging
import progressbar
import argparse
import log
import json
import cachedb

from notion_client import Client

from notion.client import NotionClient
from notion.block import (
    AudioBlock,
    TextBlock,
    CalloutBlock,
)
from notion.collection import CollectionRowBlock

MAX_TEXT_SIZE = 2000
JSON_EXT = ".json"


class NotionUploader(object):
    def __init__(
        self,
        token,
        api_key,
        database_id,
        cache_db_file,
        force_update=False,
        dry_run=False,
    ):
        self.__status = {
            "total": 0,
            "existing": 0,
            "processed": 0,
            "removed": 0,
            "created": 0,
            "failed": 0,
            "skipped": 0,
        }
        self.__cache = cachedb.CacheDB(cache_db_file)
        self.__dry_run = dry_run
        self.__force_update = force_update
        self.__notion = NotionClient(token_v2=token, enable_caching=False)

        self.__database_id = database_id
        self.__notion_api = Client(auth=api_key)

        self.init_existing_pages()

    def status(self):
        return self.__status

    def init_existing_pages(self):
        cnt = len(self.__cache.list_existing_pages())
        if cnt == 0 and not self.__dry_run:
            logging.info("Cache empty, init...")
            self.__cache.sync_existing_pages(
                self.__notion_api, self.__database_id
            )
            cnt = len(self.__cache.list_existing_pages())

        self.__status["existing_init"] = cnt
        self.__status["existing"] = cnt
        logging.info(f"Found existing {cnt} items")

    def add_existing_page(self, source, processtime, bid):
        if not self.__dry_run:
            self.__cache.add_existing_page(source, processtime, bid)
        self.__status["existing"] += 1

    def split_large_text(self, text):
        block_len = 0
        block = []
        blocks = []
        for s in text.split("\n"):
            s_len = len(s) + 1
            if block_len + s_len < MAX_TEXT_SIZE:
                block.append(s)
                block_len += s_len
            else:
                blocks.append("\n".join(block))
                block = []
                block_len = 0

        if len(block) != 0:
            blocks.append("\n".join(block))

        return blocks

    def delete_page(self, source, bid):
        logging.debug(f"remove block {bid}")
        if not self.__dry_run:
            block = self.__notion.get_block(bid)
            if type(block) is CollectionRowBlock:
                block.remove()
            else:
                block.remove(permanently=True)

            if source is not None:
                self.__cache.remove_from_existing_pages(source)

        self.__status["removed"] += 1

    def check_existing(self, source, processtime):
        page = self.__cache.check_existing_pages(source)
        logging.debug(f"check_existing: {source}: {page}")
        if page is None:
            return False

        # page processtime == "" mean that page was modied on notion side
        if processtime > page[0] and page[0] != "":
            logging.info(
                f"processtime changed: {processtime} > {page[0]} for {source}"
            )
            self.delete_page(source, page[1])
            return False

        if self.__force_update:
            logging.info(f"force update for {source}")
            self.delete_page(source, page[1])
            return False

        return True

    def add_row(self, title, date, source, processtime, icon):
        properties = {
            "title": {"title": [{"text": {"content": title}}]},
            "Date": {"type": "date", "date": {"start": date}},
            "source": {
                "type": "rich_text",
                "rich_text": [
                    {
                        "type": "text",
                        "text": {"content": source},
                    },
                ],
            },
            "processtime": {
                "type": "rich_text",
                "rich_text": [
                    {
                        "type": "text",
                        "text": {"content": processtime},
                    },
                ],
            },
        }

        res = self.__notion_api.pages.create(
            parent={"database_id": self.__database_id},
            icon={"type": "emoji", "emoji": icon},
            properties=properties,
        )

        return res["id"]

    def create_page(self, data, fname):
        if self.__dry_run:
            self.__status["created"] += 1
            return

        bid = self.add_row(
            title=data["caption"],
            date=data["recordtime"][:10],
            source=data["source"],
            processtime=data["processtime"],
            icon="🎙️",
        )
        try:
            res = self.__notion.get_block(bid)
            res.children.add_new(
                CalloutBlock,
                title=data["recordtime"],
                icon="📅",
                color="gray_background",
            )

            audio = res.children.add_new(AudioBlock)
            info = audio.upload_file(fname)
            logging.debug(f"Audio uploaded: {info}")

            for block in self.split_large_text(data["text"]):
                res.children.add_new(TextBlock, title=block)

            res.set("format.block_locked", True)

            self.add_existing_page(data["source"], data["processtime"], res.id)
        except Exception:
            logging.warning(f"Delete uncompleate page for: {fname}")
            self.delete_page(None, bid)
            raise

        self.__status["created"] += 1

    def load_json(self, file):
        with open(file, "r") as f:
            return json.load(f)

    def check_json(self, data):
        for f in ("caption", "recordtime", "processtime", "source"):
            if len(data[f].strip()) == 0:
                raise Exception(f"Incorrect file: empty {f}")

    def get_source_file(self, in_file, src_file):
        return os.path.join(os.path.dirname(in_file), src_file)

    def process(self, file):
        logging.info(f"Process file: {file}")
        self.__status["processed"] += 1

        data = self.load_json(file)
        self.check_json(data)

        if self.check_existing(data["source"], data["processtime"]):
            logging.debug("skip existing")
            self.__status["skipped"] += 1
            return

        fname = self.get_source_file(file, data["source"])
        res = self.create_page(data, fname)

        logging.info(f"Saved: {res}")

    def process_list(self, fileslist):
        self.__status["total"] = len(fileslist)
        pbar = progressbar.ProgressBar(
            maxval=len(fileslist),
            widgets=[
                "Uploading",
                ' ',
                progressbar.Percentage(),
                ' ',
                progressbar.Bar(),
                ' ',
                progressbar.ETA(),
            ],
        ).start()

        for fname in fileslist:
            try:
                self.process(fname)
            except Exception:
                self.__status["failed"] += 1
                logging.exception("Notion uploader failed")
            pbar.increment()

        pbar.finish()


def __on_walk_error(err):
    logging.error('Scan files error: %s' % err)


def __scan_files(inpath):
    res = []
    for root, dirs, files in os.walk(inpath, onerror=__on_walk_error):
        for fname in files:
            if os.path.splitext(fname)[1] == JSON_EXT:
                res.append(os.path.join(root, fname))

    res.sort()
    logging.info(f"Found {len(res)} files")
    return res


def args_parse():
    parser = argparse.ArgumentParser()
    parser.add_argument('inpath', help='Input path')
    parser.add_argument('-l', '--logfile', help='Log file', default=None)
    parser.add_argument(
        '-f', '--force', help='Force update', action='store_true'
    )
    parser.add_argument('-d', '--dryrun', help='Dry run', action='store_true')
    return parser.parse_args()


def main():
    args = args_parse()

    log.initLogger(args.logfile, level=logging.DEBUG)

    token = os.getenv("NOTION_TOKEN")
    api_key = os.getenv("NOTION_API_KEY")
    database_id = os.getenv("NOTION_DB_ID")
    cache_db_file = os.getenv("NOTION_CACHE_DB_FILE")

    fileslist = []
    if os.path.isfile(args.inpath):
        fileslist = (args.inpath,)
    elif os.path.isdir(args.inpath):
        fileslist = __scan_files(args.inpath)

    if len(fileslist) == 0:
        logging.info("Nothing to do, exit")
        return

    nup = NotionUploader(
        token=token,
        api_key=api_key,
        database_id=database_id,
        cache_db_file=cache_db_file,
        force_update=args.force,
        dry_run=args.dryrun,
    )
    nup.process_list(fileslist)

    logging.info(f"Done: {nup.status()}")


if __name__ == '__main__':
    try:
        main()
    except Exception:
        logging.exception("Main failed")
