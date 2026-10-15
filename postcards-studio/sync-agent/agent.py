"""Pull-only relay from Postcards Studio to a local/NAS release directory."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import signal
import tempfile
import time
from pathlib import Path
from urllib.parse import quote

import httpx


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_temp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    os.close(fd)
    temp = Path(raw_temp)
    try:
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), "utf-8")
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


class Agent:
    def __init__(self, server: str, token: str, destination: Path, application: str = ""):
        self.server = server.rstrip("/")
        self.destination = destination
        self.destination.mkdir(parents=True, exist_ok=True)
        self.application = application.rstrip("/")
        self.client = httpx.Client(headers={"X-Sync-Token": token}, timeout=120, follow_redirects=True)

    def current_id(self) -> str | None:
        try:
            return json.loads((self.destination / "current.json").read_text("utf-8")).get("releaseId")
        except Exception:
            return None

    def sync_once(self) -> bool:
        response = self.client.get(f"{self.server}/api/sync/latest")
        if response.status_code == 404:
            print("[sync] опубликованных релизов пока нет", flush=True)
            return False
        response.raise_for_status()
        manifest = response.json()
        release_id = manifest["releaseId"]
        final = self.destination / release_id
        if self.current_id() == release_id and final.is_dir():
            return False
        staging = self.destination / f".{release_id}.staging"
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True)
        try:
            for item in manifest["files"]:
                target = staging / item["name"]
                url = f"{self.server}/api/sync/releases/{quote(release_id)}/{quote(item['name'])}"
                with self.client.stream("GET", url) as download:
                    download.raise_for_status()
                    with target.open("wb") as output:
                        for chunk in download.iter_bytes(1024 * 1024):
                            output.write(chunk)
                if target.stat().st_size != int(item["size"]):
                    raise RuntimeError(f"неверный размер {item['name']}")
                if sha256(target) != item["sha256"]:
                    raise RuntimeError(f"неверная SHA-256 {item['name']}")
            (staging / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), "utf-8")
            if final.exists():
                shutil.rmtree(staging)
            else:
                os.replace(staging, final)
            if self.application:
                installed = httpx.post(f"{self.application}/api/media/release",
                                       json={"path": str(final)}, timeout=120)
                installed.raise_for_status()
            atomic_json(self.destination / "current.json", manifest)
            print(f"[sync] установлен {release_id}", flush=True)
            return True
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Postcards Studio NAS sync agent")
    server_default = os.environ.get("POSTCARDS_SERVER", "")
    token_default = os.environ.get("POSTCARDS_SYNC_TOKEN", "")
    destination_default = os.environ.get("POSTCARDS_DESTINATION", "")
    parser.add_argument("--server", default=server_default, required=not server_default)
    parser.add_argument("--token", default=token_default)
    parser.add_argument("--token-file", type=Path)
    parser.add_argument("--destination", type=Path,
                        default=Path(destination_default) if destination_default else None,
                        required=not destination_default)
    parser.add_argument("--interval", type=float, default=float(os.environ.get("POSTCARDS_INTERVAL", "30")))
    parser.add_argument("--application", default=os.environ.get("POSTCARDS_APPLICATION", "http://127.0.0.1:8787"),
                        help="Локальный Postcards API; пустая строка отключает установку")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    token = args.token
    if not token and args.token_file:
        token = args.token_file.read_text("utf-8").strip()
    if not token:
        parser.error("задайте --token, --token-file или POSTCARDS_SYNC_TOKEN")
    agent = Agent(args.server, token, args.destination, args.application)
    if args.once:
        agent.sync_once()
        return
    running = True

    def stop(*_):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, stop)
    while running:
        try:
            agent.sync_once()
        except Exception as exc:
            print(f"[sync] ошибка: {exc}", flush=True)
        for _ in range(max(1, int(args.interval * 2))):
            if not running:
                break
            time.sleep(.5)


if __name__ == "__main__":
    main()
