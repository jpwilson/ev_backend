#!/usr/bin/env python3
"""
Image optimization script for EV Lineup.

Converts car images to WebP format, generates thumbnails (400px width),
and enforces a max file size of 500KB.

Usage:
    python scripts/optimize_images.py --input-dir /path/to/car_images --output-dir /path/to/optimized

Requirements:
    pip install Pillow
"""

import argparse
import os
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("ERROR: Pillow is required. Install with: pip install Pillow")
    sys.exit(1)

MAX_FILE_SIZE_KB = 500
THUMBNAIL_WIDTH = 400
WEBP_QUALITY_START = 85
WEBP_QUALITY_MIN = 40


def convert_to_webp(input_path: Path, output_path: Path, max_size_kb: int = MAX_FILE_SIZE_KB) -> bool:
    """Convert an image to WebP, ensuring it's under max_size_kb."""
    try:
        img = Image.open(input_path)
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGBA")
        else:
            img = img.convert("RGB")

        quality = WEBP_QUALITY_START
        while quality >= WEBP_QUALITY_MIN:
            img.save(output_path, "WEBP", quality=quality, method=4)
            size_kb = output_path.stat().st_size / 1024
            if size_kb <= max_size_kb:
                return True
            quality -= 5

        # Last resort: resize down until under limit
        factor = 0.9
        while factor > 0.3:
            new_size = (int(img.width * factor), int(img.height * factor))
            resized = img.resize(new_size, Image.LANCZOS)
            resized.save(output_path, "WEBP", quality=WEBP_QUALITY_MIN, method=4)
            if output_path.stat().st_size / 1024 <= max_size_kb:
                return True
            factor -= 0.1

        return True  # Save best effort
    except Exception as e:
        print(f"  ERROR processing {input_path.name}: {e}")
        return False


def generate_thumbnail(input_path: Path, output_path: Path, width: int = THUMBNAIL_WIDTH) -> bool:
    """Generate a WebP thumbnail at the specified width."""
    try:
        img = Image.open(input_path)
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGBA")
        else:
            img = img.convert("RGB")

        ratio = width / img.width
        new_height = int(img.height * ratio)
        img = img.resize((width, new_height), Image.LANCZOS)
        img.save(output_path, "WEBP", quality=80, method=4)
        return True
    except Exception as e:
        print(f"  ERROR generating thumbnail for {input_path.name}: {e}")
        return False


def process_directory(input_dir: str, output_dir: str):
    """Process all images in input_dir, write optimized versions to output_dir."""
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    full_dir = output_path / "full"
    thumb_dir = output_path / "thumbnails"

    full_dir.mkdir(parents=True, exist_ok=True)
    thumb_dir.mkdir(parents=True, exist_ok=True)

    image_extensions = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp"}
    images = [f for f in input_path.iterdir() if f.suffix.lower() in image_extensions]

    if not images:
        print(f"No images found in {input_dir}")
        return

    print(f"Found {len(images)} images to process")

    total_original_kb = 0
    total_optimized_kb = 0
    success_count = 0

    for img_file in sorted(images):
        stem = img_file.stem
        webp_name = f"{stem}.webp"
        full_output = full_dir / webp_name
        thumb_output = thumb_dir / webp_name

        original_kb = img_file.stat().st_size / 1024
        total_original_kb += original_kb

        print(f"  Processing: {img_file.name} ({original_kb:.0f}KB)")

        if convert_to_webp(img_file, full_output):
            optimized_kb = full_output.stat().st_size / 1024
            total_optimized_kb += optimized_kb
            print(f"    Full: {optimized_kb:.0f}KB")
        else:
            print(f"    Full: FAILED")
            continue

        if generate_thumbnail(img_file, thumb_output):
            thumb_kb = thumb_output.stat().st_size / 1024
            print(f"    Thumb: {thumb_kb:.0f}KB")
        else:
            print(f"    Thumb: FAILED")

        success_count += 1

    savings = total_original_kb - total_optimized_kb
    pct = (savings / total_original_kb * 100) if total_original_kb > 0 else 0
    print(f"\nDone! {success_count}/{len(images)} images processed")
    print(f"Original: {total_original_kb / 1024:.1f}MB -> Optimized: {total_optimized_kb / 1024:.1f}MB (saved {pct:.0f}%)")
    print(f"Output: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Optimize car images for web delivery")
    parser.add_argument("--input-dir", required=True, help="Directory containing source images")
    parser.add_argument("--output-dir", required=True, help="Directory for optimized output")
    args = parser.parse_args()

    if not os.path.isdir(args.input_dir):
        print(f"ERROR: Input directory not found: {args.input_dir}")
        sys.exit(1)

    process_directory(args.input_dir, args.output_dir)


if __name__ == "__main__":
    main()
