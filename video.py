#!/usr/bin/python3

import os
import log
import progressbar
import logging
import argparse
import datelib

from moviepy.editor import VideoFileClip, concatenate_videoclips
import moviepy.video.fx.all as vfx

import googleapiclient.discovery


def add_round2(n):
    return n - n // 2 * 2


def resize_with_black_padding(clip, new_width=None, new_height=None):
    if new_width == clip.w and new_height == clip.h:
        return clip

    src_ratio = clip.w / clip.h
    dst_ratio = new_width / new_height

    if src_ratio == dst_ratio:
        return clip.resize(width=new_width, height=new_height)

    image_width = clip.w
    image_height = clip.h
    if src_ratio > dst_ratio:
        image_width = new_width
        image_height = int(image_width / src_ratio)
    else:
        image_height = new_height
        image_width = int(image_height * src_ratio)

    print(f"Image size: {image_width}x{image_height}")
    resized_clip = clip.resize(width=image_width, height=image_height)
    # correction to have result divisible by 2
    add_w = add_round2(resized_clip.w)
    add_h = add_round2(resized_clip.h)
    res = resized_clip.fx(
        vfx.margin,
        left=(new_width - image_width) // 2 + add_w,
        right=(new_width - image_width) // 2,
        top=(new_height - image_height) // 2 + add_h,
        bottom=(new_height - image_height) // 2,
        color=(0, 0, 0),
    )  # Black color padding

    if res.h != new_height or res.w != new_width:
        raise Exception(
            f"Incorrect resize: {res.w}x{res.h} != {new_width}x{new_height}"
        )
    return res


def rotate_if_needs(c):
    if c.rotation in (90, 270):
        c = c.resize(c.size[::-1])
        c.rotation = 0
    return c


def concatenate_to_mp4(filenames, outputfile):
    clips = [rotate_if_needs(VideoFileClip(f)) for f in filenames]

    max_height = 0
    max_width = 0
    for c in clips:
        if c.w > max_width:
            max_width = c.w
            max_height = c.h

    clips = [
        resize_with_black_padding(c, max_width, max_height) for c in clips
    ]

    durations = [c.duration for c in clips]
    logging.info(durations)

    final_clip = concatenate_videoclips(clips)

    final_clip.write_videofile(
        outputfile,
        codec="libx264",
        ffmpeg_params=[
            "-vf",
            "yadif,format=yuv420p",  # deinterlace videos if they're interlaced, produce pixel format with 4:2:0 chroma subsampling.
            "-crf",
            "18",  # produce a visually lossless file. Better than setting a bitrate manually.
            "-bf",
            "2",  # limit consecutive B-frames to 2
            "-c:a",
            "aac",  # use the native encoder to produce an AAC audio stream.
            "-q:a",
            "1",  # sets the highest quality for the audio. Better than setting a bitrate manually.
            "-ac",
            "2",  # rematrixes audio to stereo.
            "-ar",
            "48000",  # resamples audio to 48000 Hz.
            "-use_editlist",
            "0",  # avoids writing edit lists
            "-movflags",
            "+faststart",  # places moov atom/box at front of the output file.
        ],
    )

    return durations


def get_youtube_credentials(client_secrets, token_file):
    scopes = ["https://www.googleapis.com/auth/youtube.upload"]

    if os.path.exists(token_file):
        from google.oauth2.credentials import Credentials

        return Credentials.from_authorized_user_file(token_file, scopes=scopes)

    import google_auth_oauthlib.flow

    flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
        client_secrets,
        scopes=scopes,
        redirect_uri="urn:ietf:wg:oauth:2.0:oob",
    )
    authorization_url, _ = flow.authorization_url(
        access_type="offline", prompt="consent"
    )

    print(f"Please go to this URL and authorize access: {authorization_url}")
    authorization_code = input("Enter the authorization code: ")

    flow.fetch_token(code=authorization_code)
    credentials = flow.credentials

    with open(token_file, "w") as token:
        token.write(credentials.to_json())

    return credentials


def seconds_to_time(seconds):
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def generate_description(time_labels):
    description = ""
    for time, label in time_labels:
        description += f"{time} - {label}\n"
    return description


class VideoProcessor(object):
    def __init__(self, update_existing):
        self.__update_existing = update_existing
        scan_paths = list(
            filter(
                None,
                os.getenv("VIDEO_LIB_ROOTS").split(":"),
            ),
        )
        db_file = os.getenv("VIDEO_LIB_DB")
        self.__lib = datelib.DateLib(scan_paths, db_file)
        self.__credentials = get_youtube_credentials(
            "client_secrets.json", "token.json"
        )

    def upload_video(self, fname, title, time_labels):
        youtube = googleapiclient.discovery.build(
            "youtube", "v3", credentials=self.__credentials
        )

        # Upload video
        request_body = {
            "snippet": {
                "title": title,
                "description": generate_description(time_labels),
                "tags": ["daily"],
            },
            "status": {"privacyStatus": "unlisted"},
        }

        media_file = googleapiclient.http.MediaFileUpload(
            fname, chunksize=-1, resumable=True
        )
        response_upload = (
            youtube.videos()
            .insert(
                part="snippet,status", body=request_body, media_body=media_file
            )
            .execute()
        )

        vid = response_upload["id"]
        logging.info(f"Video uploaded: {vid}")

    def process_date(self, date):
        logging.info(f"Start: {date}")
        afiles = self.__lib.get_files_by_date(date)
        fnames = [af.name() for af in afiles]
        logging.info(f"found {len(fnames)} files")

        tempfilename = "/mnt/multimedia/tmp/00_test_concat.mp4"
        durations = concatenate_to_mp4(fnames, tempfilename)

        time_labels = []
        pos = 0
        for af, duration in zip(afiles, durations):
            time = af.prop().time().strftime("%H:%M:%S")
            caption = af.load_json()["caption"].strip()
            pos += duration

            time_labels.append(
                (seconds_to_time(int(pos)), f"[{time}] {caption}")
            )

        logging.info(time_labels)

        self.upload_video(tempfilename, date, time_labels)

        logging.info(f"Done: {date}")

    def process_all(self, dirname, filenames):
        nonprocessed = list(self.__lib.get_nonprocessed())

        pbar = progressbar.ProgressBar(
            maxval=len(nonprocessed),
            widgets=[
                "Process",
                ' ',
                progressbar.Percentage(),
                ' ',
                progressbar.Bar(),
                ' ',
                progressbar.ETA(),
            ],
        ).start()

        for date, url in nonprocessed:
            try:
                self.process_date(date)
            except Exception:
                logging.exception("Video processing failed")
            pbar.increment()

        pbar.finish()


def __args_parse():
    parser = argparse.ArgumentParser()
    parser.add_argument('date', help='Date to process')
    parser.add_argument('-l', '--logfile', help='Log file', default=None)
    parser.add_argument(
        '-u', '--update', help='Update existing', action='store_true'
    )
    return parser.parse_args()


def main():
    args = __args_parse()
    log.initLogger(args.logfile)

    vp = VideoProcessor(args.update)

    if args.date is None:
        vp.process_all()
    else:
        vp.process_date(args.date)

    logging.info("Done.")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logging.exception("Main failed")
