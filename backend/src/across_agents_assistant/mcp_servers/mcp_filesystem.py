import sys
import os
import json
from pathlib import Path
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Filesystem")

base_path = ""


def _resolve(path: str) -> Path:
    """Resolve a relative path against the base path."""
    if path.startswith("/"):
        p = Path(path)
    else:
        p = Path(base_path) / path
    p = p.resolve()
    # Security: ensure the resolved path is within base_path
    try:
        p.relative_to(Path(base_path).resolve())
    except ValueError:
        raise ValueError(f"Access denied: {path} is outside the allowed directory")
    return p


@mcp.tool(name="filesystem_read_file")
def filesystem_read_file(path: str) -> str:
    """Read the contents of a file.

    Args:
        path: Relative or absolute path to the file.
    """
    try:
        p = _resolve(path)
        if not p.exists():
            return f"Error: File not found: {path}"
        if not p.is_file():
            return f"Error: Not a file: {path}"
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception as e:
        return f"Error reading file: {str(e)}"


@mcp.tool(name="filesystem_write_file")
def filesystem_write_file(path: str, content: str) -> str:
    """Write content to a file (creates or overwrites).

    Args:
        path: Relative or absolute path to the file.
        content: The content to write.
    """
    try:
        p = _resolve(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Successfully wrote to {path}"
    except Exception as e:
        return f"Error writing file: {str(e)}"


@mcp.tool(name="filesystem_list_directory")
def filesystem_list_directory(path: str = ".") -> str:
    """List files and directories in the given path.

    Args:
        path: Relative or absolute path to the directory (default: current directory).
    """
    try:
        p = _resolve(path)
        if not p.exists():
            return f"Error: Directory not found: {path}"
        if not p.is_dir():
            return f"Error: Not a directory: {path}"
        entries = []
        for entry in p.iterdir():
            entry_type = "dir" if entry.is_dir() else "file"
            size = entry.stat().st_size if entry.is_file() else "-"
            entries.append(f"{entry_type}\t{entry.name}\t{size}")
        if not entries:
            return "Directory is empty."
        return "Type\tName\tSize\n" + "\n".join(entries)
    except Exception as e:
        return f"Error listing directory: {str(e)}"


@mcp.tool(name="filesystem_create_directory")
def filesystem_create_directory(path: str) -> str:
    """Create a new directory (including parent directories).

    Args:
        path: Relative or absolute path to the directory to create.
    """
    try:
        p = _resolve(path)
        p.mkdir(parents=True, exist_ok=True)
        return f"Successfully created directory: {path}"
    except Exception as e:
        return f"Error creating directory: {str(e)}"


@mcp.tool(name="filesystem_delete_file")
def filesystem_delete_file(path: str) -> str:
    """Delete a file.

    Args:
        path: Relative or absolute path to the file to delete.
    """
    try:
        p = _resolve(path)
        if not p.exists():
            return f"Error: File not found: {path}"
        if p.is_dir():
            return f"Error: {path} is a directory, use delete_directory instead"
        p.unlink()
        return f"Successfully deleted: {path}"
    except Exception as e:
        return f"Error deleting file: {str(e)}"


@mcp.tool(name="filesystem_delete_directory")
def filesystem_delete_directory(path: str) -> str:
    """Delete a directory and all its contents.

    Args:
        path: Relative or absolute path to the directory to delete.
    """
    try:
        import shutil
        p = _resolve(path)
        if not p.exists():
            return f"Error: Directory not found: {path}"
        if not p.is_dir():
            return f"Error: Not a directory: {path}"
        shutil.rmtree(p)
        return f"Successfully deleted directory: {path}"
    except Exception as e:
        return f"Error deleting directory: {str(e)}"


@mcp.tool(name="filesystem_move")
def filesystem_move(source: str, destination: str) -> str:
    """Move or rename a file or directory.

    Args:
        source: Relative or absolute path to the source.
        destination: Relative or absolute path to the destination.
    """
    try:
        import shutil
        src = _resolve(source)
        dst = _resolve(destination)
        if not src.exists():
            return f"Error: Source not found: {source}"
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        return f"Successfully moved {source} to {destination}"
    except Exception as e:
        return f"Error moving file: {str(e)}"


@mcp.tool(name="filesystem_get_file_info")
def filesystem_get_file_info(path: str) -> str:
    """Get information about a file or directory.

    Args:
        path: Relative or absolute path.
    """
    try:
        p = _resolve(path)
        if not p.exists():
            return f"Error: Path not found: {path}"
        stat = p.stat()
        info = {
            "path": str(p),
            "type": "directory" if p.is_dir() else "file",
            "size": stat.st_size,
            "modified": stat.st_mtime,
            "permissions": oct(stat.st_mode)[-3:],
        }
        return json.dumps(info, indent=2)
    except Exception as e:
        return f"Error getting file info: {str(e)}"


def main():
    global base_path
    import argparse
    parser = argparse.ArgumentParser(description="Filesystem MCP Server")
    parser.add_argument("path", type=str, help="Base directory path")
    args, unknown = parser.parse_known_args()

    base_path = os.path.expanduser(args.path)
    if not os.path.exists(base_path):
        os.makedirs(base_path, exist_ok=True)

    sys.argv = [sys.argv[0]] + unknown
    mcp.run()


if __name__ == "__main__":
    main()
