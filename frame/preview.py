from __future__ import annotations

import argparse
import json
import mimetypes
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from frame.constants import SLIDE_SECONDS
from frame.demo_library import ensure_demo_library
from frame.derive import build_slides
from frame.gestures import GestureClassifier
from frame.library import MediaAsset, scan_library
from frame.player import Slideshow
from frame.schema import KIND_GIF
from frame.sensor import UsbMatrixSensor, candidate_serial_ports
from frame.storage import cache_dir_for, resolve_library_root
from frame.test_images import TEST_IMAGE_DIR, ensure_test_images

WEB_DIR = Path(__file__).resolve().parent / "web"
REPO_ROOT = Path(__file__).resolve().parents[1]
LOCAL_CACHE = REPO_ROOT / "assets" / "cache"

mimetypes.add_type("video/quicktime", ".mov")
mimetypes.add_type("video/mp4", ".m4v")
mimetypes.add_type("image/heic", ".heic")


def load_slideshow(root: Path | None, test_media: bool = False) -> Slideshow:
    if test_media:
        assets = _test_gif_assets()
        cache = cache_dir_for(TEST_IMAGE_DIR, LOCAL_CACHE)
        source = f"test gifs ({TEST_IMAGE_DIR})"
    else:
        library = root or ensure_demo_library()
        assets = scan_library(library)
        if not assets:
            raise ValueError(f"no photos or videos in {library}")
        cache = cache_dir_for(library, LOCAL_CACHE)
        source = str(library)
    slides = build_slides(assets, cache)
    if not slides:
        raise ValueError("library produced no displayable slides")
    show = Slideshow(slides)
    show.set_source(source)
    return show


def _test_gif_assets() -> list[MediaAsset]:
    assets: list[MediaAsset] = []
    for still, gif, scene in ensure_test_images():
        assets.append(
            MediaAsset(
                kind=KIND_GIF,
                title=scene.title,
                still_source=still,
                motion_source=gif,
                mtime=still.stat().st_mtime,
            )
        )
    return assets


def start_sensor(show: Slideshow) -> None:
    def run() -> None:
        ports = candidate_serial_ports()
        if not ports:
            show.set_sensor("disconnected")
            return
        port = ports[0]
        show.set_sensor("connecting")
        try:
            classifier = GestureClassifier()
            with UsbMatrixSensor(port) as sensor:
                show.set_sensor("connected")
                for frame in sensor.frames():
                    event = classifier.update(time.monotonic(), frame)
                    show.set_sensor("connected" if classifier.background_ready else "learning")
                    show.set_armed(classifier.armed)
                    if event is not None:
                        show.apply_gesture(event.gesture)
        except Exception as exc:
            show.set_sensor(f"error: {exc}")

    threading.Thread(target=run, name="sen0628", daemon=True).start()


def start_clock(show: Slideshow) -> None:
    def run() -> None:
        while True:
            show.tick()
            time.sleep(0.05)

    threading.Thread(target=run, name="clock", daemon=True).start()


