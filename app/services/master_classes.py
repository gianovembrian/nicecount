from __future__ import annotations

from collections import OrderedDict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.constants import DEFAULT_MASTER_CLASSES
from app.models import MasterClass


def get_or_create_master_classes(db: Session) -> list[MasterClass]:
    rows = list(db.scalars(select(MasterClass).order_by(MasterClass.sort_order.asc(), MasterClass.code.asc())))
    row_map = {row.code: row for row in rows}
    created = False

    for code, payload in DEFAULT_MASTER_CLASSES.items():
        row = row_map.get(code)
        if row:
            continue
        row = MasterClass(
            code=code,
            label=payload["label"],
            description=payload["description"],
            sort_order=payload["sort_order"],
        )
        db.add(row)
        created = True

    if created:
        db.commit()

    return list(db.scalars(select(MasterClass).order_by(MasterClass.sort_order.asc(), MasterClass.code.asc())))


def build_master_class_lookup(rows: list[MasterClass]) -> OrderedDict[str, dict]:
    return OrderedDict(
        (
            row.code,
            {
                "label": row.label,
                "description": row.description or "",
                "sort_order": row.sort_order,
            },
        )
        for row in sorted(rows, key=lambda item: (item.sort_order, item.code))
    )
