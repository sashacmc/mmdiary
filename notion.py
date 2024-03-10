#!/usr/bin/python3

from notion_client import Client
import os
import sys
import logging
import log
import json
import time

DIR = "/mnt/multimedia/NEW/Audio/"
URL = "https://mediahome.bushnev.pro/audio-notes/"
MAX_TEXT_SIZE = 2000


class NotionUploader(object):
    def __init__(self, token, parent_page_id):
        self.__notion = Client(auth=token)
        self.__parent_page_id = parent_page_id

    def create_page(self, properties, children):
        self.__notion.pages.create(
            parent={"page_id": self.__parent_page_id}, properties=properties, children=children, icon={"type": "emoji", "emoji": "🎙️"}
        )

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


if __name__ == "__main__":
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
