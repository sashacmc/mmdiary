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

## Command line tool usage

### Transcribe files
```bash
mmdiary-transcriber-run /path/to/folder/with/media/files
```
### Upload to notion
```bash
mmdiary-notion-upload /path/to/folder/with/media/files
```
### Concat video files
```bash
mmdiary-video-concat
```
### Upload to notion
```bash
mmdiary-video-upload
```

## Contributing

Contributions are welcome! Please feel free to submit issues, feature requests, or pull requests.

## Show your support
Give a ⭐️ if this project helped you!
