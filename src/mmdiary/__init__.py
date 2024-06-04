#!/usr/bin/python3
# pylint: disable=line-too-long

import os
import sys
import json
import argparse
import logging
import getpass

from mmdiary.transcriber.transcriber import Transcriber
from mmdiary.notion.uploader import NotionUploader
from mmdiary.video.uploader import youtube, dailymotion
from mmdiary.video.processor import VideoProcessor
from mmdiary.utils import log, medialib


DESCRIPTION = """
Multimedia Diary Tools is a toolkit designed to automate the process
  of managing multimedia content for diary entries.
This toolkit offers functionalities to scan specified folders,
  identify audio and video files, perform speech-to-text transcription, merge video files,
  and upload the resulting video content to YouTube/Dailymotion.
Additionally, it integrates with Notion to create a calendar and populate it with transcribed text
  from audio and video notes, accompanied by links to the original media.
"""

README_URL = "https://github.com/sashacmc/mmdiary?tab=readme-ov-file"


def __ask(question, default_value):
    user_input = input(f"{question} [{default_value}]: ")
    return user_input.strip() or default_value


def __ask_passwd(question):
    return getpass.getpass(f"{question}: ").strip()


def __ask_bool(question, default_value):
    default_value = "y" if default_value else "n"
    while True:
        user_input = input(f"{question} (y/n) [{default_value}]: ").strip().lower()
        if user_input in ["y", "n", ""]:
            return (user_input or default_value) == "y"
        print("Invalid input. Please enter 'y' or 'n'.")


def __init_dir(dir_name):
    full_dir_name = os.path.expanduser(dir_name)
    if not os.path.exists(full_dir_name):
        if __ask_bool(f"Folder '{full_dir_name}' not exists, create?", False):
            os.makedirs(full_dir_name)
    return dir_name


def __init_audio():
    return {"MMDIARY_AUDIO_LIB_ROOT": __init_dir(__ask("Enter audio lib folder", "~/audio"))}


def __init_video():
    return {
        "MMDIARY_VIDEO_LIB_ROOTS": __init_dir(__ask("Enter video lib folder", "~/video")),
        "MMDIARY_VIDEO_WORK_DIR": __init_dir(__ask("Enter video work folder", "~/video/tmp")),
        "MMDIARY_VIDEO_RES_DIR": __init_dir(
            __ask("Enter video result folder", "~/video/converted")
        ),
    }


def __init_youtube(confg_path):
    print(
        "Obtain the YouTube API Client Secrets by following the instructions:",
        README_URL + "#obtaining-and-setting-up-the-youtube-api-client-secrets",
    )

    secrets_file = None
    while True:
        secrets_file = __ask(
            "Enter client_secrets file name", os.path.join(confg_path, "client_secrets.json")
        )
        if os.path.exists(os.path.expanduser(secrets_file)):
            break
        print(f"File {secrets_file} not exists")

    token_file = None
    while True:
        account = __ask("Enter account name (for internal usage only)", "youtube_account")
        token_file = os.path.join(confg_path, account + ".json")

        if not os.path.exists(os.path.expanduser(token_file)):
            break
        if __ask_bool(f"Account token file '{token_file}' already exists, use it?", True):
            break

    env = {
        "MMDIARY_YOUTUBE_CLIENT_SECRETS": secrets_file,
        "MMDIARY_YOUTUBE_TOKEN": token_file,
    }
    os.environ.update(env)
    while True:
        try:
            youtube.VideoUploader()
            break
        except Exception as ex:
            print(ex)
    return env


def __init_dailymotion(confg_path):
    print(
        "Generate an API key by following the instructions:",
        README_URL + "#generating-api-keys",
    )
    env = {}
    while True:
        accounts_file = __ask(
            "Enter accounts file name", os.path.join(confg_path, "dailymotion_accounts.json")
        )
        if not os.path.exists(os.path.expanduser(accounts_file)) or __ask_bool(
            "This file already exists, would you like to overwrite it?", False
        ):
            account = {
                "name": __ask("Enter account/channel name", ""),
                "username": __ask("Enter user name (E-Mail)", ""),
                "password": __ask_passwd("Enter password"),
                "api_key": __ask("Enter API key", ""),
                "api_secret": __ask_passwd("Enter API secret"),
            }
            with open(os.path.expanduser(accounts_file), "w", encoding="utf-8") as f:
                data = {"accounts": [account], "current": 0}
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(
                f"Accounts data saved to: {accounts_file}, you can add other accounts after, if needed"
            )
        env = {
            "MMDIARY_DAILYMOTION_ACCOUNTS": accounts_file,
        }
        os.environ.update(env)

        vup = dailymotion.VideoUploader()
        check_res = vup.check_accounts()
        if len(check_res) != 0 and next(iter((check_res.values()))) is not None:
            break

    return env


