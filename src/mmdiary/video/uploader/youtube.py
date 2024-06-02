#!/usr/bin/python3
# pylint: disable=import-outside-toplevel,line-too-long,no-member # because of false positive on Resource

import argparse
import logging
import os
from datetime import datetime

import googleapiclient.discovery

from mmdiary.utils import log, datelib, progressbar
from mmdiary.utils.medialib import TIME_OUT_FORMAT, split_large_text
from mmdiary.video.uploader.common import seconds_to_time

DESCRIPTION = """
Uploads generated diary videos to YouTube
Please declare enviromnent variables before use:
    MMDIARY_YOUTUBE_CLIENT_SECRETS - Path/filename to the client_secrets.json file for YouTube API
        Can be found/created there: https://console.cloud.google.com/apis/credentials
    MMDIARY_YOUTUBE_TOKEN - Path/filename to the cached YouTube token
        Path must exists, file will be created after the first authorization
    MMDIARY_VIDEO_LIB_ROOTS - List of video library root dirs
    MMDIARY_VIDEO_RES_DIR - Result dir
"""

YOUTUBE_MAX_DESCRIPTION = 5000
YOUTUBE_MAX_COMMENT = 5000
YOUTUBE_URL = "https://www.youtube.com/watch?v="

PROVIDER_NAME = "youtube"


def generate_video_url(provider, pos=None):
    url = YOUTUBE_URL + provider["video_id"]
    if pos is None:
        return url
    return url + f"&t={int(pos)}s"


def extract_video_id(video_url):
    return video_url.split("v=")[1]


def get_youtube_credentials(client_secrets, token_file):
    scopes = [
        "https://www.googleapis.com/auth/youtube.upload",
        "https://www.googleapis.com/auth/youtube.force-ssl",
    ]

    if os.path.exists(token_file):
        from google.oauth2.credentials import Credentials

        return Credentials.from_authorized_user_file(token_file, scopes=scopes)

    import google_auth_oauthlib.flow

    flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
        client_secrets,
        scopes=scopes,
        redirect_uri="urn:ietf:wg:oauth:2.0:oob",
    )
    authorization_url, _ = flow.authorization_url(access_type="offline", prompt="consent")

    print(f"Please go to this URL and authorize access: {authorization_url}")
    authorization_code = input("Enter the authorization code: ")

    flow.fetch_token(code=authorization_code)
    credentials = flow.credentials

    with open(token_file, "w", encoding="utf-8") as token:
        token.write(credentials.to_json())

    return credentials


def generate_description_full(time_labels):
    description = ""
    pos = 0.0
    for duration, label in time_labels:
        time = seconds_to_time(int(pos))
        description += f"{time} - {label}\n"
        pos += duration
    logging.info("full description len: %i", len(description))
    return description


def generate_description_redused(time_labels):
    description = ""
    pos = 0.0
    last_pos = -100
    for duration, label in time_labels:
        if pos - last_pos > 20 and len(label) > 15:  # sec
            time = seconds_to_time(int(pos))
            label = label[:50]
            description += f"{time} - {label}\n"
            last_pos = pos
        pos += duration
    logging.info("reduced description len: %i", len(description))
    return description


def generate_description(time_labels):
    description = generate_description_full(time_labels)
    if len(description) < YOUTUBE_MAX_DESCRIPTION:
        return description

    description = generate_description_redused(time_labels)
    if len(description) < YOUTUBE_MAX_DESCRIPTION:
        return description

    logging.warning("description cutted")
    return description[:YOUTUBE_MAX_DESCRIPTION]


