import progressbar


def start(text, maxval):
    return progressbar.ProgressBar(
        maxval=maxval,
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
