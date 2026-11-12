import struct
from math import isfinite
from pathlib import PurePath
from re import fullmatch

import nh3
from django.core.exceptions import ValidationError
from lxml import etree

MAX_BRAND_IMAGE_BYTES = 512 * 1024
MAX_BRAND_IMAGE_WIDTH = 2400
MAX_BRAND_IMAGE_HEIGHT = 1200
SVG_NAMESPACE = "http://www.w3.org/2000/svg"
SVG_ALLOWED_TAGS = {
    "circle",
    "clipPath",
    "defs",
    "desc",
    "ellipse",
    "g",
    "line",
    "linearGradient",
    "mask",
    "path",
    "polygon",
    "polyline",
    "radialGradient",
    "rect",
    "stop",
    "svg",
    "text",
    "title",
    "tspan",
}
SVG_ALLOWED_ATTRIBUTES = {
    "*": {
        "aria-hidden",
        "aria-label",
        "fill",
        "fill-opacity",
        "id",
        "opacity",
        "role",
        "stroke",
        "stroke-dasharray",
        "stroke-linecap",
        "stroke-linejoin",
        "stroke-opacity",
        "stroke-width",
        "transform",
    },
    "svg": {"height", "preserveAspectRatio", "viewBox", "width", "xmlns"},
    "circle": {"cx", "cy", "r"},
    "ellipse": {"cx", "cy", "rx", "ry"},
    "line": {"x1", "x2", "y1", "y2"},
    "linearGradient": {"gradientTransform", "gradientUnits", "x1", "x2", "y1", "y2"},
    "path": {"d", "pathLength"},
    "polygon": {"points"},
    "polyline": {"points"},
    "radialGradient": {"cx", "cy", "fx", "fy", "gradientTransform", "r"},
    "rect": {"height", "rx", "ry", "width", "x", "y"},
    "stop": {"offset", "stop-color", "stop-opacity"},
    "text": {"dx", "dy", "font-family", "font-size", "font-weight", "text-anchor", "x", "y"},
    "tspan": {"dx", "dy", "x", "y"},
}


def _filter_svg_attribute(attribute: str, value: str) -> str | None:
    lowered_name = attribute.casefold()
    lowered_value = value.casefold().replace("\x00", "")
    if lowered_name.startswith("on"):
        return None
    if any(
        token in lowered_value
        for token in ("javascript:", "data:", "url(", "http:", "https:", "//")
    ):
        return None
    return value


SVG_CLEANER = nh3.Cleaner(
    tags=SVG_ALLOWED_TAGS,
    clean_content_tags={
        "a",
        "animate",
        "animateMotion",
        "animateTransform",
        "foreignObject",
        "iframe",
        "image",
        "object",
        "script",
        "set",
        "style",
        "use",
    },
    attributes=SVG_ALLOWED_ATTRIBUTES,
    attribute_filter=lambda _tag, attribute, value: _filter_svg_attribute(attribute, value),
    url_schemes=set(),
    url_relative="deny",
    link_rel=None,
)


def _png_dimensions(data: bytes) -> tuple[int, int] | None:
    if len(data) >= 24 and data.startswith(b"\x89PNG\r\n\x1a\n") and data[12:16] == b"IHDR":
        return struct.unpack(">II", data[16:24])
    return None


def _jpeg_dimensions(data: bytes) -> tuple[int, int] | None:
    if not data.startswith(b"\xff\xd8"):
        return None
    offset = 2
    sof_markers = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
    while offset + 4 <= len(data):
        if data[offset] != 0xFF:
            offset += 1
            continue
        marker = data[offset + 1]
        offset += 2
        if marker in {0xD8, 0xD9}:
            continue
        if offset + 2 > len(data):
            return None
        length = int.from_bytes(data[offset : offset + 2], "big")
        if length < 2 or offset + length > len(data):
            return None
        if marker in sof_markers and length >= 7:
            height = int.from_bytes(data[offset + 3 : offset + 5], "big")
            width = int.from_bytes(data[offset + 5 : offset + 7], "big")
            return width, height
        offset += length
    return None


def _webp_dimensions(data: bytes) -> tuple[int, int] | None:
    if len(data) < 30 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        return None
    chunk = data[12:16]
    if chunk == b"VP8X" and len(data) >= 30:
        return int.from_bytes(data[24:27], "little") + 1, int.from_bytes(data[27:30], "little") + 1
    if chunk == b"VP8L" and len(data) >= 25 and data[20] == 0x2F:
        bits = int.from_bytes(data[21:25], "little")
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    if chunk == b"VP8 " and len(data) >= 30 and data[23:26] == b"\x9d\x01\x2a":
        return int.from_bytes(data[26:28], "little") & 0x3FFF, int.from_bytes(
            data[28:30], "little"
        ) & 0x3FFF
    return None


def _parse_svg_length(value: str | None) -> float | None:
    if not value:
        return None
    match = fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(?:px)?\s*", value)
    return float(match.group(1)) if match else None


