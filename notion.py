#!/usr/bin/python3

from notion_client import Client
import os
import sys
import logging
import log
import json
import time
import re

DIR = "/mnt/multimedia/NEW/Audio/"
URL = "https://mediahome.bushnev.pro/audio-notes/"
MAX_TEXT_SIZE = 2000

YEAR_REGEX = r'^\d{4}$'
MONTH_REGEX = r'^\d{4}-(0[1-9]|1[0-2])$'
DAY_REGEX = r'^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[1-2][0-9]|3[0-1])$'


class NotionStructure(object):
    def __init__(self, token, parent_page_id):
        self.__notion = Client(auth=token)
        self.__parent_page_id = parent_page_id
        self.__pages = self.load()

    def get_children(self, page_id):
        all_children = self.__notion.blocks.children.list(page_id)["results"]
        pages = filter(lambda ch: ch["type"] == "child_page" and not ch["archived"], all_children)
        return [(p["child_page"]["title"], p["id"]) for p in pages]

    def get_date_pages(self, page_id):
        res = {}
        pages = self.get_children(page_id)
        print(page_id, pages)
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
        return self.get_date_pages(self.__parent_page_id)

    def create_page(self, page_id, before_id, title):
        print("CREATE: ", page_id, before_id, title)

        properties = {"title": [{"text": {"content": title}}]}
        res = self.__notion.pages.create(
            parent={"page_id": page_id}, after=before_id, properties=properties, icon={"type": "emoji", "emoji": "🗓️"}
        )
        new_page_id = res["id"]

        page = {"object": "block", "type": "link_to_page", "link_to_page": {"page_id": new_page_id}}

        res = self.__notion.blocks.children.append(
            block_id=page_id,
            after=before_id,
            children=[
                page,
            ],
        )

        return res

    def find_before_page_id(self, date_str):
        prefix = date_str[:-2]
        num = int(date_str[-2:]) - 1
        print("BEFORE INIT: ", prefix, num)
        while num != 0:
            before = f"{prefix}{num:02}"
            before_id = self.__pages.get(before, None)
            print("BEFORE: ", before, before_id)
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
            return self.create_page(self.__parent_page_id, before_id, date_str)


class NotionUploader(object):
    def __init__(self, token, parent_page_id):
        self.__notion = Client(auth=token)
        self.__parent_page_id = parent_page_id

    def create_page(self, properties, children):
        self.__notion.pages.create(
            parent={"page_id": self.__parent_page_id}, properties=properties, children=children, icon={"type": "emoji", "emoji": "🎙️"}
        )

    def create_date_page(self, date_path):
        pass

    def load_json(self, file):
        with open(file, "r") as f:
            return json.load(f)

    def get_out_filename(self, in_file):
        return os.path.splitext(in_file)[0] + ".mp3"

    def gen_properties(self, data):
        return {"title": [{"text": {"content": data["caption"]}}]}

    def gen_children(self, data, url):
        res = []
        # Date
        res.append(
            {
                "object": "block",
                "type": "callout",
                "callout": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {
                                "content": data["recordtime"],
                            },
                        }
                    ],
                    "icon": {"type": "emoji", "emoji": "📅"},
                    "color": "gray_background",
                },
            },
        )

        # Record
        res.append({"object": "block", "type": "audio", "audio": {"external": {"url": url}}})

        # Text
        block_len = 0
        block = []
        blocks = []
        for s in data["text"].split("\n"):
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

        for block in blocks:
            res.append(
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {
                                    "content": block,
                                },
                            }
                        ]
                    },
                }
            )
        return res

    def process(self, file):
        logging.info(f"Process file: {file}")

        if DIR not in file:
            return

        url = self.get_out_filename(file.replace(DIR, URL))

        data = self.load_json(file)
        res = self.create_page(self.gen_properties(data), self.gen_children(data, url))

        logging.info(f"Saved: {res}")


if __name__ == "__main__!!!":
    log.initLogger()
    in_file = sys.argv[1]

    token = os.getenv("NOTION_API_KEY")
    page_id = "c1d9a8f5ed024019969ff36c841063df"
    nup = NotionUploader(token, page_id)

    if os.path.isfile(in_file):
        nup.process(in_file)
    elif os.path.isdir(in_file):
        for dirpath, dirs, files in os.walk(in_file):
            for filename in files:
                fname = os.path.join(dirpath, filename)
                nup.process(fname)

if __name__ == "__main__":
    log.initLogger()

    date = sys.argv[1]
    token = os.getenv("NOTION_API_KEY")
    page_id = "c1d9a8f5ed024019969ff36c841063df"
    nus = NotionStructure(token, page_id)
    print(nus.get_day_page_id(date))
