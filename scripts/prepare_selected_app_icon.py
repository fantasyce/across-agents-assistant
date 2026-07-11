#!/usr/bin/env python3
"""Prepare the selected AAA icon source at the canonical macOS source size."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


CANVAS_SIZE = 1024
STATUS_DOT_SIZE = 96


def _restore_background(image: np.ndarray, center_x: float, center_y: float, radius: float) -> np.ndarray:
    height, width, _ = image.shape
    half_size = int(radius + 76)
    left = max(1, int(round(center_x)) - half_size)
    right = min(width - 2, int(round(center_x)) + half_size)
    top = max(1, int(round(center_y)) - half_size)
    bottom = min(height - 2, int(round(center_y)) + half_size)

    # Reconstruct the smooth ivory field from all four clean boundaries using
    # a Coons patch. This removes the generated dot and its broad color halo
    # without introducing another circular repair edge.
    source = image.astype(np.float64)
    top_edge = source[top - 1, left : right + 1]
    bottom_edge = source[bottom + 1, left : right + 1]
    left_edge = source[top : bottom + 1, left - 1]
    right_edge = source[top : bottom + 1, right + 1]
    region_height = bottom - top + 1
    region_width = right - left + 1
    u = np.linspace(0.0, 1.0, region_width)[None, :, None]
    v = np.linspace(0.0, 1.0, region_height)[:, None, None]
    horizontal = (1.0 - v) * top_edge[None, :, :] + v * bottom_edge[None, :, :]
    vertical = (1.0 - u) * left_edge[:, None, :] + u * right_edge[:, None, :]
    top_left = (top_edge[0] + left_edge[0]) / 2
    top_right = (top_edge[-1] + right_edge[0]) / 2
    bottom_left = (bottom_edge[0] + left_edge[-1]) / 2
    bottom_right = (bottom_edge[-1] + right_edge[-1]) / 2
    corners = (
        (1.0 - u) * (1.0 - v) * top_left
        + u * (1.0 - v) * top_right
        + (1.0 - u) * v * bottom_left
        + u * v * bottom_right
    )
    fitted = horizontal + vertical - corners
    result = image.astype(np.float64).copy()
    result[top : bottom + 1, left : right + 1] = fitted
    return np.clip(result, 0, 255).astype(np.uint8)


def prepare(source: Path, output: Path) -> None:
    image = Image.open(source).convert("RGB").resize(
        (CANVAS_SIZE, CANVAS_SIZE), Image.Resampling.LANCZOS
    )
    pixels = np.asarray(image)
    red = pixels[..., 0].astype(np.int16)
    green = pixels[..., 1].astype(np.int16)
    blue = pixels[..., 2].astype(np.int16)
    purple = (blue > 120) & (red > 70) & (blue - red > 22) & (red - green > 9)
    ys, xs = np.where(purple)
    if xs.size == 0:
        raise RuntimeError("selected source does not contain the purple status dot")

    left, right = int(xs.min()), int(xs.max()) + 1
    top, bottom = int(ys.min()), int(ys.max()) + 1
    center_x = (left + right - 1) / 2
    center_y = (top + bottom - 1) / 2
    radius = max(right - left, bottom - top) / 2

    original_dot = image.crop((left, top, right, bottom)).resize(
        (STATUS_DOT_SIZE, STATUS_DOT_SIZE), Image.Resampling.LANCZOS
    )
    # Small status lights can be enlarged in place: the larger replacement
    # fully covers the original and preserves any surrounding machine lines.
    # Larger generated lights still need their old footprint restored first.
    if right - left <= STATUS_DOT_SIZE and bottom - top <= STATUS_DOT_SIZE:
        cleaned = image.copy()
    else:
        cleaned = Image.fromarray(_restore_background(pixels, center_x, center_y, radius), "RGB")

    mask = Image.new("L", (STATUS_DOT_SIZE * 4, STATUS_DOT_SIZE * 4), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, STATUS_DOT_SIZE * 4 - 1, STATUS_DOT_SIZE * 4 - 1), fill=255)
    mask = mask.resize((STATUS_DOT_SIZE, STATUS_DOT_SIZE), Image.Resampling.LANCZOS)
    destination = (
        round(center_x - STATUS_DOT_SIZE / 2),
        round(center_y - STATUS_DOT_SIZE / 2),
    )
    cleaned.paste(original_dot, destination, mask)
    output.parent.mkdir(parents=True, exist_ok=True)
    cleaned.save(output, format="PNG", optimize=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    prepare(args.source, args.output)


if __name__ == "__main__":
    main()