class VideoUploader:
    def __init__(self, update, upload_verification):
        self.__update = update
        self.__upload_verification = upload_verification

        self.__lib = datelib.DateLib()

        token_env = "MMDIARY_YOUTUBE_TOKEN"
        if self.__upload_verification:
            token_env = "MMDIARY_YOUTUBE_TOKEN_VERIFY"
        token_file = os.path.expanduser(os.getenv(token_env))
        logging.debug("Token file: %s", token_file)
        self.__account = os.path.splitext(os.path.basename(token_file))[0]
        self.__credentials = get_youtube_credentials(
            os.path.expanduser(os.getenv("MMDIARY_YOUTUBE_CLIENT_SECRETS")),
            token_file,
        )

        self.__youtube = googleapiclient.discovery.build(
            "youtube", "v3", credentials=self.__credentials
        )

    def __gen_time_labels(self, data, text_field, delimiter=" ", skip_empty=False):
        time_labels = []
        for info in data["videos"]:
            time = datetime.strptime(info["timestamp"], TIME_OUT_FORMAT).strftime("%H: %M: %S")
            caption = info[text_field]
            if len(caption) == 0 and skip_empty:
                continue
            time_labels.append((info["duration"], f"[{time}]{delimiter}{caption}"))
        return time_labels

    def __gen_comments(self, data):
        time_labels = self.__gen_time_labels(data, "text", delimiter="\n", skip_empty=True)
        comment_text = generate_description_full(time_labels)
        return split_large_text(comment_text, YOUTUBE_MAX_COMMENT)

    def upload_video(self, fname, title, time_labels):
        request_body = {
            "snippet": {
                "title": title,
                "description": generate_description(time_labels),
                "tags": ["daily"],
            },
            "status": {"privacyStatus": "unlisted"},
        }

        try:
            media_file = googleapiclient.http.MediaFileUpload(fname, chunksize=-1, resumable=True)
            request = self.__youtube.videos().insert(
                part="snippet,status", body=request_body, media_body=media_file
            )
            logging.debug("Upload started: %s", request_body)
            response = request.execute()
            video_id = response["id"]
            return video_id
        except googleapiclient.errors.ResumableUploadError as ex:
            if ex.status_code == 403 and ex.error_details[0]["reason"] == "quotaExceeded":
                logging.error("quotaExceeded")
                return None
            if ex.status_code == 400 and ex.error_details[0]["reason"] == "uploadLimitExceeded":
                logging.error("uploadLimitExceeded")
                return None

            raise

    def update_video(self, video_id, title, time_labels):
        logging.debug("Update video: %s", video_id)
        request = self.__youtube.videos().update(
            part="snippet",
            body={
                "id": video_id,
                "snippet": {
                    "title": title,
                    "description": generate_description(time_labels),
                    "tags": ["daily"],
                    "categoryId": "22",
                },
            },
        )
        request.execute()

    def __list_comments(self, video_id):
        try:
            request = self.__youtube.commentThreads().list(
                part="snippet", videoId=video_id, maxResults=100
            )

            comment_ids = []
            while request:
                response = request.execute()
                for item in response["items"]:
                    comment_ids.append(item["id"])
                request = self.__youtube.commentThreads().list_next(request, response)

            return comment_ids
        except googleapiclient.errors.HttpError as ex:
            if ex.status_code == 403 and ex.error_details[0]["reason"] == "commentsDisabled":
                logging.debug("commentsDisabled")
                return []
            if ex.status_code == 404 and ex.error_details[0]["reason"] == "videoNotFound":
                raise UserWarning("videoNotFound") from None
            raise

    def delete_comments(self, video_id):
        comment_ids = self.__list_comments(video_id)
        logging.debug("Remove comments for fideo %s: %s", video_id, comment_ids)
        for comment_id in comment_ids:
            self.__youtube.comments().delete(id=comment_id).execute()

    def add_comment(self, video_id, comment_text):
        if comment_text == "":
            return
        request = self.__youtube.commentThreads().insert(
            part="snippet",
            body={
                "snippet": {
                    "videoId": video_id,
                    "topLevelComment": {"snippet": {"textOriginal": comment_text}},
                }
            },
        )

        logging.debug("Comment started")
        response = request.execute()
        logging.debug(response)

    def delete_video(self, video_id):
        logging.info("Delete: %s", video_id)
        self.__youtube.videos().delete(id=video_id).execute()

    def check_video_exists(self, video_id):
        request = self.__youtube.videos().list(part="snippet", id=video_id)
        response = request.execute()

        return 'items' in response and len(response['items']) > 0

    def __check_provider(self, data):
        if "provider" not in data:
            return False
        if data["provider"]["name"] != PROVIDER_NAME:
            raise UserWarning("Incorrect provider")
        return True

    def process_date(self, date, only_verified):
        mf = self.__lib.results()[date]
        logging.info("Process: %s", date)

        if not mf.have_json():
            raise FileNotFoundError("Json file not exists")

        update = self.__update or not mf.have_file()
        if update:
            logging.debug("Update only")

        data = mf.json()
        upload = data.get("upload", not only_verified)
        if not upload:
            logging.info("Video blocked to upload, skip")
            return True
        time_labels = self.__gen_time_labels(data, "caption")
        comments_text = self.__gen_comments(data)
        logging.debug(comments_text)

        video_id = None
        if update:
            if not self.__check_provider(data):
                raise UserWarning("provider field missed, update impossible")
            video_id = data["provider"]["video_id"]
            self.delete_comments(video_id)
            self.update_video(video_id, date, time_labels)
        else:
            if self.__check_provider(data):
                try:
                    self.delete_video(data["provider"]["video_id"])
                except Exception:
                    logging.exception(
                        "Video deletion failed, possible it was removed by YouTube, skip uploading"
                    )
                    raise

            video_id = self.upload_video(mf.name(), date, time_labels)
            if video_id is None:
                return False

        for comment_text in comments_text:
            try:
                self.add_comment(video_id, comment_text)
            except Exception:
                logging.exception("Add comment failed")

        provider = {
            "name": PROVIDER_NAME,
            "account": self.__account,
            "video_id": video_id,
            "url_id": video_id,
        }
        logging.info("Video uploaded: %s, %s", provider, generate_video_url(provider))
        self.__lib.set_uploaded(date, provider, self.__upload_verification)
        logging.info("Upload done: %s", date)
        return True

    def process_all(self, masks, only_verified):
        converted = list(self.__lib.get_converted(masks))

        pbar = progressbar.start("Upload", len(converted))
        err_count = 0
        for date in converted:
            try:
                if not self.process_date(date, only_verified):
                    return pbar.value, err_count
            except Exception:
                err_count += 1
                logging.exception("Video uploading failed")

            pbar.increment()
        return pbar.value, err_count

    def verify_urls(self, masks):
        toprocess = []
        if self.__upload_verification:
            toprocess = sorted(self.__lib.get_uploaded(masks, True))
        else:
            toprocess = sorted(self.__lib.get_converted(masks) + self.__lib.get_uploaded(masks))
        res = {"count": len(toprocess), "err": 0, "no_url": 0, "exists": 0, "not_exists": 0}
        for date in toprocess:
            try:
                mf = self.__lib.results()[date]
                data = mf.json()
                if "provider" not in data:
                    res["no_url"] += 1
                    continue
                video_id = data["provider"]["video_id"]
                is_exists = self.check_video_exists(video_id)
                if is_exists:
                    res["exists"] += 1
                else:
                    res["not_exists"] += 1
                logging.info("Video %s is exists: %s", date, is_exists)
                if self.__upload_verification:
                    if is_exists:
                        self.__lib.set_converted(date, {"provider": None, "upload": True})
                    else:
                        # don't delete url for videos because it still avaliable in embedded player
                        # and it will be easy to investiagate
                        self.__lib.set_converted(date, {"upload": False})

            except Exception:
                res["err"] += 1
                logging.exception("Video verification failed")
        return res