def __init_notion(confg_path):
    env = {}
    env["MMDIARY_NOTION_CACHE"] = os.path.join(confg_path, "notion_cache.pickle")
    os.environ.update(env)
    print(
        "Generate an API key and get Auth Token by following the instructions:",
        README_URL + "#notion-setup",
    )

    api_key = os.getenv("MMDIARY_NOTION_API_KEY", "")
    token = os.getenv("MMDIARY_NOTION_TOKEN", "")
    root_page_id = os.getenv("MMDIARY_NOTION_ROOT_PAGE", "")
    while True:
        try:
            api_key = __ask("Enter Notion API key", api_key)
            token = __ask("Enter Notion Auth Token v2", token)

            nup = NotionUploader(token=token, api_key=api_key, audio_db_id=None, video_db_id=None)

            root_page_id = __ask("Enter root page ID", root_page_id)

            audio_db_id, video_db_id = nup.init_databases(root_page_id)
            env["MMDIARY_NOTION_AUDIO_DB_ID"] = audio_db_id
            env["MMDIARY_NOTION_VIDEO_DB_ID"] = video_db_id
            env["MMDIARY_NOTION_TOKEN"] = token
            env["MMDIARY_NOTION_API_KEY"] = api_key
            break
        except Exception as ex:
            print(ex)
    return env


def __update_env(env, newvars):
    env.update(newvars)
    os.environ.update(newvars)


def __init():
    env = {}
    confg_path = __ask("Enter main configuration folder", "~/.mmdiary")
    os.makedirs(os.path.expanduser(confg_path), exist_ok=True)
    env["MMDIARY_CACHE"] = os.path.join(confg_path, "json_cache.pickle")

    if __ask_bool("Will you process audio library", True):
        __update_env(env, __init_audio())

    if __ask_bool("Will you process video library", True):
        __update_env(env, __init_video())

        if __ask_bool("Will you upload video on YouTube", True):
            __update_env(env, __init_youtube(confg_path))
        if __ask_bool("Will you upload video on Dailymotion", True):
            __update_env(env, __init_dailymotion(confg_path))

    if __ask_bool("Will you upload notes on Notion", True):
        __update_env(env, __init_notion(confg_path))

    print("\nPlease add this lines to you environment file (e.g. ~/.bashrc):\n")
    for var, value in env.items():
        print(f'export {var}="{value}"')


def __run_transcriber(inpath):
    lib = medialib.MediaLib(inpath)
    fileslist = lib.get_new()
    if len(fileslist) == 0:
        logging.info("Nothing to transcribe in folder %s", inpath)
        return

    tr = Transcriber(
        os.getenv("MMDIARY_TRANSCRIBE_MODEL", "medium"),
        os.getenv("MMDIARY_TRANSCRIBE_LANGUAGE", "ru"),
    )
    tr.process_list(fileslist)


def __run_video_processor():
    vp = VideoProcessor()
    vp.process_all(None)


def __run_youtube_uploader():
    vup = youtube.VideoUploader()
    res_count, err_count = vup.process_all(None)
    logging.info("Youtube uploader done: %s, errors: %s", res_count, err_count)


def __run_dailymotion_uploader():
    vup = dailymotion.VideoUploader()
    res_count, err_count = vup.process_all(None)
    logging.info("Dailymotion uploader done: %s, errors: %s", res_count, err_count)


def __run_notion_uploader(inpath):
    lib = medialib.MediaLib(inpath)
    fileslist = lib.get_processed(should_have_file=False)

    if len(fileslist) == 0:
        logging.info("Nothing to upload at Notion in folder %s", inpath)
        return

    nup = NotionUploader(
        token=os.getenv("MMDIARY_NOTION_TOKEN"),
        api_key=os.getenv("MMDIARY_NOTION_API_KEY"),
        audio_db_id=os.getenv("MMDIARY_NOTION_AUDIO_DB_ID"),
        video_db_id=os.getenv("MMDIARY_NOTION_VIDEO_DB_ID"),
        force_update=False,
        dry_run=False,
    )
    nup.process_list(fileslist)


def __run_audio_batch(args):
    audio_root = os.environ["MMDIARY_AUDIO_LIB_ROOT"]
    __run_transcriber(audio_root)
    if args.notion:
        __run_notion_uploader(audio_root)


def __run_video_batch(args):
    video_roots = list(
        filter(
            None,
            os.environ["MMDIARY_VIDEO_LIB_ROOTS"].split(":"),
        ),
    )
    for video_root in video_roots:
        __run_transcriber(video_root)

    __run_video_processor()

    if args.youtube:
        __run_youtube_uploader()
    if args.dailymotion:
        __run_dailymotion_uploader()

    if args.notion:
        __run_notion_uploader(os.environ["MMDIARY_VIDEO_RES_DIR"])


def __run_batch(args):
    if not args.audio and not args.video:
        print("error: --video or --audio should be specified")
        sys.exit(1)

    if args.audio:
        __run_audio_batch(args)

    if args.video:
        __run_video_batch(args)


def __args_parse():
    parser = argparse.ArgumentParser(
        description=DESCRIPTION, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("-l", "--logfile", help="Log file", default="/dev/null")

    parser.add_argument("--init", help="Run interactive setup", action="store_true")

    parser.add_argument("--video", help="Proces video diary entries", action="store_true")
    parser.add_argument("--audio", help="Proces audio diary entries", action="store_true")

    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--youtube", help="Upload video diary entries to youtube", action="store_true"
    )
    group.add_argument(
        "--dailymotion", help="Upload video diary entries to dailymotion", action="store_true"
    )

    parser.add_argument("--notion", help="Upload to notion", action="store_true")

    return parser.parse_args()


def main():
    args = __args_parse()

    log.init_logger(args.logfile, level=logging.DEBUG)

    if args.init:
        __init()
        return

    __run_batch(args)


if __name__ == "__main__":
    main()
