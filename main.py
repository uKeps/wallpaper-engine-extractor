#!/usr/bin/env python3
"""Wallpaper Engine PKG & TEX Extractor Entry Point."""

import argparse
import sys
from pathlib import Path

# Add project root to path to ensure correct relative imports
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Avoid crashes when workshop titles contain characters outside the console's codepage
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

from src.extractor import extract_package
from src.tex_parser import extract_tex_file
from src.video_extractor import extract_video_file, SUPPORTED_VIDEO_EXTENSIONS


def run_cli(args):
    """Execute the extraction in CLI mode."""
    input_path = Path(args.input)
    if not input_path.is_file():
        print(f"Error: Input file does not exist: {input_path}")
        sys.exit(1)
        
    output_dir = Path(args.output) if args.output else None
    
    try:
        if input_path.suffix.lower() == ".pkg":
            extract_package(
                pkg_path=input_path,
                output_dir=output_dir,
                extract_tex=not args.no_tex_convert,
                extract_all_mipmaps=args.all_mipmaps,
                cleanup_non_images=not args.no_cleanup
            )
        elif input_path.suffix.lower() == ".tex":
            print(f"Reading texture: {input_path.name}...")
            imgs = extract_tex_file(
                tex_path=input_path,
                output_dir=output_dir,
                extract_all_mipmaps=args.all_mipmaps
            )
            print(f"Successfully extracted {len(imgs)} image(s) from .tex container.")
            for img in imgs:
                print(f"Created: {img.name}")
        elif input_path.suffix.lower() in SUPPORTED_VIDEO_EXTENSIONS:
            print(f"Processing video wallpaper: {input_path.name}...")
            output_video = extract_video_file(video_path=input_path, output_dir=output_dir)
            print(f"Created: {output_video.name}")
        else:
            print("Error: Unsupported file format. Must be .pkg, .tex, .mp4, or .webm")
            sys.exit(1)
            
        print("Done!")
    except Exception as e:
        print(f"Error during extraction: {e}")
        sys.exit(1)


def list_installed_wallpapers():
    """Print installed Wallpaper Engine Steam Workshop wallpapers and their extractable asset paths."""
    from src.steam_finder import find_installed_wallpapers

    wallpapers = find_installed_wallpapers()
    if not wallpapers:
        print("No Wallpaper Engine workshop items found.")
        return

    print(f"Found {len(wallpapers)} wallpaper(s):\n")
    for wp in wallpapers:
        location = str(wp.asset_path) if wp.asset_path else "No extractable asset found"
        print(f"[{wp.workshop_id}] {wp.title} ({wp.wp_type})")
        print(f"    {location}")


def main():
    # If no arguments are provided, default to launching the GUI
    if len(sys.argv) == 1:
        from src.gui import main as launch_gui
        launch_gui()
        return

    # CLI Arguments Parser
    parser = argparse.ArgumentParser(
        description="Extract Wallpaper Engine .pkg files and convert .tex textures to standard images."
    )
    parser.add_argument(
        "input",
        nargs="?",
        help="Path to the scene.pkg, an individual .tex file, or a video wallpaper (.mp4/.webm)."
    )
    parser.add_argument(
        "-o", "--output",
        help="Directory to save extracted files. Defaults to '<pkg_name>_extracted'."
    )
    parser.add_argument(
        "--no-tex-convert",
        action="store_true",
        help="Disable converting extracted .tex files to PNG/JPG."
    )
    parser.add_argument(
        "--all-mipmaps",
        action="store_true",
        help="Extract all mipmap sizes instead of only the highest resolution texture."
    )
    parser.add_argument(
        "--no-cleanup",
        action="store_true",
        help="Disable cleaning up non-image files (keeps shaders, scene.json, scripts, etc.)."
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Force launch the Graphical User Interface."
    )
    parser.add_argument(
        "--list-wallpapers",
        action="store_true",
        help="List installed Wallpaper Engine Steam Workshop wallpapers and exit."
    )

    args = parser.parse_args()

    if args.list_wallpapers:
        list_installed_wallpapers()
        return

    if args.gui or not args.input:
        from src.gui import main as launch_gui
        launch_gui()
    else:
        run_cli(args)


if __name__ == "__main__":
    main()
