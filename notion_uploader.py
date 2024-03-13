#!/usr/bin/python3

import os
import sys
import logging
import progressbar
import argparse
import log
import json
import time
import re
import uuid
from datetime import datetime

from notion.client import NotionClient
from notion.block import PageBlock, AudioBlock, TextBlock, CalloutBlock, ToggleBlock
from notion.collection import NotionDate, CollectionRowBlock

MAX_TEXT_SIZE = 2000
JSON_EXT = ".json"


class NotionUploader(object):
    def __init__(self, token, collection_view_url, force_update=False, dry_run=False):
        self.__dry_run = dry_run
        self.__force_update = force_update
        self.__notion = NotionClient(token_v2=token, enable_caching=False)

        cv = self.__notion.get_collection_view(collection_view_url)
        self.__collection = cv.collection

        self.init_existing_pages()

    def init_existing_pages(self):
        self.__existing_pages = {}
        duplicate = False
        for r in self.__collection.get_rows(limit=10000000):
            if not self.add_existing_page(r.source, r.processtime, r.id, update=False):
                duplicate = True
        if duplicate:
            raise Exception("Duplicate items in collection")
        logging.info(f"Found existing {len(self.__existing_pages)} items")

    def add_existing_page(self, sourse, processtime, bid, update=True):
        if not update:
            if sourse in self.__existing_pages:
                logging.warn(f"Duplicate item: {sourse}: {bid}")
                return False

        self.__existing_pages[sourse] = (processtime, bid)
        return True

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

    def str_to_notion_date(self, s):
        return NotionDate(datetime.strptime(s[:10], "%Y-%m-%d").date())

    def delete_page(self, bid):
        logging.debug(f"remove block {bid}")
        block = self.__notion.get_block(bid)
        if type(block) is CollectionRowBlock:
            block.remove()
        else:
            block.remove(permanently=True)

    def check_existing(self, source, processtime):
        page = self.__existing_pages.get(source, None)
        logging.debug(f"check_existing: {source}: {page}")
        if page is None:
            return False

        if page[0] != processtime:
            logging.info(f"processtime changed: {page[0]} != {processtime} for {source}")
            self.delete_page(page[1])
            return False

        if self.__force_update:
            logging.info(f"force update for {source}")
            self.delete_page(page[1])
            return False

        return True

    def create_page(self, data, fname):
        if self.__dry_run:
            rid = uuid.uuid1()
            return rid

        res = self.__collection.add_row(
            title=data["caption"],
            date=self.str_to_notion_date(data["recordtime"]),
            source=data["source"],
            processtime=data["processtime"],
            icon="🎙️",
        )

        res.children.add_new(CalloutBlock, title=data["recordtime"], icon="📅", color="gray_background")

        audio = res.children.add_new(AudioBlock)
        info = audio.upload_file(fname)
        logging.debug(f"Audio uploaded: {info}")

        for block in self.split_large_text(data["text"]):
            res.children.add_new(TextBlock, title=block)

        res.set("format.block_locked", True)

        return res.id

    def load_json(self, file):
        with open(file, "r") as f:
            return json.load(f)

    def get_source_file(self, in_file, src_file):
        return os.path.join(os.path.dirname(in_file), src_file)

    def process(self, file):
        logging.info(f"Process file: {file}")

        data = self.load_json(file)

        if self.check_existing(data["source"], data["processtime"]):
            logging.debug(f"skip existing")
            return

        fname = self.get_source_file(file, data["source"])
        res = self.create_page(data, fname)

        self.add_existing_page(data["source"], data["processtime"], res)
        logging.info(f"Saved: {res}")


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
    parser.add_argument('-f', '--force', help='Force update', action='store_true')
    parser.add_argument('-d', '--dryrun', help='Dry run', action='store_true')
    return parser.parse_args()


def main():
    args = args_parse()

    log.initLogger(args.logfile, level=logging.DEBUG)

    token = os.getenv("NOTION_TOKEN")
    collection_view_url = os.getenv("NOTION_COLLECTION_VIEW")
    nup = NotionUploader(token, collection_view_url, force_update=args.force, dry_run=args.dryrun)

    fileslist = []
    if os.path.isfile(args.inpath):
        fileslist = (args.inpath,)
    elif os.path.isdir(args.inpath):
        fileslist = __scan_files(args.inpath)

    if len(fileslist) == 0:
        return

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
            nup.process(fname)
        except Exception:
            logging.exception("Notion uploader failed")
        pbar.increment()

    pbar.finish()
    logging.info(f"Done.")


if __name__ == '__main__':
    try:
        main()
    except Exception:
        logging.exception("Main failed")
