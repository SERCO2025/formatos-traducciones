# -*- coding: utf-8 -*-
from dataclasses import dataclass, field
from typing import List


FIELD_TYPE_TEXT = "text"
FIELD_TYPE_NUMBER = "number"
FIELD_TYPE_ALPHANUMERIC = "alphanumeric"
FIELD_TYPE_IMAGE = "image"

FIELD_TYPES = (
    FIELD_TYPE_TEXT,
    FIELD_TYPE_NUMBER,
    FIELD_TYPE_ALPHANUMERIC,
    FIELD_TYPE_IMAGE,
)


@dataclass
class Color:
    r: int = 0
    g: int = 0
    b: int = 0

    def to_dict(self):
        return {"r": self.r, "g": self.g, "b": self.b}

    @classmethod
    def from_dict(cls, data):
        data = data or {}
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
        data = data or {}
        return cls(
            x=int(data.get("x", 0)),
            y=int(data.get("y", 0)),
            width=int(data.get("width", 0)),
            height=int(data.get("height", 0)),
        )


@dataclass
class Validation:
    numeric_only: bool = False
    alphanumeric_only: bool = False

    def to_dict(self):
        return {
            "numeric_only": self.numeric_only,
            "alphanumeric_only": self.alphanumeric_only,
        }

    @classmethod
    def from_dict(cls, data):
        data = data or {}
        return cls(
            numeric_only=bool(data.get("numeric_only", False)),
            alphanumeric_only=bool(data.get("alphanumeric_only", False)),
        )


@dataclass
class TextStyle:
    font_family: str = ""
    font_size_px: int = 24
    color: Color = field(default_factory=Color)
    orientation: str = "horizontal"
    alignment: str = "left"
    bold: bool = False
    italic: bool = False

    def to_dict(self):
        return {
            "font_family": self.font_family,
            "font_size_px": self.font_size_px,
            "color": self.color.to_dict(),
            "orientation": self.orientation,
            "alignment": self.alignment,
            "bold": self.bold,
            "italic": self.italic,
        }

    @classmethod
    def from_dict(cls, data):
        data = data or {}
        return cls(
            font_family=str(data.get("font_family", "")),
            font_size_px=int(data.get("font_size_px", 24)),
            color=Color.from_dict(data.get("color", {})),
            orientation=str(data.get("orientation", "horizontal")),
            alignment=str(data.get("alignment", "left")),
            bold=bool(data.get("bold", False)),
            italic=bool(data.get("italic", False)),
        )


@dataclass
class Field:
    field_id: str
    question: str
    field_type: str = FIELD_TYPE_TEXT
    order: int = 0
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
            "order": self.order,
            "required": self.required,
            "validation": self.validation.to_dict(),
            "position": self.position.to_dict(),
            "text_style": self.text_style.to_dict(),
            "text": self.text,
        }

    @classmethod
    def from_dict(cls, data):
        data = data or {}
        return cls(
            field_id=str(data.get("field_id", "")),
            question=str(data.get("question", "")),
            field_type=str(data.get("field_type", FIELD_TYPE_TEXT)),
            order=int(data.get("order", 0)),
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
        data = data or {}
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
    version: int = 2

    def ordenar_campos(self):
        # FDT v1 no tenia "order"; en ese caso se conserva el orden
        # original de la lista y se le asigna numeracion nueva.
        if self.fields and all(item.order <= 0 for item in self.fields):
            for numero, campo in enumerate(self.fields, start=1):
                campo.order = numero
            return

        self.fields.sort(
            key=lambda item: item.order if item.order > 0 else 10**9
        )

        for numero, campo in enumerate(self.fields, start=1):
            campo.order = numero

    def agregar_campo(self, campo):
        campo.order = len(self.fields) + 1
        self.fields.append(campo)

    def to_dict(self):
        self.ordenar_campos()
        return {
            "version": self.version,
            "name": self.name,
            "template": self.template.to_dict(),
            "fields": [item.to_dict() for item in self.fields],
        }

    @classmethod
    def from_dict(cls, data):
        data = data or {}
        formato = cls(
            version=int(data.get("version", 1)),
            name=str(data.get("name", "")),
            template=TemplateInfo.from_dict(data.get("template", {})),
            fields=[Field.from_dict(item) for item in data.get("fields", [])],
        )
        formato.ordenar_campos()
        return formato
