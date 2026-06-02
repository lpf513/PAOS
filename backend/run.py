from pathlib import Path
import sys

import uvicorn


def _configure_import_path() -> None:
    """Make the backend package importable in source and PyInstaller modes."""

    if getattr(sys, "frozen", False):
        base_dir = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    else:
        base_dir = Path(__file__).resolve().parent

    if str(base_dir) not in sys.path:
        sys.path.insert(0, str(base_dir))


def main() -> None:
    """Start the PAOS FastAPI backend for Tauri sidecar packaging."""

    _configure_import_path()

    # Import the ASGI app directly so PyInstaller can discover and bundle it.
    from app.main import app

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8000,
        log_level="info",
        reload=False,
    )


if __name__ == "__main__":
    main()
