# Multimedia Diary Tools 

![CodeQL](https://github.com/sashacmc/mmdiary/workflows/CodeQL/badge.svg)
[![PyPI - Version](https://img.shields.io/pypi/v/mmdiary.svg)](https://pypi.org/project/mmdiary)
[![PyPI - Downloads](https://pepy.tech/badge/mmdiary)](https://pepy.tech/project/mmdiary)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.commdiarym/psf/black)

Multimedia Diary Tools is a Python toolkit designed to automate the process of managing multimedia content for diary entries. This toolkit offers functionalities to scan specified folders, identify audio and video files, perform speech-to-text transcription, merge video files, and upload the resulting video content to YouTube. Additionally, it integrates with Notion to create a calendar and populate it with transcribed text from audio and video notes, accompanied by links to the original media. A Telegram bot is also provided for easy access to audio notes.

## Installation

You can install MultiMedia Diary Tools via pip:

```bash
pip install mmdiary
```

## Environment Setup

Ensure you set the necessary environment variables:

- `MMDIARY_AUDIO_LIB_ROOT`: Root directory for audio notes.
- `MMDIARY_VIDEO_LIB_ROOTS`: Root directories for video notes (multiple roots can be specified, separated by semicolon).
- `MMDIARY_VIDEO_WORK_DIR`: Work dir for video processing (can be HUGE)
- `MMDIARY_VIDEO_RES_DIR`: Results dir for video diary files
- `MMDIARY_NOTION_API_KEY`: Your Notion API Key (see below).
- `MMDIARY_NOTION_TOKEN`: Your Notion Auth Token v2 (see below).
- `MMDIARY_NOTION_CACHE`: Notion uploader cache file
- `MMDIARY_CACHE`: JSON processing cache file (to avoid reading all transribed files each run)


Example:

```bash
export MMDIARY_AUDIO_LIB_ROOT=/path/to/audio/library
export MMDIARY_VIDEO_LIB_ROOTS=/path/to/video/library1:/path/to/video/library2
export MMDIARY_VIDEO_WORK_DIR=/path/to/work/dir
export MMDIARY_VIDEO_RES_DIR=/path/to/wideo/result/dir
export MMDIARY_NOTION_API_KEY="your_notion_api_key_here"
export MMDIARY_NOTION_TOKEN="your_notion_auth_token_v2_here"
export MMDIARY_NOTION_CACHE=~/.mmdiary/notion_cache.pickle
export MMDIARY_CACHE=~/.mmdiary/json_cache.pickle
```

## Recommended Tools

To ensure unique filenames for your files, it is recommended to use the [photo-importer](https://github.com/sashacmc/photo-importer) tool.

## Notion Setup

To integrate Multimedia Diary Tools with Notion, you'll need to set up both an API Key and an Auth Token v2. This dual setup is necessary because the API Key allows for fast and efficient operations via the official API, while the Auth Token v2 enables functionalities not available through the official API, such as file uploads and locking pages for editing.

### Obtaining and Setting Up the Notion API Key

1. **Create an Integration in Notion**:
   - Go to [Notion Integrations](https://www.notion.so/my-integrations) and click on "New Integration".
   - Follow the instructions to create a new integration and obtain your API Key.

2. **Set the Environment Variable**:
   - Save the API Key in an environment variable named `MMDIARY_NOTION_API_KEY`.
   - Example for Unix-based systems:
     ```bash
     export MMDIARY_NOTION_API_KEY="your_notion_api_key_here"
     ```

### Obtaining and Setting Up the Notion Auth Token v2

1. **Extract the Auth Token v2 from Your Browser**:
   - Open Notion in your web browser and log in.
   - Open the developer tools (usually by pressing `F12` or right-clicking on the page and selecting "Inspect").
   - Go to the "Application" tab and find the `token_v2` under Cookies for `notion.so`.
   - Copy the value of the `token_v2`.

2. **Set the Environment Variable**:
   - Save the Auth Token v2 in an environment variable named `MMDIARY_NOTION_TOKEN`.
   - Example for Unix-based systems:
     ```bash
     export MMDIARY_NOTION_TOKEN="your_notion_auth_token_v2_here"
     ```
     
## Step-By-Step Process Overview

### Audio Diary

#### Speech Recognition

Use the `mmdiary-transcriber-run` utility to perform speech-to-text transcription on audio files.

Command:

```bash
mmdiary-transcriber-run /path/to/audio/files
```

#### Upload to Notion

Use the `mmdiary-notion-upload` utility to upload the transcribed text and audio files to Notion.

Command:
```bash
mmdiary-notion-upload /path/to/audio/files
```

### Video Diary

#### Speech Recognition

Use the `mmdiary-transcriber-run` utility to perform speech-to-text transcription on video files.

Command:

```bash
mmdiary-transcriber-run /path/to/video/files
```

#### Daily Video Concatenation

Use the `mmdiary-video-concat` utility to merge video files into a single daily video.

Command:
```bash
mmdiary-video-concat [dates ...]
```

#### Upload to YouTube

Use the `mmdiary-video-upload` utility to upload the concatenated video to YouTube.

Command:
```bash
mmdiary-video-upload [dates ...]
```

#### Upload to Notion

Use the `mmdiary-notion-upload` utility to upload the transcribed text with YouTube links to Notion.

Command:
```bash
mmdiary-notion-upload "$MMDIARY_VIDEO_RES_DIR"
```

## Contributing

Contributions are welcome! Please feel free to submit issues, feature requests, or pull requests.

## Show your support
Give a ⭐️ if this project helped you!
