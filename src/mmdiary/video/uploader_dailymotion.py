#!/usr/bin/python3

import argparse
import logging
import json
import os
import dailymotion

from mmdiary.utils import log, datelib, progressbar

DESCRIPTION = """
Uploads generated diary videos to Dailymotion 
Please declare enviromnent variables before use:
    MMDIARY_DAILYMOTION_ACCOUNTS - Path/filename to the file with account details
    MMDIARY_VIDEO_LIB_ROOTS - List of video library root dirs
    MMDIARY_VIDEO_RES_DIR - Result dir
"""

DAILYMOTION_EMBED_URL = "https://www.dailymotion.com/embed/video/"


def generate_video_url(video_id):
    return DAILYMOTION_EMBED_URL + video_id


class DailymotionAccounts:
    def __init__(self, accounts_file):
        self.__accounts_file = accounts_file
        self.__current = 0
        self.__read()

    def __read(self):
        with open(self.__accounts_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            self.__accounts = data["accounts"]
            self.__max_try = len(self.__accounts)
            if "current" in data:
                current = int(data["current"])
                if current < self.__max_try:
                    self.__current = current

    def __save(self):
        with open(self.__accounts_file, "w", encoding="utf-8") as f:
            data = {"accounts": self.__accounts, "current": self.__current}
            json.dump(data, f, ensure_ascii=False, indent=2)

    def get(self):
        return self.__accounts[self.__current]

    def next(self):
        self.__max_try -= 1
        if self.__max_try <= 0:
            return False
        self.__current = (self.__current + 1) % self.__accounts
        self.__save()
        return True


class VideoUploaderDailymotion:
    def __init__(self):
        self.__lib = datelib.DateLib()

        self.__accounts = DailymotionAccounts(
            os.path.expanduser(os.getenv("MMDIARY_DAILYMOTION_ACCOUNTS"))
        )
        self.__current_account = None

    def upload_video(self, fname, title):
        while True:
            account = self.__accounts.get()
            self.__current_account = account["name"]
            try:
                d = dailymotion.Dailymotion()
                d.set_grant_type(
                    "password",
                    scope=["manage_videos"],
                    api_key=account["api_key"],
                    api_secret=account["api_secret"],
                    info={"username": account["username"], "password": account["password"]},
                )
                url = d.upload(fname)
                res = d.post(
                    "/me/videos",
                    {
                        "url": url,
                        "title": title,
                        "published": "true",
                        "channel": "creation",
                        "private": "true",
                        "is_created_for_kids": "false",
                        "fields": "private_id",
                    },
                )
                logging.debug("uploaded: %s", res)
                return res
            except dailymotion.DailymotionApiError:
                if not self.__accounts.next():
                    logging.warning("All accounts limit was reached")
                    return None

    def delete_video(self, video_id):
        logging.info("Delete: %s", video_id)
        # Not implemented

    def process_date(self, date):
        mf = self.__lib.results()[date]
        logging.info("Process: %s", date)

        if not mf.have_json():
            raise FileNotFoundError("Json file not exists")

        data = mf.json()
        if "provider" in data:
            self.delete_video(data["provider"]["video_id"])

        res = self.upload_video(mf.name(), date)
        if res is None:
            return False

        url = generate_video_url(res["private_id"])
        provider = {
            "name": "dailymotion",
            "account": self.__current_account,
            "video_id": res["id"],
            "url_id": res["private_id"],
        }
        logging.info("Video uploaded: %s, %s", provider, url)
        self.__lib.set_uploaded(date, provider, url)
        logging.info("Upload done: %s", date)
        return True

    def process_all(self, masks):
        converted = list(self.__lib.get_converted(masks))

        pbar = progressbar.start("Upload", len(converted))
        err_count = 0
        for date in converted:
            try:
                if not self.process_date(date):
                    return pbar.value, err_count
            except Exception:
                err_count += 1
                logging.exception("Video uploading failed")

            pbar.increment()
        return pbar.value, err_count


def __args_parse():
    parser = argparse.ArgumentParser(
        description=DESCRIPTION, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("dates", nargs="*", help="Dates to process")
    parser.add_argument("-l", "--logfile", help="Log file", default=None)
    return parser.parse_args()


def main():
    args = __args_parse()
    log.init_logger(args.logfile, logging.DEBUG)

    vup = VideoUploaderDailymotion()

    res_count, err_count = vup.process_all(args.dates)
    logging.info("Uploader done: %s, errors: %s", res_count, err_count)


if __name__ == "__main__":
    main()