def __args_parse():
    parser = argparse.ArgumentParser(
        description=DESCRIPTION, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("dates", nargs="*", help="Dates to process")
    parser.add_argument("-l", "--logfile", help="Log file", default=None)
    parser.add_argument(
        "-u",
        "--update",
        help="Update video description/comment without reupload",
        action='store_true',
    )
    parser.add_argument(
        "--verify-urls", help="Verify uploaded videos by urls check", action='store_true'
    )
    parser.add_argument(
        "--upload-verification",
        help="Enable upload verification mode to test video correctly pass all YouTube restrictions:"
        + "\n  Uses MMDIARY_YOUTUBE_TOKEN_VERIFY enviromnent varable for user token"
        + "\n  Sets `uploadverification` state in place of `uploaded`"
        + "\n  --veribles-urls will process only dates in `uploadverification` state and set `upload` field",
        action='store_true',
    )
    parser.add_argument(
        "--only-verified",
        help="Upload to main channel only video witch already pass verification",
        action='store_true',
    )
    return parser.parse_args()


def main():
    args = __args_parse()
    log.init_logger(args.logfile, logging.DEBUG)
    logging.getLogger("py.warnings").setLevel(logging.ERROR)

    vup = VideoUploader(args.update, args.upload_verification)

    if args.verify_urls:
        res = vup.verify_urls(args.dates)
        logging.info("Verification done: %s", res)
        return

    res_count, err_count = vup.process_all(args.dates, args.only_verified)
    logging.info("Uploader done: %s, errors: %s", res_count, err_count)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logging.exception("Video uploader main failed")
