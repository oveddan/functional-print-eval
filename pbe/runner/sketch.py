"""A sketch the agent sends with a measure call in a live session: an SVG drawing with numbered dimensions, so the
person can answer by number and both mean the same dimension.

Only live sessions offer it (pbe/runner/live.py). The eval's scripted conditions keep measure as it was.

The drawing comes from a model and is opened in the person's browser, so it's checked before it's saved: it has
to parse as SVG, stay under a size cap, and use only drawing elements and attributes. Scripts, styles, images,
links, event handlers and anything that loads a file or a URL are refused, not stripped, and the model is told
which one, so nothing in a sketch ever runs. What's saved and opened is the drawing written out again from the
checked elements, not the text the model sent. Every numbered dimension has to appear as a label in the drawing.
"""
import re
from pathlib import Path
from xml.etree import ElementTree

from pydantic import BaseModel, ConfigDict, Field, ValidationError

MAX_CHARS = 50_000
SVG_NS = "http://www.w3.org/2000/svg"
ELEMENTS = {"svg", "g", "defs", "marker", "title", "desc", "line", "rect", "circle", "ellipse", "polyline", "polygon",
            "path", "text", "tspan"}
ATTRIBUTES = {
    "x", "y", "x1", "y1", "x2", "y2", "cx", "cy", "r", "rx", "ry", "dx", "dy", "width", "height", "d", "points",
    "viewBox", "preserveAspectRatio", "transform", "id", "class", "version",
    "fill", "fill-opacity", "fill-rule", "stroke", "stroke-width", "stroke-dasharray", "stroke-linecap", "stroke-linejoin",
    "stroke-opacity", "opacity", "font-size", "font-family", "font-weight", "font-style", "text-anchor", "dominant-baseline",
    "marker-start", "marker-mid", "marker-end", "markerWidth", "markerHeight", "markerUnits", "refX", "refY", "orient",
}
MARKERS = {"marker-start", "marker-mid", "marker-end"}
OWN_MARKER = re.compile(r"url\(#[\w.-]+\)")  # a marker drawn in the same sketch; the only reference allowed
XML_DECLARATION = re.compile(r"^\s*<\?xml\s[^>]*\?>")  # the one <?...?> a drawing may open with
LOADS_SOMETHING = re.compile(r"url\s*\(|javascript:|data:|https?:|file:|expression\s*\(|@import", re.I)
# the tool's parameter, as live sessions offer it
SCHEMA = {
    "type": "object",
    "description": ("Optional. A drawing of the thing with each dimension you want numbered on it, so the person can "
                    "answer by number and you both mean the same dimension."),
    "properties": {
        "svg": {"type": "string", "description": (
            f"A complete <svg> drawing, at most {MAX_CHARS} characters. Lines, shapes, paths and text only: no scripts, "
            "styles, images or links. Label each dimension with its number.")},
        "dimensions": {"type": "array", "description": "What each number in the drawing asks for", "items": {
            "type": "object",
            "properties": {"number": {"type": "integer", "description": "The number as labelled in the drawing"},
                           "what": {"type": "string", "description": "What to measure there, e.g. 'the hole's diameter'"}},
            "required": ["number", "what"]}},
    },
    "required": ["svg", "dimensions"],
}


class Dimension(BaseModel):
    model_config = ConfigDict(extra="forbid")
    number: int
    what: str = Field(min_length=1)


class Sketch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    svg: str
    dimensions: list[Dimension] = Field(min_length=1)


class BadSketch(ValueError):
    """A sketch that isn't shown or saved. The message says why, in words for the model."""


def _local(name: str) -> str:
    """An element's or attribute's name without its namespace."""
    return name.rsplit("}", 1)[-1]


def _namespace(name: str) -> str:
    return name[1:].split("}", 1)[0] if name.startswith("{") else ""


def _check_attribute(element, name, value):
    local = _local(name)
    if _namespace(name) or local not in ATTRIBUTES:
        raise BadSketch(f"the attribute {local} on <{_local(element.tag)}> isn't allowed in a sketch")
    if local in MARKERS and OWN_MARKER.fullmatch(value.strip()):
        return
    if LOADS_SOMETHING.search(value):
        raise BadSketch(f"the attribute {local} on <{_local(element.tag)}> points at something outside the drawing")


def _check_element(element):
    if _namespace(element.tag) != SVG_NS or _local(element.tag) not in ELEMENTS:
        raise BadSketch(f"<{_local(element.tag)}> isn't allowed in a sketch: use lines, shapes, paths and text")
    for name, value in element.attrib.items():
        _check_attribute(element, name, value)


def _parsed(svg: str):
    if len(svg) > MAX_CHARS:
        raise BadSketch(f"it's {len(svg)} characters, and a sketch can be at most {MAX_CHARS}")
    if "<!" in svg.replace("<!--", ""):  # a DOCTYPE or ENTITY: entities can expand without limit or read files
        raise BadSketch("it has a DOCTYPE or entity declaration, which a sketch can't have")
    if "<?" in XML_DECLARATION.sub("", svg, count=1):  # e.g. xml-stylesheet, which makes a browser load a URL
        raise BadSketch("it has a processing instruction (<?...?>), which a sketch can't have")
    try:
        root = ElementTree.fromstring(svg)
    except ElementTree.ParseError as e:
        raise BadSketch(f"it doesn't parse as SVG ({e})") from None
    if root.tag != f"{{{SVG_NS}}}svg":
        raise BadSketch(f'it has to be one <svg xmlns="{SVG_NS}"> element')
    return root


def _labels(root) -> set[str]:
    """Every number written in the drawing's text."""
    text = " ".join("".join(element.itertext()) for element in root.iter() if _local(element.tag) == "text")
    return set(re.findall(r"\d+", text))


def _check_dimensions(sketch: Sketch, root):
    numbers = [dimension.number for dimension in sketch.dimensions]
    if len(set(numbers)) != len(numbers):
        raise BadSketch("two dimensions have the same number")
    unlabelled = [str(number) for number in numbers if str(number) not in _labels(root)]
    if unlabelled:
        raise BadSketch(f"dimension {', '.join(unlabelled)} isn't labelled with its number in the drawing's text")


def checked(arguments) -> Sketch:
    """The sketch a measure call sent, or BadSketch saying why it can't be shown."""
    try:
        sketch = Sketch.model_validate(arguments)
    except ValidationError as e:
        problems = "; ".join(f"{'.'.join(map(str, error['loc']))}: {error['msg']}" for error in e.errors())
        raise BadSketch(f"it needs `svg` and at least one of `dimensions`, each with a number and what to measure ({problems})") from None
    root = _parsed(sketch.svg)
    for element in root.iter():
        _check_element(element)
    _check_dimensions(sketch, root)
    return sketch.model_copy(update={"svg": _as_checked(root)})


def _as_checked(root) -> str:
    """The drawing written out again from the elements that were checked, so the file the browser opens holds
    nothing the check didn't read: the parser drops comments and anything outside the elements."""
    ElementTree.register_namespace("", SVG_NS)
    return ElementTree.tostring(root, encoding="unicode")


def sent_back(error: BadSketch) -> str:
    """What the model is told about a sketch that was refused."""
    return f"I couldn't open your sketch: {error}. Call measure again with a fixed sketch, or without one."


def save(sketch: Sketch, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(sketch.svg)
    return path
