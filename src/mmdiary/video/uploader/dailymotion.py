#!/usr/bin/python3

import argparse
import logging
import json
import os
import requests
import dailymotion


from fp.fp import FreeProxy

from mmdiary.utils import log, datelib, progressbar, proxypatch

DESCRIPTION = """
Uploads generated diary videos to Dailymotion 
Please declare enviromnent variables before use:
    MMDIARY_DAILYMOTION_ACCOUNTS - Path/filename to the file with account details
    MMDIARY_VIDEO_LIB_ROOTS - List of video library root dirs
    MMDIARY_VIDEO_RES_DIR - Result dir
"""

FILE_SIZE_LIMIT = 4 * 1024 * 1024 * 1024

DAILYMOTION_EMBED_URL = "https://www.dailymotion.com/embed/video/"

PROVIDER_NAME = "dailymotion"


def generate_video_url(provider, pos=None):
    url = DAILYMOTION_EMBED_URL + provider["url_id"] + "?queue-autoplay-next=0"
    if pos is None:
        return url
    return url + f"&start={int(pos)}"


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
        tmpfile = self.__accounts_file + ".tmp"
        with open(tmpfile, "w", encoding="utf-8") as f:
            data = {"accounts": self.__accounts, "current": self.__current}
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmpfile, self.__accounts_file)

    def get_all(self):
        return self.__accounts

    def count(self):
        return len(self.__accounts)

    def get(self):
        return self.__accounts[self.__current]

    def next(self):
        self.__max_try -= 1
        if self.__max_try <= 0:
            return False
        self.__current = (self.__current + 1) % len(self.__accounts)
        self.__save()
        return True


class VideoUploaderDailymotion:
    def __init__(self, use_proxy):
        self.__lib = datelib.DateLib()

        self.__accounts = DailymotionAccounts(
            os.path.expanduser(os.getenv("MMDIARY_DAILYMOTION_ACCOUNTS"))
        )
        self.__current_account = None
        if self.__accounts.count() == 0:
            raise UserWarning("No account specified")

        self.__use_proxy = use_proxy
        if self.__use_proxy is None:
            self.__use_proxy = self.__accounts.count() > 1

        self.__reset_proxy()

    def __reset_proxy(self):
        if self.__use_proxy:
            proxypatch.set_proxy(None)
            proxypatch.set_proxy(FreeProxy(rand=True).get())

    def __dm_auth(self, account):
        dm = dailymotion.Dailymotion(session_store_enabled=False)
        dm.set_grant_type(
            "password",
            scope=["manage_videos"],
            api_key=account["api_key"],
            api_secret=account["api_secret"],
            info={"username": account["username"], "password": account["password"]},
        )
        return dm

    def upload_video(self, fname, title):
        while True:
            account = self.__accounts.get()
            self.__current_account = account["name"]
            logging.info("Upload `%s` to `%s`", fname, self.__current_account)
            try:
                dm = self.__dm_auth(account)
                url = dm.upload(fname)
                res = dm.post(
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
            except dailymotion.DailymotionAuthError:
                if not self.__accounts.next():
                    logging.warning("All accounts limit was reached")
                    return None
                logging.info("Account auth error, try other one")
                self.__reset_proxy()
                continue
            except dailymotion.DailymotionApiError as ex:
                logging.exception("DailymotionApiError")
                exstr = str(ex)
                if "reached your upload rate limit" in exstr:
                    if not self.__accounts.next():
                        logging.warning("All accounts limit was reached")
                        return None
                    logging.info("Account reached limit, try other one")
                    self.__reset_proxy()
                    continue
                if "file exceeds maximum allowed size" in exstr:
                    logging.error("File %s too big, skip", fname)
                    raise
            except dailymotion.DailymotionClientError:
                logging.warning("Probably proxy error, try other one")
                self.__reset_proxy()
            except requests.exceptions.ProxyError:
                logging.warning("Probably proxy timeout, try other one")
                self.__reset_proxy()
            except requests.exceptions.SSLError:
                logging.warning("Probably proxy max retries exceeded, try other one")
                self.__reset_proxy()

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

        if os.path.getsize(mf.name()) >= FILE_SIZE_LIMIT:
            raise UserWarning(f"File {mf.name()} too big, skip")

        res = self.upload_video(mf.name(), date)
        if res is None:
            return False

        provider = {
            "name": PROVIDER_NAME,
            "account": self.__current_account,
            "video_id": res["id"],
            "url_id": res["private_id"],
        }
        logging.info("Video uploaded: %s, %s", provider, generate_video_url(provider))
        self.__lib.set_uploaded(date, provider)
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

    def check_accounts(self):
        for account in self.__accounts.get_all():
            name = account["name"]
            cont = True
            while cont:
                try:
                    dm = self.__dm_auth(account)
                    print(
                        "CHECK RESULT:",
                        name,
                        dm.get(
                            "/user/" + name,
                            params={"fields": "status,limits,videos_total"},
                        ),
                    )
                    cont = False
                except dailymotion.DailymotionApiError:
                    print("CHECK RESULT: Api error", name)
                    cont = False
                except dailymotion.DailymotionAuthError:
                    print("CHECK RESULT: Auth error", name)
                    cont = False
                except dailymotion.DailymotionClientError:
                    logging.exception(name)
                    logging.warning("Probably proxy error, try other one")
                except requests.exceptions.ProxyError:
                    logging.exception(name)
                    logging.warning("Probably proxy timeout, try other one")
                except requests.exceptions.SSLError:
                    logging.exception(name)
                    logging.warning("Probably proxy max retries exceeded, try other one")
                self.__reset_proxy()


def __use_proxy_mode(value):
    if value == "on":
        return True
    if value == "off":
        return False
    if value == "auto":
        return None
    raise argparse.ArgumentTypeError(f"Invalid use_proxy value: {value}")


def __args_parse():
    parser = argparse.ArgumentParser(
        description=DESCRIPTION, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("dates", nargs="*", help="Dates to process")
    parser.add_argument("-l", "--logfile", help="Log file", default=None)
    parser.add_argument("--use-proxy", help="Use proxy (on, off, auto)", default="auto")
    parser.add_argument("--check-accounts", help="Check accounts status", action="store_true")
    args = parser.parse_args()
    args.use_proxy = __use_proxy_mode(args.use_proxy)
    return args


def main():
    args = __args_parse()
    log.init_logger(args.logfile, logging.DEBUG)

    vup = VideoUploaderDailymotion(args.use_proxy)

    if args.check_accounts:
        vup.check_accounts()
        return

    res_count, err_count = vup.process_all(args.dates)
    logging.info("Uploader done: %s, errors: %s", res_count, err_count)


if __name__ == "__main__":
    main()
