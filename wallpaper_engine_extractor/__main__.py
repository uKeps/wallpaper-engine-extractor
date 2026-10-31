"""Command-line entry point: `wallpaper-engine-extractor`, `python -m wallpaper_engine_extractor`."""

import argparse
import re
import sys
from importlib import metadata
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


def package_version() -> str:
    """The version_info.txt next to the sources (checkout, exe), else the installed metadata (wheel)."""
    try:
        text = (Path(__file__).resolve().parent.parent / "assets" / "version_info.txt").read_text()
        return re.search(r'"ProductVersion", "(\d+\.\d+\.\d+)', text).group(1)
    except (OSError, AttributeError):
        pass
    try:
        return metadata.version("wallpaper-engine-extractor")
    except metadata.PackageNotFoundError:
        return "unknown"


def find_wallpaper_assets(directory: Path) -> tuple[list[tuple[Path, Path]], list[tuple[str, str]]]:
    """Every (wallpaper folder, .pkg or video) under a directory, like RePKG's -r,
    plus (title, reason) for the wallpaper folders that have nothing to extract."""
    folders = {p.parent for pattern in ("*.pkg", "project.json") for p in directory.rglob(pattern)}
    found, skipped = [], []
    for folder in sorted(folders):
        if not (folder / "project.json").is_file():
            # Loose packages with no wallpaper metadata: each one is its own wallpaper
            found.extend((pkg, pkg) for pkg in sorted(folder.glob("*.pkg")))
            continue
        wallpaper = wallpaper_from_folder(folder)
        if wallpaper.asset_path:
            found.append((folder, wallpaper.asset_path))
        elif wallpaper.wp_type in ("web", "application"):
            skipped.append((wallpaper.title, f"{wallpaper.wp_type} wallpaper, nothing to extract"))
        else:
            skipped.append((wallpaper.title, "no .pkg or video found"))
    return found, skipped


def run_cli(args):
    """Execute the extraction in CLI mode."""
    input_path = Path(args.input).resolve()
    output_dir = Path(args.output) if args.output else None

    if input_path.is_dir():
        wallpapers, skipped = find_wallpaper_assets(input_path)
        for title, reason in skipped:
            print(f'Skipped "{title}": {reason}' if wallpapers else f'Error: "{title}" can\'t be extracted: {reason}')
        jobs = []  # (label, asset, output dir)
        if wallpapers:
            kind, output_root = "wallpaper", output_dir or input_path.parent / f"{input_path.name}_extracted"
            used_names: set[str] = set()
            for folder, asset in wallpapers:
                name = wallpaper_output_name(folder)
                if name.casefold() in used_names:
                    name = f"{name} ({folder.name})"
                used_names.add(name.casefold())
                jobs.append((name, asset, output_root / name))
        elif not skipped:
            # Loose textures, like RePKG's -t: converted next to themselves, or mirrored into -o
            kind, output_root = "texture", output_dir or input_path
            for tex in sorted(input_path.rglob("*.tex")):
                rel = tex.relative_to(input_path)
                jobs.append((rel.as_posix(), tex, output_root / rel.parent))
        if not jobs:
            if not skipped:
                print(f"Error: No wallpaper (.pkg, video or .tex) found under: {input_path}")
            sys.exit(1)
        failures = 0
        for n, (label, asset, out) in enumerate(jobs, 1):
            print(f"\n[{n}/{len(jobs)}] {label}")
            try:
                extract_one(asset, out, args)
            except Exception as e:
                failures += 1
                print(f"Error during extraction of {label}: {e}")
        summary = f"\nDone! Extracted {len(jobs) - failures} of {len(jobs)} {kind}(s) to: {output_root}"
        print(summary + (f" ({len(skipped)} skipped, nothing to extract)" if skipped else ""))
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
    parser.add_argument("--version", action="version", version=f"wallpaper-engine-extractor {package_version()}")
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
