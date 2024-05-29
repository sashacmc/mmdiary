#!/usr/bin/python3
# pylint: disable=too-many-arguments,too-many-instance-attributes

import argparse
import logging
import os
import sys

from notion.block import AudioBlock, CalloutBlock, TextBlock, VideoBlock
from notion.client import NotionClient
from notion.collection import CollectionRowBlock
from notion_client import Client

from mmdiary.utils import log, medialib, progressbar
from mmdiary.notion import cache
from mmdiary.video.uploader import seconds_to_time, generate_video_url


DESCRIPTION = """
Uploads transcribed file(s) to the notion database.
Please declare enviromnent variables before use:
    MMDIARY_NOTION_TOKEN - Notion web auth token, please obtain the `token_v2` value by inspectingn
        your browser cookies on a logged-in (non-guest) session on Notion.so
    MMDIARY_NOTION_API_KEY - Notion API key, please create notion integration and provide an API key
        see details there: https://www.notion.so/my-integrations
        (don't forget to share your page/workspace with the integration you created)
    MMDIARY_NOTION_AUDIO_DB_ID - Notion Database ID for Audio Notes (can be created by --init command)
    MMDIARY_NOTION_VIDEO_DB_ID - Notion Database ID for Video Diary (can be created by --init command)
    MMDIARY_NOTION_CACHE_FILE - Cache file
"""


MAX_TEXT_SIZE = 2000
MAX_BLOCKS_BATCH_SIZE = 100


class NotionUploader:
    def __init__(
        self,
        token,
        api_key,
        audio_db_id,
        video_db_id,
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
        self.__cache = cache.Cache()
        self.__dry_run = dry_run
        self.__force_update = force_update
        self.__notion = NotionClient(token_v2=token, enable_caching=False)

        self.__audio_db_id = audio_db_id
        self.__video_db_id = video_db_id
        self.__notion_api = Client(auth=api_key)

        self.__init_existing_pages()

    def status(self):
        return self.__status

    def __init_existing_pages(self):
        cnt = len(self.__cache.list_existing_pages())
        if cnt == 0 and not self.__dry_run:
            logging.info("Cache empty, init...")
            self.__cache.sync_existing_pages(
                self.__notion_api, (self.__audio_db_id, self.__video_db_id)
            )
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

    def __check_existing(self, file, delete):
        source = file.get_field("source")
        processtime = file.get_field("processtime")
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
        if not file.have_field("source"):
            return False
        return not self.__check_existing(file, False)

    def __create_database(self, parent_page_id, icon, title, fields):
        properties = {}
        for f, tp in fields.items():
            properties[f] = {tp: {}}

        res = self.__notion_api.databases.create(
            parent={
                "page_id": parent_page_id,
            },
            icon={"type": "emoji", "emoji": icon},
            title=[
                {
                    "type": "text",
                    "text": {
                        "content": title,
                    },
                }
            ],
            properties=properties,
        )
        logging.info("Database %s created: %s", title, res["id"])
        return res["id"]

    def __create_audio_database(self, parent_page_id):
        return self.__create_database(
            parent_page_id,
            "📔",
            "Audio Notes",
            {
                "source": "rich_text",
                "processtime": "rich_text",
                "Date": "date",
                "Title": "title",
                "Created time": "created_time",
            },
        )

    def __create_video_database(self, parent_page_id):
        return self.__create_database(
            parent_page_id,
            "📽️",
            "Video Diary",
            {
                "source": "rich_text",
                "processtime": "rich_text",
                "Date": "date",
                "Title": "title",
                "Created time": "created_time",
                "Provider": "rich_text",
                "Account": "rich_text",
            },
        )

    def init_databases(self, parent_page_id):
        audio_db_id = self.__create_audio_database(parent_page_id)
        video_db_id = self.__create_video_database(parent_page_id)

        return audio_db_id, video_db_id

    def __prop_rich_text(self, text):
        return {
            "type": "rich_text",
            "rich_text": [
                {
                    "type": "text",
                    "text": {"content": text},
                },
            ],
        }

    def __add_row(self, db_id, title, date, source, processtime, icon, provider=None, account=None):
        properties = {
            "title": {"title": [{"text": {"content": title}}]},
            "Date": {"type": "date", "date": {"start": date}},
            "source": self.__prop_rich_text(source),
            "processtime": self.__prop_rich_text(processtime),
        }
        if provider is not None:
            properties["Provider"] = self.__prop_rich_text(provider)
        if account is not None:
            properties["Account"] = self.__prop_rich_text(account)

        res = self.__notion_api.pages.create(
            parent={"database_id": db_id},
            icon={"type": "emoji", "emoji": icon},
            properties=properties,
        )

        return res["id"]

    def __gen_video_description_blocks(self, timestamp, url, time, text):
        max_size = MAX_TEXT_SIZE - len(url) - len(timestamp) - len(time)
        texts = medialib.split_large_text(text, max_size)
        first_text = texts[0]
        blocks = [
            {
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
                                "content": first_text,
                            },
                        },
                    ],
                },
            }
        ]

        for next_text in texts[1:]:
            blocks.append(
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {
                                    "content": next_text,
                                },
                            },
                        ],
                    },
                }
            )
        return blocks

    def __create_audio_page(self, file):
        if self.__dry_run:
            self.__status["created"] += 1
            return

        bid = self.__add_row(
            self.__audio_db_id,
            title=file.get_field("caption"),
            date=file.recorddate(),
            source=file.get_field("source"),
            processtime=file.get_field("processtime"),
            icon="🎙️",
        )
        try:
            res = self.__notion.get_block(bid)
            res.children.add_new(
                CalloutBlock,
                title=file.recordtime(),
                icon="📅",
                color="gray_background",
            )

            audio = res.children.add_new(AudioBlock)
            info = audio.upload_file(file.name())
            logging.debug("Audio uploaded: %s", info)

            for block in medialib.split_large_text(file.get_field("text"), MAX_TEXT_SIZE):
                res.children.add_new(TextBlock, title=block)

            res.set("format.block_locked", True)

            self.__add_existing_page(
                file.get_field("source"), file.get_field("processtime"), res.id
            )
        except Exception:
            logging.warning("Delete uncompleate page for: %s", file)
            self.__delete_page(None, bid)
            raise

        self.__status["created"] += 1

    def __create_video_page(self, file):
        if file.state() != "uploaded":
            logging.debug("file not uploaded to video provider yet: %s", file)
            return

        if self.__dry_run:
            self.__status["created"] += 1
            return

        date = file.recorddate()
        provider = file.get_field("provider")

        bid = self.__add_row(
            self.__video_db_id,
            title=date,
            date=date,
            source=file.get_field("source"),
            processtime=file.get_field("processtime"),
            provider=provider["name"],
            account=provider["account"],
            icon="📹",
        )
        try:
            res = self.__notion.get_block(bid)
            video = res.children.add_new(VideoBlock)
            video.set_source_url(generate_video_url(provider))

            blocks = []
            pos = 0.0
            for video in file.get_field("videos"):
                text = video["text"]
                if text != "":
                    blocks += self.__gen_video_description_blocks(
                        seconds_to_time(int(pos)),
                        generate_video_url(provider, pos),
                        medialib.get_time_from_timestring(video["timestamp"]),
                        text,
                    )

                pos += float(video["duration"])

            for i in range(0, len(blocks), MAX_BLOCKS_BATCH_SIZE):
                self.__notion_api.blocks.children.append(
                    bid, children=blocks[i : i + MAX_BLOCKS_BATCH_SIZE]
                )

            res.set("format.block_locked", True)

            self.__add_existing_page(
                file.get_field("source"), file.get_field("processtime"), res.id
            )
        except Exception:
            logging.warning("Delete uncompleate page for: %s", date)
            self.__delete_page(None, bid)
            raise

        self.__status["created"] += 1

    def process(self, file):
        logging.info("Process file: %s", file)
        self.__status["processed"] += 1

        if self.__check_existing(file, True):
            return

        tp = file.type()
        if tp == "audio":
            self.__create_audio_page(file)
        elif tp == "mergedvideo":
            self.__create_video_page(file)
        else:
            raise UserWarning("Unknown json type: {tp}")

        logging.info("Saved")

    def process_list(self, fileslist):
        logging.debug("fileslist len before filter: %i", len(fileslist))
        fileslist = list(filter(self.__filter_existing, fileslist))
        logging.debug("fileslist len after filter: %i", len(fileslist))

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
    parser.add_argument("inpath", nargs="?", help="Input path (single file or dir for search)")
    parser.add_argument("--init", help="Init Notion databases (provide parent page ID)")
    parser.add_argument("-l", "--logfile", help="Log file")
    parser.add_argument("-f", "--force", help="Force update (recreate all)", action="store_true")
    parser.add_argument("-d", "--dryrun", help="Dry run", action="store_true")
    return parser.parse_args()