def _svg_dimensions(root) -> tuple[float, float] | None:
    width = _parse_svg_length(root.get("width"))
    height = _parse_svg_length(root.get("height"))
    if width is not None and height is not None:
        return width, height
    view_box = root.get("viewBox")
    if view_box:
        try:
            _x, _y, view_width, view_height = [
                float(item) for item in view_box.replace(",", " ").split()
            ]
        except (TypeError, ValueError):
            return None
        if isfinite(view_width) and isfinite(view_height):
            return view_width, view_height
    return None


def _parse_svg(data: bytes, *, allow_missing_namespace: bool = False):
    lowered = data.lower()
    if b"<!doctype" in lowered or b"<!entity" in lowered:
        raise ValidationError("El SVG no puede declarar DTD ni entidades")
    parser = etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        recover=False,
        remove_comments=True,
        remove_pis=True,
        huge_tree=False,
    )
    try:
        root = etree.fromstring(data, parser=parser)
    except (etree.XMLSyntaxError, ValueError) as exc:
        raise ValidationError("El archivo no es un SVG válido") from exc
    name = etree.QName(root)
    allowed_namespaces = {SVG_NAMESPACE, None} if allow_missing_namespace else {SVG_NAMESPACE}
    if name.localname != "svg" or name.namespace not in allowed_namespaces:
        raise ValidationError("El archivo debe tener una raíz SVG con namespace estándar")
    return root


def _sanitize_svg(data: bytes) -> tuple[bytes, tuple[float, float]]:
    _parse_svg(data)
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValidationError("El SVG debe usar codificación UTF-8") from exc
    sanitized = SVG_CLEANER.clean(text).encode("utf-8")
    root = _parse_svg(sanitized, allow_missing_namespace=True)

    def copy_with_namespace(element, *, root_element=False):
        copied = etree.Element(
            f"{{{SVG_NAMESPACE}}}{etree.QName(element).localname}",
            nsmap={None: SVG_NAMESPACE} if root_element else None,
        )
        for attribute, value in element.attrib.items():
            copied.set(etree.QName(attribute).localname, value)
        copied.text = element.text
        copied.tail = element.tail
        for child in element:
            copied.append(copy_with_namespace(child))
        return copied

    root = copy_with_namespace(root, root_element=True)
    sanitized = etree.tostring(root, encoding="utf-8")
    root = _parse_svg(sanitized)
    dimensions = _svg_dimensions(root)
    if dimensions is None:
        raise ValidationError("El SVG debe declarar width/height en px o un viewBox válido")
    return sanitized, dimensions


def _replace_upload_content(uploaded, content: bytes) -> None:
    try:
        uploaded.seek(0)
        uploaded.write(content)
        uploaded.truncate()
        uploaded.seek(0)
    except (AttributeError, OSError, TypeError) as exc:
        raise ValidationError("No fue posible almacenar el SVG saneado") from exc
    if hasattr(uploaded, "size"):
        try:
            uploaded.size = len(content)
        except AttributeError:
            if hasattr(uploaded, "file") and hasattr(uploaded.file, "size"):
                uploaded.file.size = len(content)
    if hasattr(uploaded, "content_type"):
        uploaded.content_type = "image/svg+xml"


def validate_brand_image(uploaded) -> None:
    position = uploaded.tell() if hasattr(uploaded, "tell") else 0
    try:
        data = uploaded.read(MAX_BRAND_IMAGE_BYTES + 1)
    finally:
        if hasattr(uploaded, "seek"):
            uploaded.seek(position)
    if len(data) > MAX_BRAND_IMAGE_BYTES:
        raise ValidationError("La imagen no puede superar 512 KiB")

    suffix = PurePath(uploaded.name).suffix.casefold()
    if suffix == ".svg":
        declared_mime = getattr(uploaded, "content_type", None)
        if declared_mime and declared_mime != "image/svg+xml":
            raise ValidationError("El MIME declarado no coincide con el contenido SVG")
        sanitized, dimensions = _sanitize_svg(data)
        width, height = dimensions
        if sanitized != data:
            _replace_upload_content(uploaded, sanitized)
    else:
        detectors = (
            ({".png"}, "image/png", _png_dimensions),
            ({".jpg", ".jpeg"}, "image/jpeg", _jpeg_dimensions),
            ({".webp"}, "image/webp", _webp_dimensions),
        )
        detected = next(
            (
                (extensions, mime, dimensions)
                for extensions, mime, parser in detectors
                if (dimensions := parser(data))
            ),
            None,
        )
        if detected is None:
            raise ValidationError("El archivo no es una imagen PNG, JPEG, WebP o SVG válida")
        extensions, mime, (width, height) = detected
        if suffix not in extensions:
            raise ValidationError(f"La extensión no coincide con el contenido {mime}")
        declared_mime = getattr(uploaded, "content_type", None)
        if declared_mime and declared_mime != mime:
            raise ValidationError("El MIME declarado no coincide con el contenido de la imagen")
    if width < 1 or height < 1 or width > MAX_BRAND_IMAGE_WIDTH or height > MAX_BRAND_IMAGE_HEIGHT:
        raise ValidationError(
            f"Dimensiones máximas: {MAX_BRAND_IMAGE_WIDTH}×{MAX_BRAND_IMAGE_HEIGHT} px"
        )
