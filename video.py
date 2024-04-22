#!/usr/bin/python3

import os
import log
import progressbar
import logging
import argparse
import datelib
import subprocess
import json

import googleapiclient.discovery

YOUTUBE_MAX_DESCRIPTION = 5000


def ffprobe_get_video_info(filename):
    command = [
        'ffprobe',
        '-v',
        'error',
        '-show_format',
        '-show_streams',
        '-print_format',
        'json',
        filename,
    ]
    result = subprocess.run(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    if result.returncode != 0:
        error_msg = result.stderr.decode('utf-8').strip()
        raise Exception(error_msg)

    output = result.stdout.decode('utf-8')
    data = json.loads(output)

    video_stream = next(
        (
            stream
            for stream in data['streams']
            if stream['codec_type'] == 'video'
        ),
        None,
    )
    if video_stream is None:
        raise Exception("File has no video steam")

    info = {
        "width": int(video_stream.get('width', 0)),
        "height": int(video_stream.get('height', 0)),
        "duration": float(data['format']['duration']),
        "orientation": int(
            video_stream.get('side_data_list', [{}])[0].get('rotation', 0)
        ),
        "interlaced": (
            video_stream.get('field_order', 'unknown') != "progressive"
        ),
    }
    logging.info(f"{filename}: {info}")
    return info


FFMPEG_BINARY = "ffmpeg"
FFMPEG_CODEC = "libx264"
REENCODE_FPS = "25"


def ffmpeg_apply_video_filters(in_file, out_file, filters, add_params=[]):
    cmd = [FFMPEG_BINARY, "-y"]  # overwrite existing
    cmd += ("-i", in_file)  # input file
    cmd += ("-vf", ",".join(filters))  # filters
    if out_file is None:
        cmd += ("-f", "null", "-")
    else:
        cmd += ("-qp", "0")  # lossless
        cmd += ("-preset", "ultrafast")  # maimum speed, big file
        cmd += ("-acodec", "copy")  # copy audio as is
        cmd += ("-c:v", FFMPEG_CODEC)  # video codec
        cmd += add_params
        cmd += (out_file,)
    logging.debug(cmd)
    res = subprocess.run(cmd).returncode
    if res != 0:
        raise Exception(f"ffmpeg_apply_video_filters failed: {res}")


def ffmpeg_deinterlace(in_file, out_file):
    filters = [
        "yadif",
        "format=yuv420p",
    ]
    logging.info("start deinterlace")
    ffmpeg_apply_video_filters(in_file, out_file, filters)


def ffmpeg_stabilize(in_file, out_file, tmpdirname):
    trffile = os.path.join(tmpdirname, 'transforms.txt')
    try:
        filters = [
            f"vidstabdetect=stepsize=32:shakiness=10:accuracy=10:result={trffile}",
        ]
        logging.info("start stab prep")
        ffmpeg_apply_video_filters(in_file, None, filters)

        filters = [
            f"vidstabtransform=input={trffile}:zoom=0:smoothing=10,unsharp=5:5:0.8:3:3:0.4",
        ]
        logging.info("start stab")
        ffmpeg_apply_video_filters(in_file, out_file, filters)
    finally:
        try:
            os.unlink(trffile)
        except FileNotFoundError:
            pass


def ffmpeg_resize(in_file, out_file, w, h):
    filters = [
        "format=yuv420p",
        f"scale=w='if(gt(a,{w}/{h}),{w},trunc(oh*a/2)*2)':h='if(gt(a,{w}/{h}),trunc(ow/a/2)*2,{h})'",
        f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black",
    ]
    add_params = ["-r", REENCODE_FPS]
    logging.info("start resize")
    ffmpeg_apply_video_filters(in_file, out_file, filters, add_params)


def ffmpeg_concatenate(filenames, out_file, tmpdirname):
    if len(filenames) == 0:
        logging.warning("empty filenames list")
        return
    listfile = os.path.join(tmpdirname, 'list.txt')
    with open(listfile, 'w') as f:
        for fname in filenames:
            f.write(f"file '{fname}'\n")

    cmd = [FFMPEG_BINARY, "-y"]  # overwrite existing
    cmd += ("-f", "concat")
    cmd += ("-safe", "0")
    cmd += ("-i", listfile)
    cmd += ("-c:v", FFMPEG_CODEC)
    cmd += ("-crf", "17")  # produce a visually lossless file.
    cmd += ("-bf", "2")  # limit consecutive B-frames to 2
    cmd += ("-use_editlist", "0")  # avoids writing edit lists
    # places moov atom/box at front of the output file.
    cmd += ("-movflags", "+faststart")
    # use the native encoder to produce an AAC audio stream.
    cmd += ("-c:a", "aac")
    cmd += ("-q:a", "1")  # sets the highest quality for the audio.
    cmd += ("-ac", "2")  # rematrixes audio to stereo.
    cmd += ("-ar", "48000")  # resamples audio to 48000 Hz.
    cmd += (out_file,)
    logging.info("start concatenate")
    logging.debug(cmd)
    try:
        res = subprocess.run(cmd).returncode
        if res != 0:
            raise Exception(f"concatenate failed: {res}")
        logging.info(f"file saved: {out_file}")
    finally:
        try:
            os.unlink(listfile)
        except FileNotFoundError:
            pass


def concatenate_to_mp4(
    filenames, outputfile, tmpdirname="/tmp", dry_run=False
):
    max_height = 0
    max_width = 0
    durations = []
    interlaced = []
    for f in filenames:
        info = ffprobe_get_video_info(f)
        durations.append(info["duration"])
        interlaced.append(info["interlaced"])
        w = info["width"]
        h = info["height"]
        if info["orientation"] not in (0, 180, -180):
            w, h = h, w
        if w > max_width:
            max_width = w
            max_height = h

    logging.info(f"Result video: width={max_width}, height={max_height}")

    tmpfilenames = []

    if dry_run:
        return durations

    for i, f in enumerate(filenames):
        fname = os.path.join(tmpdirname, f"{i}.mp4")
        tfname = os.path.join(tmpdirname, f"{i}_tmp.mp4")

        logging.info(f"convert '{f}' to '{fname}'")

        if interlaced[i]:
            ffmpeg_deinterlace(f, tfname)
            os.rename(tfname, fname)
            f = fname

        ffmpeg_stabilize(f, tfname, tmpdirname)
        os.rename(tfname, fname)

        ffmpeg_resize(fname, tfname, max_width, max_height)
        os.rename(tfname, fname)

        tmpfilenames.append(fname)

    ffmpeg_concatenate(tmpfilenames, outputfile, tmpdirname)

    for f in tmpfilenames:
        os.unlink(f)

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
    logging.info(f"full description len: {len(description)}")
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
    logging.info(f"reduced description len: {len(description)}")
    return description


def generate_description(time_labels):
    description = generate_description_full(time_labels)
    if len(description) < YOUTUBE_MAX_DESCRIPTION:
        return description

    description = generate_description_redused(time_labels)
    if len(description) < YOUTUBE_MAX_DESCRIPTION:
        return description

    logging.warn("description cutted")
    return description[:YOUTUBE_MAX_DESCRIPTION]


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

        self.__work_dir = os.getenv("VIDEO_PROCESSOR_WORK_DIR")
        os.makedirs(self.__work_dir, exist_ok=True)
        self.__res_dir = os.getenv("VIDEO_PROCESSOR_RES_DIR")
        os.makedirs(self.__res_dir, exist_ok=True)

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

        resfilename = os.path.join(self.__res_dir, f"{date}.mp4")
        durations = concatenate_to_mp4(fnames, resfilename, self.__work_dir)

        time_labels = []
        for af, duration in zip(afiles, durations):
            time = af.prop().time().strftime("%H: %M: %S")
            caption = af.load_json()["caption"].strip()
            time_labels.append((duration, f"[{time}] {caption}"))

        logging.info(time_labels)

        # TODO: uncomment
        self.upload_video(resfilename, date, time_labels)

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
    log.initLogger(args.logfile, logging.DEBUG)
    logging.getLogger("py.warnings").setLevel(logging.ERROR)

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
