"""Khung giờ lưu hành: phép tính thuần trên các khoảng giây trong ngày, không phụ thuộc DB."""

from collections.abc import Iterable

from optimization import Window

DAY_S = 24 * 3600


def parse_time(value: str) -> int:
    hour, minute = value.split(":")
    return int(hour) * 3600 + int(minute) * 60


def merge(windows: Iterable[Window]) -> tuple[Window, ...]:
    out: list[Window] = []
    for start, end in sorted(windows):
        if out and start <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], end))
        else:
            out.append((start, end))
    return tuple(out)


def expand(windows: Iterable[Iterable[str]]) -> tuple[Window, ...]:
    """[["21:00", "06:00"]] → [(0h, 6h), (21h, 24h)]: khoảng qua 0h tách làm 2."""
    out: list[Window] = []
    for pair in windows:
        start, end = (parse_time(v) for v in pair)
        if end > start:
            out.append((start, end))
        else:
            out += [(0, end), (start, DAY_S)]
    return merge(w for w in out if w[0] < w[1])


def intersect(a: tuple[Window, ...], b: tuple[Window, ...]) -> tuple[Window, ...]:
    pairs = ((max(x[0], y[0]), min(x[1], y[1])) for x in a for y in b)
    return merge(w for w in pairs if w[0] < w[1])


def arrival_windows(
    windows: tuple[Window, ...], buffer_s: int, service_s: int
) -> tuple[Window, ...]:
    """Giờ được ĐẾN điểm: chừa thời gian vào vùng và thời gian giao + ra khỏi vùng trước khi hết
    khung. Mốc 0h/24h không cần chừa vì xe vẫn được phép ở đó."""
    out = []
    for start, end in windows:
        first = start + buffer_s if start > 0 else start
        last = end - service_s - buffer_s if end < DAY_S else end
        if first <= last:
            out.append((first, last))
    return tuple(out)


def fmt_time(seconds: int) -> str:
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}"


def fmt_windows(windows: tuple[Window, ...]) -> str:
    """Khoảng qua 0h viết liền: (0h, 6h) + (21h, 24h) → "21:00-06:00"."""
    items = list(windows)
    night = ""
    if len(items) > 1 and items[0][0] == 0 and items[-1][1] == DAY_S:
        night = f"{fmt_time(items[-1][0])}-{fmt_time(items[0][1])}"
        items = items[1:-1]
    return ", ".join(
        [*(f"{fmt_time(a)}-{fmt_time(b)}" for a, b in items), *([night] if night else [])]
    )
