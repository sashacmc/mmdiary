#!/usr/bin/python3

import os
import sys
import logging
import log
import json
import time
import re

from notion.client import NotionClient
from notion.block import PageBlock, AudioBlock, TextBlock, CalloutBlock

DIR = "/mnt/multimedia/NEW/Audio/"
URL = "https://mediahome.bushnev.pro/audio-notes/"
MAX_TEXT_SIZE = 2000

YEAR_REGEX = r'^\d{4}$'
MONTH_REGEX = r'^\d{4}-(0[1-9]|1[0-2])$'
DAY_REGEX = r'^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[1-2][0-9]|3[0-1])$'


class NotionStructure(object):
    def __init__(self, notion, root_page_id):
        self.__notion = notion
        self.__root_page_id = root_page_id
        self.__pages = self.load()

    def get_children(self, page_id):
        all_children = self.__notion.get_block(page_id).children
        pages = filter(lambda ch: ch.type == "page", all_children)
        return [(p.title, p.id) for p in pages]

    def get_date_pages(self, page_id):
        res = {}
        pages = self.get_children(page_id)
        for title, pid in pages:
            if re.match(YEAR_REGEX, title):
                res[title] = pid
                res.update(self.get_date_pages(pid))
            elif re.match(MONTH_REGEX, title):
                res[title] = pid
                res.update(self.get_date_pages(pid))
            elif re.match(DAY_REGEX, title):
                res[title] = pid
        return res

    def load(self):
        return self.get_date_pages(self.__root_page_id)

    def children_pages_count(self, block):
        res = 0
        for ch in block.children:
            if ch.type == "page":
                res += 1
        return res

    def create_page(self, page_id, before_id, title):
        parent = self.__notion.get_block(page_id)
        res = parent.children.add_new(PageBlock, title=title, icon="🗓️")

        if self.children_pages_count(parent) > 1:
            if before_id is None:
                res.move_to(parent, "first-child")
            else:
                sibling = self.__notion.get_block(before_id)
                res.move_to(sibling, "after")

        res.set("format.block_locked", True)

        self.__pages[title] = res.id

        return res.id

    def find_before_page_id(self, date_str):
        prefix = date_str[:-2]
        num = int(date_str[-2:]) - 1
        while num != 0:
            before = f"{prefix}{num:02}"
            before_id = self.__pages.get(before, None)
            if before_id != None:
                return before_id
            num -= 1
        return None

    def get_day_page_id(self, date_str):
        if not re.match(DAY_REGEX, date_str):
            raise Exception(f"Incorrect date: {date_str}")
        if date_str in self.__pages:
            return self.__pages[date_str]
        else:
            page_id = self.get_month_page_id(date_str[:-3])
            before_id = self.find_before_page_id(date_str)
            return self.create_page(page_id, before_id, date_str)

    def get_month_page_id(self, date_str):
        if not re.match(MONTH_REGEX, date_str):
            raise Exception(f"Incorrect month: {date_str}")
        if date_str in self.__pages:
            return self.__pages[date_str]
        else:
            page_id = self.get_year_page_id(date_str[:-3])
            before_id = self.find_before_page_id(date_str)
            return self.create_page(page_id, before_id, date_str)

    def get_year_page_id(self, date_str):
        if not re.match(YEAR_REGEX, date_str):
            raise Exception(f"Incorrect year: {date_str}")
        if date_str in self.__pages:
            return self.__pages[date_str]
        else:
            before_id = self.find_before_page_id(date_str)
            return self.create_page(self.__root_page_id, before_id, date_str)


class NotionUploader(object):
    def __init__(self, token, root_page_id):
        self.__notion = NotionClient(token_v2=token)
        self.__structure = NotionStructure(self.__notion, root_page_id)
        self.__root_page_id = root_page_id

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

    def create_page(self, data, url):
        parent_id = self.__structure.get_day_page_id(data["recordtime"][:10])
        parent = self.__notion.get_block(parent_id)

        res = parent.children.add_new(PageBlock, title=data["caption"], icon="🎙️")

        res.children.add_new(CalloutBlock, title=data["recordtime"], icon="📅", color="gray_background")

        res.children.add_new(AudioBlock, source=url)

        for block in self.split_large_text(data["text"]):
            res.children.add_new(TextBlock, title=block)

        res.set("format.block_locked", True)

        return res.id

    def load_json(self, file):
        with open(file, "r") as f:
            return json.load(f)

    def get_url(self, in_file, src_file):
        orig_file = os.path.join(os.path.dirname(in_file), src_file)
        return orig_file.replace(DIR, URL)

    def process(self, file):
        logging.info(f"Process file: {file}")

        if DIR not in file:
            logging.info(f"File outside of main tree, skipped")
            return

        data = self.load_json(file)

        url = self.get_url(file, data["source"])
        res = self.create_page(data, url)

        logging.info(f"Saved: {res}")


if __name__ == "__main__":
    log.initLogger()
    in_file = sys.argv[1]

    token = os.getenv("NOTION_TOKEN")
    page_id = "c1d9a8f5ed024019969ff36c841063df"
    nup = NotionUploader(token, page_id)

    fileslist = []
    if os.path.isfile(in_file):
        nup.process(in_file)
    elif os.path.isdir(in_file):
        for dirpath, dirs, files in os.walk(in_file):
            for filename in files:
                if os.path.splitext(filename)[1] == ".json":
                    fname = os.path.join(dirpath, filename)
                    fileslist.append(fname)

    logging.info(f"{len(fileslist)} files found")

    for fname in fileslist:
        nup.process(fname)

    logging.info(f"Done.")
