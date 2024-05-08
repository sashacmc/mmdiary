#!/usr/bin/python3
# pylint: disable=import-outside-toplevel,no-member # because of false positive on Resource

import argparse
import logging
import os
from datetime import datetime

import googleapiclient.discovery

from mmdiary.utils import log, datelib, progressbar
from mmdiary.utils.medialib import TIME_OUT_FORMAT, split_large_text

YOUTUBE_MAX_DESCRIPTION = 5000
YOUTUBE_MAX_COMMENT = 5000
YOUTUBE_URL = "https://www.youtube.com/watch?v="


def generate_video_url(video_id):
    return YOUTUBE_URL + video_id


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


def seconds_to_time(seconds):
    minutes = seconds // 60
    seconds = seconds % 60
    return f"{minutes:02d}:{seconds:02d}"


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
    def __init__(self):
        self.__res_dir = os.getenv("VIDEO_PROCESSOR_RES_DIR")
        os.makedirs(self.__res_dir, exist_ok=True)

        self.__lib = datelib.DateLib()
        self.__credentials = get_youtube_credentials("client_secrets.json", "token.json")
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

    def add_comment(self, video_id, comment_text):
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

    def process_date(self, date):
        mf = self.__lib.results()[date]
        data = mf.json()
        logging.info("Upload: %s", date)

        if not mf.have_file():
            raise FileNotFoundError("Source video file not exists")
        if not mf.have_json():
            raise FileNotFoundError("Json file not exists")

        if "url" in data:
            try:
                self.delete_video(extract_video_id(data["url"]))
            except Exception:
                logging.exception("Video deletion failed")

        time_labels = self.__gen_time_labels(data, "caption")
        comments_text = self.__gen_comments(data)
        logging.debug(comments_text)

        video_id = self.upload_video(mf.name(), date, time_labels)
        if video_id is None:
            return False

        for comment_text in comments_text:
            try:
                self.add_comment(video_id, comment_text)
            except Exception:
                logging.exception("Add comment failed")

        url = generate_video_url(video_id)
        logging.info("Video uploaded: %s", url)
        self.__lib.set_uploaded(date, url)
        logging.info("Upload done: %s", date)
        return True

    def process_all(self):
        converted = list(self.__lib.get_converted())

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
    parser = argparse.ArgumentParser()
    parser.add_argument("dates", nargs="*", help="Date to process")
    parser.add_argument('-l', '--logfile', help='Log file', default=None)
    return parser.parse_args()


def main():
    args = __args_parse()
    log.init_logger(args.logfile, logging.DEBUG)
    logging.getLogger("py.warnings").setLevel(logging.ERROR)

    vup = VideoUploader()

    res_count = 0
    err_count = 0
    if len(args.dates) == 0:
        res_count, err_count = vup.process_all()
    else:
        for date in args.dates:
            vup.process_date(date)
            res_count += 1

    logging.info("Uploader done: %s, errors: %s", res_count, err_count)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logging.exception("Video uploader main failed")
