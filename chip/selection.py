"""Parse the user's PR pick ("1,3", "2-4", "all", "shopbox-api#274") into 1-based row indexes."""
from __future__ import annotations

from typing import List, Sequence

from chip.menu import SKIP


class SelectionError(ValueError):
    pass


def parse_selection(text: str, count: int, labels: Sequence[str] = ()) -> List[int]:
    by_label = {label.lower(): i for i, label in enumerate(labels, 1)}
    skip = "".join(SKIP.split()).lower()
    cleaned = "".join(text.split()).lower()
    if not cleaned:
        raise SelectionError("chưa chọn PR nào")
    if cleaned == "all":
        if count == 0:
            raise SelectionError("danh sách trống")
        return list(range(1, count + 1))

    picked = set()
    for token in filter(None, cleaned.split(",")):
        if token == skip:
            continue
        if "#" in token:
            if token not in by_label:
                raise SelectionError(f"'{token}' không có trong danh sách")
            values = [by_label[token]]
        elif "-" in token:
            lo, _, hi = token.partition("-")
            if not (lo.isdigit() and hi.isdigit()) or int(lo) > int(hi):
                raise SelectionError(f"'{token}' không hợp lệ")
            values = range(int(lo), int(hi) + 1)
        elif token.isdigit():
            values = [int(token)]
        else:
            raise SelectionError(f"'{token}' không hợp lệ")
        for value in values:
            if not 1 <= value <= count:
                raise SelectionError(f"'{token}' ngoài khoảng 1-{count}")
            picked.add(value)
    if not picked:
        raise SelectionError("chưa chọn PR nào")
    return sorted(picked)
