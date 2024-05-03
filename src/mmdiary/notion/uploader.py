#!/usr/bin/python3
# pylint: disable=too-many-arguments

import argparse
import logging
import os

from notion.block import AudioBlock, CalloutBlock, TextBlock, VideoBlock
from notion.client import NotionClient
from notion.collection import CollectionRowBlock
from notion_client import Client

from mmdiary.utils import log, medialib, progressbar
from mmdiary.notion import cachedb
from mmdiary.video.uploader import seconds_to_time


DESCRIPTION = """
Uploads transcribed file(s) to the notion database.
Please declare enviromnent variables before use:
    NOTION_TOKEN - Notion web auth token
    NOTION_API_KEY - Notion API key
    NOTION_DB_ID - Notion Database ID
    NOTION_CACHE_DB_FILE - Cachedb file
"""


MAX_TEXT_SIZE = 2000
MAX_BLOCKS_BATCH_SIZE = 100


class NotionUploader:
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
        }
        self.__cache = cachedb.CacheDB(cache_db_file)
        self.__dry_run = dry_run
        self.__force_update = force_update
        self.__notion = NotionClient(token_v2=token, enable_caching=False)

        self.__database_id = database_id
        self.__notion_api = Client(auth=api_key)

        self.__init_existing_pages()

    def status(self):
        return self.__status

    def __init_existing_pages(self):
        cnt = len(self.__cache.list_existing_pages())
        if cnt == 0 and not self.__dry_run:
            logging.info("Cache empty, init...")
            self.__cache.sync_existing_pages(self.__notion_api, self.__database_id)
            cnt = len(self.__cache.list_existing_pages())

        self.__status["existing_init"] = cnt
        self.__status["existing"] = cnt
        logging.info("Found existing %i items", cnt)

    def __add_existing_page(self, source, processtime, bid):
        if not self.__dry_run:
            self.__cache.add_existing_page(source, processtime, bid)
        self.__status["existing"] += 1

    def __delete_page(self, source, bid):
        logging.debug("remove block %s", bid)
        if not self.__dry_run:
            block = self.__notion.get_block(bid)
            if isinstance(block, CollectionRowBlock):
                block.remove()
            else:
                block.remove(permanently=True)

            if source is not None:
                self.__cache.remove_from_existing_pages(source)

        self.__status["removed"] += 1

    def __check_existing(self, data, delete):
        source = data["source"]
        processtime = data["processtime"]
        page = self.__cache.check_existing_pages(source)
        logging.debug("check_existing: %s: %s", source, page)
        if page is None:
            return False

        # page processtime == "" mean that page was modied on notion side
        if processtime > page[0] and page[0] != "":
            if delete:
                logging.info("processtime changed: %s > %s for %s", processtime, page[0], source)
                self.__delete_page(source, page[1])
            return False

        if self.__force_update:
            if delete:
                logging.info("force update for %s", source)
                self.__delete_page(source, page[1])
            return False

        return True

    def __filter_existing(self, file):
        data = file.load_json()
        self.__check_json(data)

        return not self.__check_existing(data, False)

    def __add_row(self, title, date, source, processtime, icon):
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

    def __gen_video_description_block(self, timestamp, url, time, text):
        return {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {"content": timestamp, "link": {"url": url}},
                        "annotations": {
                            "bold": True,
                        },
                    },
                    {
                        "type": "text",
                        "text": {
                            "content": f" - {time}\n",
                        },
                        "annotations": {
                            "bold": True,
                        },
                    },
                    {
                        "type": "text",
                        "text": {
                            "content": text,
                        },
                    },
                ],
            },
        }

    def __create_audio_page(self, data, fname):
        if self.__dry_run:
            self.__status["created"] += 1
            return

        bid = self.__add_row(
            title=data["caption"],
            date=medialib.get_date_from_timestring(data["recordtime"]),
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
            logging.debug("Audio uploaded: %s", info)

            for block in medialib.split_large_text(data["text"], MAX_TEXT_SIZE):
                res.children.add_new(TextBlock, title=block)

            res.set("format.block_locked", True)

            self.__add_existing_page(data["source"], data["processtime"], res.id)
        except Exception:
            logging.warning("Delete uncompleate page for: %s", fname)
            self.__delete_page(None, bid)
            raise

        self.__status["created"] += 1

    def __create_video_page(self, data):
        if self.__dry_run:
            self.__status["created"] += 1
            return

        date = medialib.get_date_from_timestring(data["recordtime"])
        url = data["url"]

        bid = self.__add_row(
            title=date,
            date=date,
            source=data["source"],
            processtime=data["processtime"],
            icon="📹",
        )
        try:
            res = self.__notion.get_block(bid)
            video = res.children.add_new(VideoBlock)
            video.set_source_url(url)

            blocks = []
            pos = 0.0
            for video in data["videos"]:
                text = video["text"]
                if text != "":
                    blocks.append(
                        self.__gen_video_description_block(
                            seconds_to_time(int(pos)),
                            f"{url}&t={int(pos)}s",
                            medialib.get_time_from_timestring(video["timestamp"]),
                            text,
                        )
                    )
                pos += float(video["duration"])

            for i in range(0, len(blocks), MAX_BLOCKS_BATCH_SIZE):
                self.__notion_api.blocks.children.append(
                    bid, children=blocks[i : i + MAX_BLOCKS_BATCH_SIZE]
                )

            res.set("format.block_locked", True)

            self.__add_existing_page(data["source"], data["processtime"], res.id)
        except Exception:
            logging.warning("Delete uncompleate page for: %s", date)
            self.__delete_page(None, bid)
            raise

        self.__status["created"] += 1

    def __check_json(self, data):
        for f in ("recordtime", "processtime", "source"):
            if len(data[f].strip()) == 0:
                raise UserWarning(f"Incorrect file: empty {f}")

    def process(self, file):
        logging.info("Process file: %s", file)
        self.__status["processed"] += 1

        data = file.load_json()
        self.__check_json(data)

        if self.__check_existing(data, True):
            return

        tp = data.get("type")
        if tp == "audio":
            self.__create_audio_page(data, file.name())
        elif tp == "mergedvideo":
            self.__create_video_page(data)
        else:
            raise UserWarning("Unknown json type: {tp}")

        logging.info("Saved")

    def process_list(self, fileslist):
        fileslist = list(filter(self.__filter_existing, fileslist))

        self.__status["total"] = len(fileslist)
        pbar = progressbar.start("Uploading", len(fileslist))

        for af in fileslist:
            try:
                self.process(af)
            except Exception:
                self.__status["failed"] += 1
                logging.exception("Notion uploader failed")
            pbar.increment()

        pbar.finish()


def __args_parse():
    parser = argparse.ArgumentParser(
        description=DESCRIPTION, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument('inpath', help='Input path (single file or dir for search)')
    parser.add_argument('-l', '--logfile', help='Log file', default=None)
    parser.add_argument('-f', '--force', help='Force update (recreate all)', action='store_true')
    parser.add_argument('-d', '--dryrun', help='Dry run', action='store_true')
    return parser.parse_args()


def main():
    args = __args_parse()

    log.init_logger(args.logfile, level=logging.DEBUG)

    token = os.getenv("NOTION_TOKEN")
    api_key = os.getenv("NOTION_API_KEY")
    database_id = os.getenv("NOTION_DB_ID")
    cache_db_file = os.getenv("NOTION_CACHE_DB_FILE")

    fileslist = []
    if os.path.isfile(args.inpath):
        fileslist = (medialib.MediaFile(args.inpath),)
    elif os.path.isdir(args.inpath):
        lib = medialib.MediaLib(args.inpath)
        fileslist = lib.get_processed()

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

    logging.info("Done: %s", nup.status())


if __name__ == '__main__':
    main()
