from . import youtube
from . import dailymotion

from .common import *


def generate_video_url(provider, pos=None):
    name = provider["name"]
    if name == youtube.PROVIDER_NAME:
        return youtube.generate_video_url(provider, pos)
    if name == dailymotion.PROVIDER_NAME:
        return dailymotion.generate_video_url(provider, pos)
    raise UserWarning(f"Unknown provider: {name}")
