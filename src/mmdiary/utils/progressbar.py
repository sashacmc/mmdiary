import progressbar


def start(text, maxval):
    return progressbar.ProgressBar(
        maxval=maxmal,
        widgets=[
            f"{text}: ",
            progressbar.SimpleProgress(),
            " (",
            progressbar.Percentage(),
            ") ",
            progressbar.Bar(),
            ' ',
            progressbar.ETA(),
        ],
    ).start()