def make_handler(show: Slideshow) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            if args and str(args[0]).startswith("GET /api/state"):
                return
            super().log_message(format, *args)

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path == "/":
                self._send_path(WEB_DIR / "index.html", "text/html; charset=utf-8")
                return
            if path == "/api/state":
                self._send_json(show.snapshot())
                return
            if path.startswith("/media/"):
                self._send_media(path)
                return
            self.send_error(404)

        def do_POST(self) -> None:  # noqa: N802
            if urlparse(self.path).path != "/api/command":
                self.send_error(404)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length) or b"{}")
            except (ValueError, json.JSONDecodeError):
                self.send_error(400)
                return
            action = payload.get("action") if isinstance(payload, dict) else None
            if action == "next":
                show.next("keyboard")
            elif action == "previous":
                show.previous("keyboard")
            elif action == "play":
                show.play("keyboard")
            elif action == "stop":
                show.stop("keyboard")
            else:
                self.send_error(400)
                return
            self._send_json(show.snapshot())

        def _send_media(self, path: str) -> None:
            parts = unquote(path).strip("/").split("/")
            if len(parts) != 3:
                self.send_error(404)
                return
            _media, token, kind = parts
            if not token.isalnum() or kind not in {"still", "motion"}:
                self.send_error(404)
                return
            slide = show.slide_by_token(token)
            if slide is None:
                self.send_error(404)
                return
            file_path = slide.still if kind == "still" else slide.motion
            if file_path is None or not file_path.is_file():
                self.send_error(404)
                return
            mime = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
            self._send_path(file_path, mime, allow_range=True)

        def _send_json(self, payload: dict[str, object]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_path(self, path: Path, content_type: str, allow_range: bool = False) -> None:
            file_size = path.stat().st_size
            start = 0
            end = file_size - 1
            status = 200
            range_header = self.headers.get("Range") if allow_range else None
            if range_header and file_size:
                byte_range = _parse_range(range_header, file_size)
                if byte_range is None:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{file_size}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                start, end = byte_range
                status = 206
            length = end - start + 1
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(length))
            if status == 206:
                self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
            if "html" in content_type:
                self.send_header("Cache-Control", "no-store")
            else:
                self.send_header("Cache-Control", "public, max-age=3600")
            self.end_headers()
            with path.open("rb") as handle:
                handle.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = handle.read(min(64 * 1024, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)

    return Handler


def _parse_range(header: str, file_size: int) -> tuple[int, int] | None:
    """Parse a single `bytes=first-last` range; None means unsatisfiable or malformed."""
    if not header.startswith("bytes="):
        return None
    spec = header[len("bytes=") :].split(",", 1)[0].strip()
    first, dash, last = spec.partition("-")
    if not dash or (first and not first.isdigit()) or (last and not last.isdigit()):
        return None
    if not first and not last:
        return None
    if not first:
        suffix = min(int(last), file_size)
        if suffix == 0:
            return None
        return file_size - suffix, file_size - 1
    start = int(first)
    end = min(file_size - 1, int(last)) if last else file_size - 1
    if start >= file_size or start > end:
        return None
    return start, end


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ken Burns frame preview for a mixed media library")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--library", help="SD card, USB volume, or folder of photos/videos")
    parser.add_argument("--discover", action="store_true", help="Use the first removable volume")
    parser.add_argument("--demo", action="store_true", help="Use the generated mixed demo library")
    parser.add_argument("--test-media", action="store_true", help="Use the original labeled test GIFs")
    parser.add_argument("--no-sensor", action="store_true")
    args = parser.parse_args(argv)

    root: Path | None = None
    if args.test_media:
        root = None
    elif args.library:
        root = Path(args.library).expanduser()
        if not root.is_dir():
            raise SystemExit(f"library not found: {root}")
    elif args.discover:
        root = resolve_library_root(None)
        if root is None:
            raise SystemExit("no removable volume found")
    elif not args.demo:
        discovered = resolve_library_root(None)
        root = discovered if discovered is not None else None

    try:
        show = load_slideshow(root, test_media=args.test_media)
    except ValueError as exc:
        if args.library or args.test_media:
            raise SystemExit(str(exc)) from exc
        print(f"Library empty ({exc}); falling back to demo.", flush=True)
        show = load_slideshow(None, test_media=False)
    start_clock(show)
    if not args.no_sensor:
        start_sensor(show)

    kinds = {}
    for slide in show.slides:
        kinds[slide.kind] = kinds.get(slide.kind, 0) + 1
    server = ThreadingHTTPServer((args.host, args.port), make_handler(show))
    url = f"http://{args.host}:{args.port}/"
    print(f"Preview {url}", flush=True)
    print(f"Library: {show.source}  ({len(show.slides)} slides, {SLIDE_SECONDS:.0f}s stills)", flush=True)
    print(f"  {kinds}", flush=True)
    print("Stills Ken Burns. Push to play live/video/GIF. Pull away to pause.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