def main():
    args = __args_parse()

    log.init_logger(args.logfile, level=logging.DEBUG)

    token = os.getenv("MMDIARY_NOTION_TOKEN")
    if not token:
        print("MMDIARY_NOTION_TOKEN was not set")
        sys.exit(1)

    api_key = os.getenv("MMDIARY_NOTION_API_KEY")
    if not api_key:
        print("MMDIARY_NOTION_API_KEY was not set")
        sys.exit(1)

    audio_db_id = os.getenv("MMDIARY_NOTION_AUDIO_DB_ID")
    video_db_id = os.getenv("MMDIARY_NOTION_VIDEO_DB_ID")

    nup = NotionUploader(
        token=token,
        api_key=api_key,
        audio_db_id=audio_db_id,
        video_db_id=video_db_id,
        force_update=args.force,
        dry_run=args.dryrun,
    )

    if args.init:
        audio_db_id, video_db_id = nup.init_databases(args.init)
        print("Databases inited")
        print("Plase set ids to your enviromnent:")
        print(f"export MMDIARY_NOTION_AUDIO_DB_ID='{audio_db_id}'")
        print(f"export MMDIARY_NOTION_VIDEO_DB_ID='{video_db_id}'")
        print("(don't forget to share created DBs with the your integration)")
        return

    if not api_key:
        print("MMDIARY_NOTION_CACHE was not set")
        sys.exit(1)

    if not audio_db_id or not video_db_id:
        print(
            "MMDIARY_NOTION_AUDIO_DB_ID or MMDIARY_NOTION_VIDEO_DB_ID was not set,",
            "please use '--init'",
        )
        sys.exit(1)

    if args.inpath is None:
        print("Input path not provided")
        sys.exit(1)

    fileslist = []
    if os.path.isfile(args.inpath):
        fileslist = (medialib.MediaFile(args.inpath),)
    elif os.path.isdir(args.inpath):
        lib = medialib.MediaLib(args.inpath)
        fileslist = lib.get_processed(should_have_file=False)

    if len(fileslist) == 0:
        logging.info("Nothing to do, exit")
        return

    nup.process_list(fileslist)

    logging.info("Done: %s", nup.status())


if __name__ == "__main__":
    main()
