"""Media payloads shared by the recorders: tiny, deterministic and valid enough
for a provider client to accept. Built from code, never read from disk, so a
re-recording is byte-identical.
"""

from __future__ import annotations

import base64
import struct
import zlib


def _chunk(kind: bytes, body: bytes) -> bytes:
    crc = zlib.crc32(kind + body) & 0xFFFFFFFF
    return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", crc)


def _png() -> bytes:
    header = struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0)  # 1x1, 8-bit grayscale
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", header)
        + _chunk(b"IDAT", zlib.compress(b"\x00\x00", 9))
        + _chunk(b"IEND", b"")
    )


#: A 1x1 grayscale PNG, 67 bytes.
PNG_1X1: bytes = _png()
assert len(PNG_1X1) == 67, len(PNG_1X1)


def big_png(min_b64_chars: int) -> bytes:
    """A PNG-headed buffer whose base64 form has more than `min_b64_chars`
    characters: the PNG signature and a valid header, then zero padding."""
    size = (min_b64_chars // 4 + 1) * 3
    head = PNG_1X1[:33]  # signature and IHDR
    return head + bytes(size - len(head))


def _wav() -> bytes:
    rate, samples = 8000, 800  # 0.1 s of 16-bit mono silence
    data = bytes(samples * 2)
    fmt = struct.pack("<HHIIHH", 1, 1, rate, rate * 2, 2, 16)
    return (
        b"RIFF"
        + struct.pack("<I", 36 + len(data))
        + b"WAVEfmt "
        + struct.pack("<I", len(fmt))
        + fmt
        + b"data"
        + struct.pack("<I", len(data))
        + data
    )


#: 0.1 s of silence, 8 kHz 16-bit mono WAV.
WAV_SILENT: bytes = _wav()


def _pdf() -> bytes:
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 72 72] >>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref,
    )
    return out


#: A minimal one-page PDF.
PDF_ONE_PAGE: bytes = _pdf()


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def data_url(mime: str, data: bytes) -> str:
    return f"data:{mime};base64,{b64(data)}"
