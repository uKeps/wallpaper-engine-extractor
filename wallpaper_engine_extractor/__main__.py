"""Command-line entry point: `wallpaper-engine-extractor`, `python -m wallpaper_engine_extractor`."""

import argparse
import sys
from pathlib import Path

from wallpaper_engine_extractor.extractor import extract_package, wallpaper_output_name
from wallpaper_engine_extractor.steam_finder import wallpaper_from_folder
from wallpaper_engine_extractor.tex_parser import extract_tex_file
from wallpaper_engine_extractor.video_extractor import extract_video_file, SUPPORTED_VIDEO_EXTENSIONS


def extract_one(input_path: Path, output_dir: Path | None, args) -> Path:
    """Extract a single .pkg, .tex or video file and return where the output went."""
    suffix = input_path.suffix.lower()
    if suffix == ".pkg":
        output_dir = output_dir or input_path.parent / f"{input_path.stem}_extracted"
        extract_package(
            pkg_path=input_path,
            output_dir=output_dir,
            extract_tex=not args.no_tex_convert,
            extract_all_mipmaps=args.all_mipmaps,
            cleanup_non_images=not args.no_cleanup
        )
    elif suffix == ".tex":
        output_dir = output_dir or input_path.parent
        print(f"Reading texture: {input_path.name}...")
        imgs = extract_tex_file(
            tex_path=input_path,
            output_dir=output_dir,
            extract_all_mipmaps=args.all_mipmaps
        )
        print(f"Successfully extracted {len(imgs)} image(s) from .tex container.")
        for img in imgs:
            print(f"Created: {img.name}")
    elif suffix in SUPPORTED_VIDEO_EXTENSIONS:
        output_dir = output_dir or input_path.parent
        print(f"Processing video wallpaper: {input_path.name}...")
        output_video = extract_video_file(video_path=input_path, output_dir=output_dir)
        print(f"Created: {output_video.name}")
    else:
        raise ValueError("Unsupported file format. Must be .pkg, .tex, .mp4, .webm, or a folder")
    return output_dir


def find_wallpaper_assets(directory: Path) -> list[tuple[Path, Path]]:
    """Every (wallpaper folder, .pkg or video) under a directory, like RePKG's -r."""
    folders = {p.parent for pattern in ("*.pkg", "project.json") for p in directory.rglob(pattern)}
    found = []
    for folder in sorted(folders):
        if not (folder / "project.json").is_file():
            # Loose packages with no wallpaper metadata: each one is its own wallpaper
            found.extend((pkg, pkg) for pkg in sorted(folder.glob("*.pkg")))
            continue
        wallpaper = wallpaper_from_folder(folder)
        if wallpaper and wallpaper.asset_path:
            found.append((folder, wallpaper.asset_path))
    return found


def run_cli(args):
    """Execute the extraction in CLI mode."""
    input_path = Path(args.input).resolve()
    output_dir = Path(args.output) if args.output else None

    if input_path.is_dir():
        wallpapers = find_wallpaper_assets(input_path)
        if not wallpapers:
            print(f"Error: No wallpaper (.pkg or video) found under: {input_path}")
            sys.exit(1)
        output_root = output_dir or input_path.parent / f"{input_path.name}_extracted"
        used_names: set[str] = set()
        failures = 0
        for folder, asset in wallpapers:
            name = wallpaper_output_name(folder)
            if name.casefold() in used_names:
                name = f"{name} ({folder.name})"
            used_names.add(name.casefold())
            print(f"\n### {asset}")
            try:
                extract_one(asset, output_root / name, args)
            except Exception as e:
                failures += 1
                print(f"Error during extraction of {asset}: {e}")
        print(f"\nDone! Extracted {len(wallpapers) - failures} of {len(wallpapers)} wallpaper(s) to: {output_root}")
        if failures:
            sys.exit(1)
        return

    if not input_path.is_file():
        print(f"Error: Input path does not exist: {input_path}")
        sys.exit(1)

    try:
        output = extract_one(input_path, output_dir, args)
        print(f"Done! Output: {output}")
    except Exception as e:
        print(f"Error during extraction: {e}")
        sys.exit(1)


def list_installed_wallpapers():
    """Print installed Wallpaper Engine Steam Workshop wallpapers and their extractable asset paths."""
    from wallpaper_engine_extractor.steam_finder import find_installed_wallpapers

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
    # Avoid crashes when workshop titles contain characters outside the console's codepage
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    # If no arguments are provided, default to launching the GUI
    if len(sys.argv) == 1:
        from wallpaper_engine_extractor.gui import main as launch_gui
        launch_gui()
        return

    # CLI Arguments Parser
    parser = argparse.ArgumentParser(
        description="Extract Wallpaper Engine .pkg files and convert .tex textures to standard images."
    )
    parser.add_argument(
        "input",
        nargs="?",
        help="Path to a scene.pkg, a .tex file, a video wallpaper (.mp4/.webm), or a folder "
             "(every wallpaper found under it is extracted into its own subfolder)."
    )
    parser.add_argument(
        "-o", "--output",
        help="Directory to save extracted files. Defaults to '<pkg_name>_extracted' (or '<folder>_extracted' for a folder)."
    )
    parser.add_argument(
        "--no-tex-convert",
        action="store_true",
        help="Keep .tex files as they are instead of converting them to images."
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
        from wallpaper_engine_extractor.gui import main as launch_gui
        launch_gui()
    else:
        run_cli(args)


if __name__ == "__main__":
    main()
