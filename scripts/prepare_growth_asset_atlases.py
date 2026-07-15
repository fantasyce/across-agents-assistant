#!/usr/bin/env python3
"""Build deterministic transparent AAA growth atlases from selected source sheets.

Run with:
  uv run --with pillow python scripts/prepare_growth_asset_atlases.py
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageStat


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "assets/growth-sources"
OUTPUT_ROOT = ROOT / "macOS-Client/Sources/Assets/growth"
CELL_SIZE = 192
SAFE_SIZE = 164
VALIDATION_SIZES = (48, 64, 96)
BACKGROUNDS = {
    "light": (246, 247, 249, 255),
    "dark": (25, 27, 31, 255),
}


@dataclass(frozen=True)
class AtlasSpec:
    identifier: str
    source: str
    output: str
    columns: int
    rows: int
    sprite_ids: tuple[str, ...]


SPECS = (
    AtlasSpec(
        "journey_nodes",
        "journey-nodes-source.png",
        "journey-node-atlas.png",
        5,
        2,
        (
            "voice",
            "first_task",
            "evidence",
            "approval",
            "memory",
            "workflow",
            "repair",
            "replay",
            "release",
            "loop_engineering",
        ),
    ),
    AtlasSpec(
        "status_companions",
        "status-companions-source.png",
        "status-companion-atlas.png",
        4,
        2,
        ("idle", "listening", "working", "checking", "waiting", "complete", "blocked"),
    ),
    AtlasSpec(
        "trust_seals",
        "trust-seals-source.png",
        "trust-seal-atlas.png",
        2,
        2,
        ("ready", "review", "blocked", "improved"),
    ),
    AtlasSpec(
        "challenge_rewards",
        "challenge-rewards-source.png",
        "challenge-reward-atlas.png",
        4,
        2,
        (
            "first_verified_delivery",
            "evidence_explorer",
            "safe_reviewer",
            "repair_apprentice",
            "comparison_analyst",
            "release_guardian",
            "loop_guide",
        ),
    ),
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def remove_chroma_key(image: Image.Image) -> Image.Image:
    output = Image.new("RGBA", image.size)
    source_pixels = image.convert("RGBA").load()
    output_pixels = output.load()
    for y in range(image.height):
        for x in range(image.width):
            red, green, blue, alpha = source_pixels[x, y]
            distance = math.sqrt((255 - red) ** 2 + green**2 + (255 - blue) ** 2)
            magenta_excess = min(red, blue) - green
            if distance <= 34:
                alpha = 0
            elif distance < 118:
                alpha = round(alpha * (distance - 34) / 84)
            if red > 140 and blue > 140 and magenta_excess > 30:
                alpha = round(alpha * max(0.0, min(1.0, (100 - magenta_excess) / 70)))
                red = min(red, max(green, round(blue * 0.45)))
            output_pixels[x, y] = (red, green, blue, alpha)
    return output


def normalized_sprite(source: Image.Image, spec: AtlasSpec, index: int) -> Image.Image:
    column = index % spec.columns
    row = index // spec.columns
    x0 = round(source.width * column / spec.columns)
    x1 = round(source.width * (column + 1) / spec.columns)
    y0 = round(source.height * row / spec.rows)
    y1 = round(source.height * (row + 1) / spec.rows)
    inset = max(8, round(min(x1 - x0, y1 - y0) * 0.028))
    cell = source.crop((x0 + inset, y0 + inset, x1 - inset, y1 - inset))
    keyed = remove_chroma_key(cell)
    alpha_box = keyed.getchannel("A").getbbox()
    if alpha_box is None:
        raise ValueError(f"{spec.identifier}/{index} has no visible subject")
    subject = keyed.crop(alpha_box)
    subject.thumbnail((SAFE_SIZE, SAFE_SIZE), Image.Resampling.NEAREST)
    sprite = Image.new("RGBA", (CELL_SIZE, CELL_SIZE))
    sprite.alpha_composite(
        subject,
        ((CELL_SIZE - subject.width) // 2, (CELL_SIZE - subject.height) // 2),
    )
    return sprite


def validate_sprite(sprite: Image.Image, identifier: str) -> dict[str, object]:
    alpha = sprite.getchannel("A")
    opaque_pixels = sum(alpha.histogram()[24:])
    coverage = opaque_pixels / (CELL_SIZE * CELL_SIZE)
    if not 0.08 <= coverage <= 0.72:
        raise ValueError(f"{identifier} alpha coverage out of range: {coverage:.3f}")
    corner_alpha = max(
        alpha.getpixel((0, 0)),
        alpha.getpixel((CELL_SIZE - 1, 0)),
        alpha.getpixel((0, CELL_SIZE - 1)),
        alpha.getpixel((CELL_SIZE - 1, CELL_SIZE - 1)),
    )
    if corner_alpha != 0:
        raise ValueError(f"{identifier} does not preserve transparent safe-area corners")

    modes: dict[str, dict[str, float]] = {}
    for size in VALIDATION_SIZES:
        resized = sprite.resize((size, size), Image.Resampling.NEAREST)
        for mode, background in BACKGROUNDS.items():
            composited = Image.new("RGBA", (size, size), background)
            composited.alpha_composite(resized)
            luminance = composited.convert("L")
            standard_deviation = float(ImageStat.Stat(luminance).stddev[0])
            if standard_deviation < 12:
                raise ValueError(f"{identifier} is not distinguishable at {size}pt/{mode}")
            modes[f"{size}-{mode}"] = {"luminance_stddev": round(standard_deviation, 3)}
    return {"alpha_coverage": round(coverage, 4), "modes": modes}


def build_atlas(spec: AtlasSpec) -> dict[str, object]:
    source_path = SOURCE_ROOT / spec.source
    output_path = OUTPUT_ROOT / spec.output
    source = Image.open(source_path).convert("RGBA")
    atlas = Image.new("RGBA", (spec.columns * CELL_SIZE, spec.rows * CELL_SIZE))
    validations = []
    for index, sprite_id in enumerate(spec.sprite_ids):
        sprite = normalized_sprite(source, spec, index)
        atlas.alpha_composite(
            sprite,
            ((index % spec.columns) * CELL_SIZE, (index // spec.columns) * CELL_SIZE),
        )
        validations.append({"id": sprite_id, **validate_sprite(sprite, f"{spec.identifier}/{sprite_id}")})

    for index in range(len(spec.sprite_ids), spec.columns * spec.rows):
        cell = atlas.crop(
            (
                (index % spec.columns) * CELL_SIZE,
                (index // spec.columns) * CELL_SIZE,
                ((index % spec.columns) + 1) * CELL_SIZE,
                ((index // spec.columns) + 1) * CELL_SIZE,
            )
        )
        if cell.getchannel("A").getbbox() is not None:
            raise ValueError(f"{spec.identifier} unused cell {index} is not transparent")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    atlas.save(output_path, format="PNG", optimize=True)
    return {
        "id": spec.identifier,
        "source": spec.source,
        "source_sha256": sha256(source_path),
        "file": spec.output,
        "output_sha256": sha256(output_path),
        "columns": spec.columns,
        "rows": spec.rows,
        "cell_pixels": CELL_SIZE,
        "sprites": validations,
    }


def main() -> None:
    results = [build_atlas(spec) for spec in SPECS]
    validation = {
        "schema_version": "across-growth-asset-validation/1.0",
        "owner": "Across Agents Assistant",
        "source_kind": "selected built-in ImageGen pixel-art source sheets",
        "chroma_key": "#ff00ff",
        "validation_sizes": list(VALIDATION_SIZES),
        "background_modes": list(BACKGROUNDS),
        "atlases": results,
    }
    (OUTPUT_ROOT / "asset-validation.json").write_text(
        json.dumps(validation, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Prepared and validated {len(results)} AAA growth atlases.")


if __name__ == "__main__":
    main()
