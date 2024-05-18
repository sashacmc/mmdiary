import pytest

from mmdiary.transcriber.verifier import check_text, remove_duplicate_lines


@pytest.mark.parametrize(
    "par,expected",
    [
        ("Some english", ""),
        ("Что-то на кириллице", "Что-то на кириллице"),
        #
        ("Редактор субтитров", ""),
        ("Реактор субтитров", ""),
        ("Субтитры субтитров", ""),
        ("Спасибо за субтитры", ""),
        ("Субтитры подготовлены", ""),
        ("Субтитры делал", ""),
        ("Субтитры сделаны", ""),
        #
        ("Подписывайтесь на канал", ""),
        ("Подписывайтесь на мой канал", ""),
        ("Подписывайтесь на наш канал", ""),
        ("Подписывайтесь на этот канал", ""),
        ("подписывайтесь на канал", ""),
        #
        ("Добро пожаловать в наш канал", ""),
        ("Добро пожаловать на наш канал", ""),
        ("добро пожаловать на мой канал", ""),
        ("Добро пожаловать на канал", ""),
        #
        ("Всем спасибо за внимание", ""),
        ("Большое спасибо за внимание!", ""),
        ("Спасибо за внимание!", ""),
    ],
)
def test_hall_match(par, expected):
    assert check_text(par, "ru") == expected


@pytest.mark.parametrize(
    "par,expected",
    [
        ([], []),
        (["line1"], ["line1"]),
        (["line1", "line2", "line3"], ["line1", "line2", "line3"]),
        (["line1", "line2", "line2"], ["line1", "line2", "line2"]),
        (["line1", "line1", "line1"], ["line1", "line1"]),
        (
            ["line1", "line2", "line3", "line3", "line3", "line3", "line3", "line1", "line2"],
            ["line1", "line2", "line3", "line3", "line1", "line2"],
        ),
    ],
)
def test_remove_duplicate_lines(par, expected):
    assert remove_duplicate_lines(par) == expected
