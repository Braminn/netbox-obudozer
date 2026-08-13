"""
Разбор графика работы арендатора из текстового custom field `work_time`.

Формат значения (текст, заполняется вручную):

    ПН-ПТ: 9:00-20:00
    ПН-ЧТ: 8:30-17:30, ПТ: 8:30-16:30

То есть один или несколько интервалов через запятую, каждый — «дни: время».
Дни задаются либо диапазоном (`ПН-ПТ`), либо одним днём (`ПТ`).

Модуль ничего не знает про NetBox — только текст на входе и bool/структуры
на выходе. Используется в rutoken.py для отсева контактов вне рабочего времени.
"""
import logging
import re
from datetime import time
from typing import List, NamedTuple, Optional, Set

from django.utils import timezone

logger = logging.getLogger('netbox.plugins.netbox_obudozer.work_time')

# Русские сокращения дней недели → индекс как в datetime.weekday() (ПН=0 … ВС=6)
DAY_NAMES = {
    'ПН': 0,
    'ВТ': 1,
    'СР': 2,
    'ЧТ': 3,
    'ПТ': 4,
    'СБ': 5,
    'ВС': 6,
}

# Один интервал: «дни: время-время».
# Ищем регуляркой по всей строке, а не режем по запятой — так не важно,
# чем именно разделены интервалы и есть ли вокруг лишний текст/пробелы.
# Разделителем диапазона может быть как дефис, так и любое тире.
_INTERVAL_RE = re.compile(
    r'(?P<day_from>[А-ЯЁ]{2})\s*(?:[-–—]\s*(?P<day_to>[А-ЯЁ]{2}))?\s*:\s*'
    r'(?P<from_h>\d{1,2})[:.](?P<from_m>\d{2})\s*[-–—]\s*'
    r'(?P<to_h>\d{1,2})[:.](?P<to_m>\d{2})',
    re.IGNORECASE,
)


class WorkInterval(NamedTuple):
    """Рабочий интервал: набор дней недели + время начала и окончания."""
    days: Set[int]
    start: time
    end: time


def _expand_days(day_from: str, day_to: Optional[str]) -> Set[int]:
    """
    Дни недели из «ПН-ПТ» / «ПТ».

    Диапазон разворачивается по кругу, поэтому «СБ-ВТ» — это СБ, ВС, ПН, ВТ.
    Неизвестное сокращение → пустой набор.
    """
    start = DAY_NAMES.get(day_from.upper())
    if start is None:
        return set()

    if not day_to:
        return {start}

    end = DAY_NAMES.get(day_to.upper())
    if end is None:
        return set()

    days = set()
    current = start
    while True:
        days.add(current)
        if current == end:
            break
        current = (current + 1) % 7
    return days


def parse_work_time(value: str) -> List[WorkInterval]:
    """
    Разбирает значение custom field `work_time` в список интервалов.

    Нераспознанные куски строки молча игнорируются — на выдачу влияет только
    то, что удалось разобрать. Если не разобрано вообще ничего, а текст был,
    пишем warning: скорее всего, у арендатора опечатка в формате.

    :return: список WorkInterval; пустой, если разобрать нечего
    """
    if not value or not value.strip():
        return []

    intervals = []
    for match in _INTERVAL_RE.finditer(value):
        days = _expand_days(match.group('day_from'), match.group('day_to'))
        if not days:
            continue

        try:
            start = time(int(match.group('from_h')), int(match.group('from_m')))
            end = time(int(match.group('to_h')), int(match.group('to_m')))
        except ValueError:
            # Часы > 23 или минуты > 59
            continue

        intervals.append(WorkInterval(days=days, start=start, end=end))

    if not intervals:
        logger.warning("Не удалось разобрать график работы: %r", value)

    return intervals


def is_working_now(value: str, now=None) -> bool:
    """
    Попадает ли текущий момент в график работы.

    Время берётся локальное — по TIME_ZONE из настроек NetBox, а не UTC.

    Интервал, у которого время окончания меньше или равно времени начала,
    считается переходящим через полночь: «ПН: 22:00-06:00» — это вечер
    понедельника И ночь со понедельника на вторник (до 6 утра вторника),
    а «ПН-ВС: 00:00-00:00» — круглосуточно.

    Граница открытия включается, граница закрытия — нет: при графике
    9:00-20:00 в 9:00:00 уже открыто, в 20:00:00 уже закрыто.

    :param value: значение custom field work_time
    :param now: момент для проверки (по умолчанию — сейчас); удобно для отладки
    :return: True, если сейчас рабочее время
    """
    intervals = parse_work_time(value)
    if not intervals:
        return False

    now = now or timezone.localtime()
    weekday = now.weekday()
    current = now.time()

    for interval in intervals:
        if interval.start < interval.end:
            if weekday in interval.days and interval.start <= current < interval.end:
                return True
            continue

        # Переход через полночь (или круглосуточно при start == end):
        # вечерняя часть относится к своему дню, утренняя — к следующему
        if weekday in interval.days and current >= interval.start:
            return True
        if (weekday - 1) % 7 in interval.days and current < interval.end:
            return True

    return False
