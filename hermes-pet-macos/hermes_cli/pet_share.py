"""Codex Pet Share importer for the Hermes desktop pet."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from hermes_constants import get_hermes_home

CODEX_PET_SHARE_URL = "https://codex-pet-share.pages.dev"
CODEX_PET_SHARE_API_BASE = "https://ihzwckyzfcuktrljwpha.supabase.co/functions/v1/petshare"
PET_SHARE_ATLAS_SIZE = (1536, 1872)
PET_SHARE_CELL_SIZE = (192, 208)
PET_SHARE_ROWS = {
    "idle": {"row": 0, "frames": 6},
    "running-right": {"row": 1, "frames": 8},
    "running-left": {"row": 2, "frames": 8},
    "waving": {"row": 3, "frames": 4},
    "jumping": {"row": 4, "frames": 5},
    "failed": {"row": 5, "frames": 8},
    "waiting": {"row": 6, "frames": 6},
    "running": {"row": 7, "frames": 6},
    "review": {"row": 8, "frames": 6},
}
PET_SHARE_IDLE_FRAME_DURATIONS_MS = [280, 110, 110, 140, 140, 320]
PET_SHARE_IDLE_DURATION_MULTIPLIER = 6
PET_SHARE_ACTION_FRAME_TIMINGS_MS = {
    "running-right": (120, 220),
    "running-left": (120, 220),
    "waving": (140, 280),
    "jumping": (140, 280),
    "failed": (140, 240),
    "waiting": (150, 260),
    "running": (120, 220),
    "review": (150, 280),
}
SPRITE_FILES = {
    "idle": "hermes_pet_idle.png",
    "blink": "hermes_pet_blink.png",
    "working": "hermes_pet_working.png",
    "review": "hermes_pet_review.png",
}
REQUIRED_ACTIVE_FILES = [
    *SPRITE_FILES.values(),
    "manifest.json",
]
_USER_AGENT = "Hermes Pet Share Importer/0.1"
_MAX_PACKAGE_BYTES = 16 * 1024 * 1024


@dataclass(frozen=True)
class PetSharePet:
    id: str
    display_name: str
    description: str
    owner_name: str
    tags: tuple[str, ...]
    like_count: int
    view_count: int
    spritesheet_url: str
    download_url: str

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> "PetSharePet":
        return cls(
            id=str(payload.get("id") or "").strip(),
            display_name=str(payload.get("displayName") or "").strip(),
            description=str(payload.get("description") or "").strip(),
            owner_name=str(payload.get("ownerName") or "").strip(),
            tags=tuple(str(tag) for tag in payload.get("tags") or []),
            like_count=int(payload.get("likeCount") or 0),
            view_count=int(payload.get("viewCount") or 0),
            spritesheet_url=_absolute_share_url(str(payload.get("spritesheetUrl") or "")),
            download_url=_absolute_share_url(str(payload.get("downloadUrl") or "")),
        )


@dataclass(frozen=True)
class PetSharePage:
    pets: tuple[PetSharePet, ...]
    page: int
    page_size: int
    total: int
    total_pages: int


@dataclass(frozen=True)
class PetShareApplyResult:
    pet: PetSharePet
    asset_dir: Path
    manifest_path: Path
    backup_dir: Optional[Path]


@dataclass(frozen=True)
class InstalledPetAsset:
    asset_id: str
    pet_id: str
    display_name: str
    owner_name: str
    source: str
    applied_at: float
    path: Path


@dataclass(frozen=True)
class SourcePetSkin:
    source_id: str
    asset: InstalledPetAsset


def pet_assets_root() -> Path:
    return get_hermes_home() / "runtime" / "pet_assets"


def pet_assets_library_dir() -> Path:
    return pet_assets_root() / "library"


def pet_thumbnail_cache_dir() -> Path:
    return pet_assets_root() / "thumbs"


def source_pet_skins_file() -> Path:
    return pet_assets_root() / "source_skins.json"


def current_pet_asset_dir() -> Path:
    return pet_assets_root() / "current"


def current_pet_manifest_file() -> Path:
    return current_pet_asset_dir() / "manifest.json"


def active_pet_asset_dir(default_asset_dir: Path) -> Path:
    custom_dir = current_pet_asset_dir()
    if all((custom_dir / filename).exists() for filename in REQUIRED_ACTIVE_FILES):
        return custom_dir
    return default_asset_dir


def read_current_pet_manifest() -> Optional[dict[str, Any]]:
    try:
        return json.loads(current_pet_manifest_file().read_text())
    except FileNotFoundError:
        return None
    except Exception:
        return None


def clear_active_pet_assets() -> Optional[Path]:
    current = current_pet_asset_dir()
    if not current.exists():
        return None
    backup = _unique_path(pet_assets_root() / f"disabled-{_timestamp()}")
    backup.parent.mkdir(parents=True, exist_ok=True)
    current.rename(backup)
    return backup


def list_installed_pet_assets(*, limit: int = 12) -> list[InstalledPetAsset]:
    assets: list[InstalledPetAsset] = []
    library = pet_assets_library_dir()
    if library.exists():
        for item in library.iterdir():
            if item.is_dir():
                asset = _installed_asset_from_dir(item)
                if asset is not None:
                    assets.append(asset)

    current = current_pet_asset_dir()
    current_asset = _installed_asset_from_dir(current, asset_id="current") if current.exists() else None
    if current_asset is not None and all(asset.path != current for asset in assets):
        assets.append(current_asset)

    assets.sort(key=lambda asset: asset.applied_at, reverse=True)
    return assets[: max(1, min(limit, 50))]


def activate_installed_pet_asset(asset_id: str) -> InstalledPetAsset:
    clean_id = _clean_asset_id(asset_id)
    if not clean_id or clean_id == "current":
        raise ValueError("Choose a saved pet artwork entry, not the active current entry")

    source = pet_assets_library_dir() / clean_id
    asset = _installed_asset_from_dir(source, asset_id=clean_id)
    if asset is None:
        raise ValueError(f"Saved pet artwork not found: {asset_id}")

    staging = _unique_path(pet_assets_root() / f".staging-installed-{clean_id}-{_timestamp()}")
    shutil.copytree(source, staging)
    backup = _activate_staged_assets(staging)
    if backup:
        _write_activation_marker(current_pet_manifest_file())
    return asset


def list_source_pet_skins() -> list[SourcePetSkin]:
    skins: list[SourcePetSkin] = []
    for source_id, asset_id in _read_source_skin_map().items():
        asset = installed_pet_asset(asset_id)
        if asset is not None:
            skins.append(SourcePetSkin(source_id=source_id, asset=asset))
    return sorted(skins, key=lambda skin: skin.source_id)


def installed_pet_asset(asset_id: str) -> Optional[InstalledPetAsset]:
    clean_id = _clean_asset_id(asset_id)
    if not clean_id or clean_id == "current":
        return None
    return _installed_asset_from_dir(pet_assets_library_dir() / clean_id, asset_id=clean_id)


def set_source_pet_skin(source_id: str, asset_id: str) -> SourcePetSkin:
    clean_source = _clean_source_id(source_id)
    if not clean_source:
        raise ValueError("source id required")
    asset = installed_pet_asset(asset_id)
    if asset is None:
        raise ValueError(f"Saved pet artwork not found: {asset_id}")
    mapping = _read_source_skin_map()
    mapping[clean_source] = asset.asset_id
    _write_source_skin_map(mapping)
    return SourcePetSkin(source_id=clean_source, asset=asset)


def clear_source_pet_skin(source_id: str) -> bool:
    clean_source = _clean_source_id(source_id)
    if not clean_source:
        raise ValueError("source id required")
    mapping = _read_source_skin_map()
    existed = clean_source in mapping
    mapping.pop(clean_source, None)
    _write_source_skin_map(mapping)
    return existed


def source_pet_skin_asset(source_id: str, *, asset_id: Optional[str] = None) -> Optional[InstalledPetAsset]:
    if asset_id:
        return installed_pet_asset(asset_id)
    clean_source = _clean_source_id(source_id)
    if not clean_source:
        return None
    mapped = _read_source_skin_map().get(clean_source)
    if not mapped:
        return None
    return installed_pet_asset(mapped)


def list_share_pets(
    *,
    query: str = "",
    page: int = 1,
    page_size: int = 12,
    sort: str = "new",
    content: str = "safe",
) -> PetSharePage:
    params = {
        "page": str(max(1, page)),
        "pageSize": str(max(1, min(page_size, 50))),
    }
    if query.strip():
        params["q"] = query.strip()
    if sort != "new":
        params["sort"] = sort
    if content == "all":
        params["content"] = "all"
    payload = _request_json(_api_url("/api/pets", params=params))
    pets = tuple(PetSharePet.from_api(item) for item in payload.get("pets") or [])
    return PetSharePage(
        pets=pets,
        page=int(payload.get("page") or page),
        page_size=int(payload.get("pageSize") or page_size),
        total=int(payload.get("total") or len(pets)),
        total_pages=int(payload.get("totalPages") or 1),
    )


def cache_share_pet_thumbnail(pet: PetSharePet, *, size: int = 64) -> Optional[Path]:
    """Return a local PNG thumbnail for a Codex Pet Share result when possible."""
    if not pet.spritesheet_url:
        return None
    resolved_size = max(40, min(size, 96))
    key = hashlib.sha256(f"{pet.id}:{pet.spritesheet_url}:{resolved_size}".encode("utf-8")).hexdigest()[:14]
    target_dir = pet_thumbnail_cache_dir() / f"{_clean_asset_id(pet.id) or 'pet'}-{key}"
    thumbnail = target_dir / f"hermes_pet_idle_{resolved_size}.png"
    if thumbnail.exists():
        return thumbnail

    staging = _unique_path(pet_thumbnail_cache_dir() / f".staging-thumb-{_clean_asset_id(pet.id) or 'pet'}-{_timestamp()}")
    with tempfile.TemporaryDirectory(prefix="hermes-pet-thumb-") as tmp_name:
        spritesheet = Path(tmp_name) / "spritesheet.webp"
        _download_url(pet.spritesheet_url, spritesheet)
        staging.mkdir(parents=True, exist_ok=False)
        try:
            _convert_spritesheet(spritesheet, staging, size=resolved_size)
            if not (staging / f"hermes_pet_idle_{resolved_size}.png").exists():
                raise RuntimeError("thumbnail conversion did not produce an idle frame")
            if target_dir.exists():
                shutil.rmtree(staging, ignore_errors=True)
            else:
                target_dir.parent.mkdir(parents=True, exist_ok=True)
                staging.rename(target_dir)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise

    return thumbnail if thumbnail.exists() else None


def fetch_share_pet(identifier: str) -> PetSharePet:
    pet_id = extract_share_pet_id(identifier)
    if not pet_id:
        raise ValueError(f"Could not find a Codex Pet Share pet id in: {identifier}")
    payload = _request_json(_api_url(f"/api/pets/{urllib.parse.quote(pet_id)}"))
    pet_payload = payload.get("pet")
    if not isinstance(pet_payload, dict):
        raise ValueError(f"Codex Pet Share did not return pet details for {pet_id}")
    return PetSharePet.from_api(pet_payload)


def apply_share_pet(identifier: str, *, size: int = 84) -> PetShareApplyResult:
    pet = fetch_share_pet(identifier)
    if not pet.download_url:
        raise ValueError(f"Codex Pet Share pet {pet.id} has no package download URL")

    root = pet_assets_root()
    root.mkdir(parents=True, exist_ok=True)
    staging = _unique_path(root / f".staging-{pet.id}-{_timestamp()}")

    with tempfile.TemporaryDirectory(prefix="hermes-pet-share-") as tmp_name:
        tmp = Path(tmp_name)
        package_path = tmp / f"{pet.id}.codex-pet.zip"
        _download_url(pet.download_url, package_path)
        package_dir = tmp / "package"
        manifest, spritesheet = _extract_package(package_path, package_dir)
        staging.mkdir(parents=True, exist_ok=False)
        try:
            _convert_spritesheet(spritesheet, staging, size=size)
            _write_manifest(
                staging / "manifest.json",
                pet=pet,
                package_manifest=manifest,
                size=size,
            )
            backup = _activate_staged_assets(staging)
            _copy_current_to_library(pet.id)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise

    return PetShareApplyResult(
        pet=pet,
        asset_dir=current_pet_asset_dir(),
        manifest_path=current_pet_manifest_file(),
        backup_dir=backup,
    )


def extract_share_pet_id(value: str) -> str:
    raw = value.strip()
    if not raw:
        return ""

    parsed = urllib.parse.urlparse(raw)
    if parsed.scheme and parsed.netloc:
        candidates = [
            parsed.fragment,
            parsed.path,
        ]
        for candidate in candidates:
            pet_id = _pet_id_from_path(candidate)
            if pet_id:
                return pet_id
        return ""

    pet_id = _pet_id_from_path(raw)
    if pet_id:
        return pet_id
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,80}", raw):
        return raw.lower()
    return ""


def format_pet_share_page(page: PetSharePage) -> str:
    if not page.pets:
        return "No Codex Pet Share pets found."
    lines = [
        f"Codex Pet Share pets page {page.page}/{page.total_pages} ({page.total} total):",
    ]
    for pet in page.pets:
        tags = f" tags={','.join(pet.tags)}" if pet.tags else ""
        lines.append(
            f"- {pet.id}: {pet.display_name} by {pet.owner_name or '?'} "
            f"likes={pet.like_count} views={pet.view_count}{tags}"
        )
    return "\n".join(lines)


def format_current_pet_manifest() -> str:
    manifest = read_current_pet_manifest()
    if not manifest:
        return "Hermes Pet is using the bundled Hermes artwork."
    pet = manifest.get("pet") or {}
    name = pet.get("displayName") or pet.get("id") or "unknown"
    pet_id = pet.get("id") or "unknown"
    source = manifest.get("source") or CODEX_PET_SHARE_URL
    return f"Hermes Pet artwork: {name} ({pet_id}) from {source}"


def artwork_menu_payload(*, limit: int = 8) -> dict[str, Any]:
    current = read_current_pet_manifest()
    current_payload: Optional[dict[str, Any]] = None
    if current:
        pet = current.get("pet") or {}
        current_payload = {
            "id": str(pet.get("id") or ""),
            "display_name": str(pet.get("displayName") or pet.get("id") or "unknown"),
            "owner_name": str(pet.get("ownerName") or ""),
            "source": str(current.get("source") or ""),
        }
    return {
        "current": current_payload,
        "installed": [
            {
                "asset_id": asset.asset_id,
                "pet_id": asset.pet_id,
                "display_name": asset.display_name,
                "owner_name": asset.owner_name,
                "source": asset.source,
            }
            for asset in list_installed_pet_assets(limit=limit)
            if asset.asset_id != "current"
        ],
    }


def _pet_id_from_path(value: str) -> str:
    path = value.strip()
    if path.startswith("#"):
        path = path[1:]
    path = path.lstrip("/")
    patterns = [
        r"^pets/([^/?#]+)",
        r"^share/([^/?#]+)",
        r"(?:^|/)api/pets/([^/?#]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, path)
        if match:
            return urllib.parse.unquote(match.group(1)).lower()
    return ""


def _api_url(path: str, *, params: Optional[dict[str, str]] = None) -> str:
    suffix = "/" + path.lstrip("/")
    url = f"{CODEX_PET_SHARE_API_BASE}{suffix}"
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    return url


def _absolute_share_url(value: str) -> str:
    if not value:
        return ""
    if value.startswith("/api/"):
        return f"{CODEX_PET_SHARE_API_BASE}{value}"
    return urllib.parse.urljoin(CODEX_PET_SHARE_URL, value)


def _request_json(url: str) -> dict[str, Any]:
    handle = tempfile.NamedTemporaryFile(prefix="hermes-pet-share-json-", delete=False)
    path = Path(handle.name)
    handle.close()
    try:
        _download_url(url, path)
        return json.loads(path.read_text())
    finally:
        path.unlink(missing_ok=True)


def _download_url(url: str, path: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            length = response.headers.get("Content-Length")
            if length and int(length) > _MAX_PACKAGE_BYTES:
                raise ValueError(f"Codex Pet Share download is too large: {length} bytes")
            data = response.read(_MAX_PACKAGE_BYTES + 1)
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not download Codex Pet Share asset: {exc}") from exc
    if len(data) > _MAX_PACKAGE_BYTES:
        raise ValueError("Codex Pet Share download exceeded size limit")
    path.write_bytes(data)


def _extract_package(package_path: Path, output_dir: Path) -> tuple[dict[str, Any], Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(package_path) as archive:
        names = archive.namelist()
        for name in names:
            if _unsafe_zip_name(name):
                raise ValueError(f"Unsafe file in Codex Pet Share package: {name}")
        if "pet.json" not in names or "spritesheet.webp" not in names:
            raise ValueError("Codex Pet Share package must contain pet.json and spritesheet.webp")
        archive.extract("pet.json", output_dir)
        archive.extract("spritesheet.webp", output_dir)

    try:
        manifest = json.loads((output_dir / "pet.json").read_text())
    except json.JSONDecodeError as exc:
        raise ValueError("pet.json in Codex Pet Share package is invalid JSON") from exc
    return manifest, output_dir / "spritesheet.webp"


def _unsafe_zip_name(name: str) -> bool:
    path = Path(name)
    return path.is_absolute() or ".." in path.parts


def _convert_spritesheet(spritesheet: Path, output_dir: Path, *, size: int) -> None:
    binary = _compile_converter()
    subprocess.run(
        [
            str(binary),
            str(spritesheet),
            str(output_dir),
            str(max(56, min(size, 160))),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )


def _compile_converter() -> Path:
    if os.name != "posix":
        raise RuntimeError("Codex Pet Share sprite conversion is only implemented on macOS/POSIX")
    swiftc = Path("/usr/bin/swiftc")
    source = Path(__file__).with_name("assets") / "pet_share_sheet_converter.swift"
    if not swiftc.exists() or not source.exists():
        raise RuntimeError("Swift compiler is required to convert Codex Pet Share spritesheets")

    runtime_dir = get_hermes_home() / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    binary = runtime_dir / "pet_share_sheet_converter"
    try:
        needs_compile = not binary.exists() or source.stat().st_mtime > binary.stat().st_mtime
    except OSError:
        needs_compile = True
    if needs_compile:
        subprocess.run(
            [str(swiftc), str(source), "-o", str(binary)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
    return binary


def _write_manifest(
    path: Path,
    *,
    pet: PetSharePet,
    package_manifest: dict[str, Any],
    size: int,
) -> None:
    resolved_size = max(56, min(size, 160))
    animations = {
        state: _animation_manifest_for_state(state, spec, resolved_size)
        for state, spec in PET_SHARE_ROWS.items()
    }
    data = {
        "source": CODEX_PET_SHARE_URL,
        "apiBase": CODEX_PET_SHARE_API_BASE,
        "appliedAt": time.time(),
        "size": resolved_size,
        "atlasSize": f"{PET_SHARE_ATLAS_SIZE[0]}x{PET_SHARE_ATLAS_SIZE[1]}",
        "cellSize": f"{PET_SHARE_CELL_SIZE[0]}x{PET_SHARE_CELL_SIZE[1]}",
        "stateRows": PET_SHARE_ROWS,
        "animations": animations,
        "pet": {
            "id": pet.id,
            "displayName": pet.display_name,
            "description": pet.description,
            "ownerName": pet.owner_name,
            "tags": list(pet.tags),
            "spritesheetUrl": pet.spritesheet_url,
            "downloadUrl": pet.download_url,
        },
        "packageManifest": package_manifest,
    }
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def _animation_manifest_for_state(state: str, spec: dict[str, int], size: int) -> dict[str, Any]:
    frame_count = int(spec["frames"])
    base_frames = [f"animations/{state}_{index}_{size}.png" for index in range(frame_count)]
    idle_frames = [f"animations/idle_{index}_{size}.png" for index in range(PET_SHARE_ROWS["idle"]["frames"])]
    idle_durations = [
        duration * PET_SHARE_IDLE_DURATION_MULTIPLIER
        for duration in PET_SHARE_IDLE_FRAME_DURATIONS_MS
    ]

    if state == "idle":
        frames = base_frames
        frame_durations = idle_durations
        loop_start_index = 0
    else:
        normal_duration, final_duration = PET_SHARE_ACTION_FRAME_TIMINGS_MS[state]
        action_durations = [normal_duration] * max(frame_count - 1, 0) + [final_duration]
        frames = [*base_frames, *base_frames, *base_frames, *idle_frames]
        frame_durations = [*action_durations, *action_durations, *action_durations, *idle_durations]
        loop_start_index = frame_count * 3

    return {
        "row": spec["row"],
        "frames": frames,
        "durationMs": sum(frame_durations),
        "frameDurationsMs": frame_durations,
        "loopStartIndex": loop_start_index,
    }


def _activate_staged_assets(staging: Path) -> Optional[Path]:
    missing = [name for name in REQUIRED_ACTIVE_FILES if not (staging / name).exists()]
    if missing:
        raise RuntimeError(f"Converted Codex Pet Share assets are incomplete: {', '.join(missing)}")

    current = current_pet_asset_dir()
    backup: Optional[Path] = None
    if current.exists():
        backup = _unique_path(pet_assets_root() / f"previous-{_timestamp()}")
        current.rename(backup)
    staging.rename(current)
    return backup


def _copy_current_to_library(pet_id: str) -> Optional[Path]:
    current = current_pet_asset_dir()
    if not current.exists():
        return None
    library = pet_assets_library_dir()
    library.mkdir(parents=True, exist_ok=True)
    asset_id = f"{_clean_asset_id(pet_id) or 'pet'}-{_timestamp()}"
    target = _unique_path(library / asset_id)
    shutil.copytree(current, target)
    return target


def _installed_asset_from_dir(path: Path, *, asset_id: Optional[str] = None) -> Optional[InstalledPetAsset]:
    if not all((path / filename).exists() for filename in REQUIRED_ACTIVE_FILES):
        return None
    try:
        manifest = json.loads((path / "manifest.json").read_text())
    except Exception:
        return None
    pet = manifest.get("pet") if isinstance(manifest, dict) else None
    if not isinstance(pet, dict):
        return None
    return InstalledPetAsset(
        asset_id=asset_id or path.name,
        pet_id=str(pet.get("id") or path.name),
        display_name=str(pet.get("displayName") or pet.get("id") or path.name),
        owner_name=str(pet.get("ownerName") or ""),
        source=str(manifest.get("source") or ""),
        applied_at=float(manifest.get("appliedAt") or 0.0),
        path=path,
    )


def _write_activation_marker(manifest_path: Path) -> None:
    try:
        data = json.loads(manifest_path.read_text())
        data["appliedAt"] = time.time()
        manifest_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    except Exception:
        return


def _clean_asset_id(value: str) -> str:
    raw = str(value or "").strip().lower()
    clean = "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in raw)
    return clean.strip("._-")[:96]


def _clean_source_id(value: str) -> str:
    raw = str(value or "").strip()
    clean = "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in raw)
    return clean.strip("._-")[:96]


def _read_source_skin_map() -> dict[str, str]:
    try:
        data = json.loads(source_pet_skins_file().read_text())
    except FileNotFoundError:
        return {}
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    skins = data.get("skins")
    if not isinstance(skins, dict):
        return {}
    cleaned: dict[str, str] = {}
    for source_id, asset_id in skins.items():
        clean_source = _clean_source_id(str(source_id))
        clean_asset = _clean_asset_id(str(asset_id))
        if clean_source and clean_asset:
            cleaned[clean_source] = clean_asset
    return cleaned


def _write_source_skin_map(mapping: dict[str, str]) -> Path:
    path = source_pet_skins_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    clean = {
        _clean_source_id(source_id): _clean_asset_id(asset_id)
        for source_id, asset_id in mapping.items()
        if _clean_source_id(source_id) and _clean_asset_id(asset_id)
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"skins": clean, "updatedAt": time.time()}, indent=2, sort_keys=True) + "\n")
    tmp.replace(path)
    return path


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    for index in range(2, 1000):
        candidate = path.with_name(f"{path.name}-{index}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Could not allocate unique path near {path}")


def _timestamp() -> str:
    return time.strftime("%Y%m%d-%H%M%S")
