from __future__ import annotations

import json
from typing import Any, get_args, get_origin, Literal, Union, get_type_hints


class ValidationError(ValueError):
    pass


class FieldInfo:
    def __init__(self, *, min_length: int | None = None) -> None:
        self.min_length = min_length


def Field(*, min_length: int | None = None) -> FieldInfo:
    return FieldInfo(min_length=min_length)


class BaseModel:
    def __init__(self, **data: Any) -> None:
        annotations = get_type_hints(self.__class__)
        for key, anno in annotations.items():
            default = getattr(self.__class__, key, ...)
            if key in data:
                value = data[key]
            elif isinstance(default, FieldInfo):
                raise ValidationError(f"Missing required field: {key}")
            elif default is ...:
                raise ValidationError(f"Missing required field: {key}")
            else:
                value = default
            self._validate_field(key, anno, value, default)
            setattr(self, key, value)

    def _validate_field(self, key: str, anno: Any, value: Any, default: Any) -> None:
        origin = get_origin(anno)
        if origin is Literal:
            allowed = get_args(anno)
            if value not in allowed:
                raise ValidationError(f"{key} not in literal set")
        elif origin in (Union, getattr(__import__('types'), 'UnionType', Union)):
            options = get_args(anno)
            if value is None and type(None) in options:
                return
            if not any(isinstance(value, o) for o in options if o is not type(None)):
                raise ValidationError(f"{key} invalid union value")
        elif anno in (str, int, bool, dict, list) and not isinstance(value, anno):
            raise ValidationError(f"{key} expected {anno}")

        if isinstance(default, FieldInfo) and default.min_length is not None:
            if not isinstance(value, str) or len(value) < default.min_length:
                raise ValidationError(f"{key} shorter than min_length")

    def model_dump(self) -> dict[str, Any]:
        return self.__dict__.copy()

    def model_dump_json(self) -> str:
        return json.dumps(self.model_dump(), sort_keys=True)
