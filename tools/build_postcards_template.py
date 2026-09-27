"""Build the canonical 28-page Postcards PDF from the supplied two-page master.

The source pages are cloned directly. Nothing is rasterized or re-laid out, so
the original A3 geometry, crop marks, line positions, images and fonts remain
unchanged.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from pypdf import PdfReader, PdfWriter


def build(source: Path, output: Path, repeats: int = 14) -> None:
    reader = PdfReader(source)
    if len(reader.pages) != 2:
        raise ValueError(f"expected a two-page master, got {len(reader.pages)} pages")

    expected_box = tuple(float(value) for value in reader.pages[0].mediabox)
    for index, page in enumerate(reader.pages, start=1):
        box = tuple(float(value) for value in page.mediabox)
        if box != expected_box:
            raise ValueError(f"page {index} has a different MediaBox: {box}")

    writer = PdfWriter()
    writer.metadata = {
        "/Title": "Postcards - 2x2 template, 14 blocks",
        "/Subject": "Canonical two-page A3 master repeated 14 times",
        "/Creator": "Postcards template builder",
    }
    for _ in range(repeats):
        for page in reader.pages:
            writer.add_page(page)

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as stream:
        writer.write(stream)

    check = PdfReader(output)
    if len(check.pages) != repeats * 2:
        raise RuntimeError(f"expected {repeats * 2} output pages, got {len(check.pages)}")
    for index, page in enumerate(check.pages, start=1):
        box = tuple(float(value) for value in page.mediabox)
        if box != expected_box:
            raise RuntimeError(f"output page {index} changed MediaBox: {box}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--repeats", type=int, default=14)
    args = parser.parse_args()
    build(args.source, args.output, args.repeats)


if __name__ == "__main__":
    main()
