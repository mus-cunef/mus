"""Extensión de Griffe para la documentación: convierte las marcas de reStructuredText de los
docstrings (``:class:`Player```, ``:func:`~musarena.x.y```, dobles comillas invertidas,
``Ejemplo::``) a Markdown, que es lo que entiende MkDocs."""

import re

import griffe

_ROL = re.compile(r":(?:class|func|meth|mod|data|attr|exc|obj|const):`(~?)([^`]+)`")
_DOBLE = re.compile(r"``([^`]+)``")
_LITERAL = re.compile(r"::[ \t]*$", re.MULTILINE)  # sin comerse la línea en blanco siguiente


def convertir(texto: str) -> str:
    def rol(m: re.Match) -> str:
        nombre = m.group(2)
        if "<" in nombre and nombre.endswith(">"):  # :class:`título <ruta>`
            nombre = nombre.split("<")[0].strip()
        elif m.group(1) == "~":
            nombre = nombre.rsplit(".", 1)[-1]
        return f"`{nombre}`"

    texto = _ROL.sub(rol, texto)
    texto = _DOBLE.sub(r"`\1`", texto)
    return _LITERAL.sub(":", texto)


class ConvertirRest(griffe.Extension):
    def on_instance(self, *, obj: griffe.Object, **kwargs: object) -> None:
        if obj.docstring is not None:
            obj.docstring.value = convertir(obj.docstring.value)
