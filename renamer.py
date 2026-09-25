import os
import shlex
import sys
from pathlib import Path

def parse_drag_and_drop_paths(input_str: str) -> list[Path]:
    """
    Parses paths from drag-and-drop input in the terminal.
    Handles quoted paths, unquoted paths, space-delimited paths,
    and Windows backslashes.
    """
    input_str = input_str.strip()
    if not input_str:
        return []

    paths = []
    
    # Try shlex splitting first (handles quotes correctly)
    try:
        # posix=False preserves Windows backslashes
        tokens = shlex.split(input_str, posix=False)
    except Exception:
        # Fallback simple split if shlex fails on unescaped quotes
        tokens = [input_str]

    for token in tokens:
        # Strip surrounding quotes if present
        cleaned = token.strip('"\'')
        if not cleaned:
            continue
        p = Path(cleaned)
        if p.exists():
            if p.is_dir():
                # If a directory was dropped, add all files inside it
                for child in sorted(p.iterdir()):
                    if child.is_file():
                        paths.append(child)
            elif p.is_file():
                paths.append(p)
    return paths

def main():
    print("=" * 60)
    print("           Offset Auto Renamer")
    print("=" * 60)
    print("Drag and drop file(s) or a folder into this terminal window, then press Enter.")
    print("Press Ctrl+C at any time to exit.\n")

    try:
        user_input = input("Drag & drop files here: ")
    except (KeyboardInterrupt, EOFError):
        print("\nExiting.")
        return

    files = parse_drag_and_drop_paths(user_input)

    if not files:
        print("\nNo valid files found or selected.")
        return

    print(f"\nFound {len(files)} file(s) to process.")
    print("-" * 60)
    print("Instructions:")
    print("  • Type the NEW name for each file and press Enter.")
    print("  • If you omit the file extension, the original extension will be kept automatically.")
    print("  • Leave blank (just press Enter) to KEEP the original name.")
    print("  • Type 'skip' to skip renaming a file.")
    print("  • Type 'quit' to stop processing remaining files.")
    print("-" * 60 + "\n")

    renamed_count = 0
    skipped_count = 0

    for idx, file_path in enumerate(files, 1):
        orig_name = file_path.name
        orig_ext = file_path.suffix

        prompt = f"{orig_name} -> "
        try:
            new_name_input = input(prompt).strip()
        except (KeyboardInterrupt, EOFError):
            print("\nRenaming process interrupted.")
            break

        if new_name_input.lower() in ("quit", "q", ":q"):
            print("\nStopping further renames.")
            break

        if not new_name_input or new_name_input.lower() == "skip":
            print(f"   [Skipped: {orig_name}]\n")
            skipped_count += 1
            continue

        # Determine target extension & filename
        target_path = Path(new_name_input)
        if not target_path.suffix and orig_ext:
            # User didn't type an extension; append original extension automatically
            target_name = new_name_input + orig_ext
        else:
            target_name = new_name_input

        target_file_path = file_path.parent / target_name

        if target_file_path == file_path:
            print(f"   [Unchanged: {orig_name}]\n")
            skipped_count += 1
            continue

        if target_file_path.exists():
            print(f"   [!] WARNING: '{target_name}' already exists in this folder.")
            try:
                overwrite = input("       Overwrite existing file? (y/N): ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                break
            if overwrite != 'y':
                print(f"   [Skipped: {orig_name}]\n")
                skipped_count += 1
                continue

        try:
            file_path.rename(target_file_path)
            print(f"   [✓ Successfully renamed to: {target_name}]\n")
            renamed_count += 1
        except Exception as e:
            print(f"   [✗ Error renaming file: {e}]\n")

    print("=" * 60)
    print(f"Summary: {renamed_count} renamed, {skipped_count} skipped/kept.")
    print("=" * 60)

if __name__ == "__main__":
    main()
