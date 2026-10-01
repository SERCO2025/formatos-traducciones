# -*- coding: utf-8 -*-
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class Color:
    r: int = 0
    g: int = 0
    b: int = 0

    def to_dict(self):
        return {"r": self.r, "g": self.g, "b": self.b}

    @classmethod
    def from_dict(cls, data):
        return cls(
            r=int(data.get("r", 0)),
            g=int(data.get("g", 0)),
            b=int(data.get("b", 0)),
        )


@dataclass
class Position:
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0

    def to_dict(self):
        return {
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            x=int(data.get("x", 0)),
            y=int(data.get("y", 0)),
            width=int(data.get("width", 0)),
            height=int(data.get("height", 0)),
        )


@dataclass
class Validation:
    numeric_only: bool = False

    def to_dict(self):
        return {"numeric_only": self.numeric_only}

    @classmethod
    def from_dict(cls, data):
        return cls(numeric_only=bool(data.get("numeric_only", False)))


@dataclass
class TextStyle:
    font_family: str = ""
    font_size_px: int = 24
    color: Color = field(default_factory=Color)
    orientation: str = "horizontal"
    alignment: str = "left"

    def to_dict(self):
        return {
            "font_family": self.font_family,
            "font_size_px": self.font_size_px,
            "color": self.color.to_dict(),
            "orientation": self.orientation,
            "alignment": self.alignment,
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            font_family=str(data.get("font_family", "")),
            font_size_px=int(data.get("font_size_px", 24)),
            color=Color.from_dict(data.get("color", {})),
            orientation=str(data.get("orientation", "horizontal")),
            alignment=str(data.get("alignment", "left")),
        )


@dataclass
class Field:
    field_id: str
    question: str
    field_type: str = "text"
    required: bool = False
    validation: Validation = field(default_factory=Validation)
    position: Position = field(default_factory=Position)
    text_style: TextStyle = field(default_factory=TextStyle)
    text: str = ""

    def to_dict(self):
        return {
            "field_id": self.field_id,
            "question": self.question,
            "field_type": self.field_type,
            "required": self.required,
            "validation": self.validation.to_dict(),
            "position": self.position.to_dict(),
            "text_style": self.text_style.to_dict(),
            "text": self.text,
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            field_id=str(data.get("field_id", "")),
            question=str(data.get("question", "")),
            field_type=str(data.get("field_type", "text")),
            required=bool(data.get("required", False)),
            validation=Validation.from_dict(data.get("validation", {})),
            position=Position.from_dict(data.get("position", {})),
            text_style=TextStyle.from_dict(data.get("text_style", {})),
            text=str(data.get("text", "")),
        )


@dataclass
class TemplateInfo:
    path: str
    width: int
    height: int
    dpi: int = 300
    mode: str = "RGB"

    def to_dict(self):
        return {
            "path": self.path,
            "width": self.width,
            "height": self.height,
            "dpi": self.dpi,
            "mode": self.mode,
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            path=str(data.get("path", "")),
            width=int(data.get("width", 0)),
            height=int(data.get("height", 0)),
            dpi=int(data.get("dpi", 300)),
            mode=str(data.get("mode", "RGB")),
        )


@dataclass
class Formato:
    name: str
    template: TemplateInfo
    fields: List[Field] = field(default_factory=list)
    version: int = 1

    def to_dict(self):
        return {
            "version": self.version,
            "name": self.name,
            "template": self.template.to_dict(),
            "fields": [item.to_dict() for item in self.fields],
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            version=int(data.get("version", 1)),
            name=str(data.get("name", "")),
            template=TemplateInfo.from_dict(data.get("template", {})),
            fields=[Field.from_dict(item) for item in data.get("fields", [])],
        )
