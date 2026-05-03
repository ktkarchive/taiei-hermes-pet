import json
import zipfile
from pathlib import Path

import pytest

import hermes_cli.pet_share as pet_share
from hermes_cli.pet_share import (
    activate_installed_pet_asset,
    PetSharePet,
    artwork_menu_payload,
    active_pet_asset_dir,
    apply_share_pet,
    cache_share_pet_thumbnail,
    clear_active_pet_assets,
    current_pet_asset_dir,
    extract_share_pet_id,
    format_current_pet_manifest,
    list_source_pet_skins,
    list_share_pets,
    set_source_pet_skin,
)


def test_extract_share_pet_id_accepts_site_and_api_urls():
    assert extract_share_pet_id("shiroko") == "shiroko"
    assert extract_share_pet_id("https://codex-pet-share.pages.dev/#/pets/mimi") == "mimi"
    assert extract_share_pet_id("https://codex-pet-share.pages.dev/share/maiko") == "maiko"
    assert (
        extract_share_pet_id(
            "https://ihzwckyzfcuktrljwpha.supabase.co/functions/v1/petshare/api/pets/anatoly/download?v=1"
        )
        == "anatoly"
    )


def test_list_share_pets_normalizes_relative_urls(monkeypatch):
    def fake_request_json(url):
        assert "/api/pets?" in url
        return {
            "pets": [
                {
                    "id": "mimi",
                    "displayName": "Mimi",
                    "description": "A tiny companion.",
                    "ownerName": "plutoless",
                    "tags": ["cute"],
                    "likeCount": 2,
                    "viewCount": 3,
                    "spritesheetUrl": "/api/pets/mimi/spritesheet?v=1",
                    "downloadUrl": "/api/pets/mimi/download?v=1",
                }
            ],
            "page": 1,
            "pageSize": 1,
            "total": 1,
            "totalPages": 1,
        }

    monkeypatch.setattr(pet_share, "_request_json", fake_request_json)

    page = list_share_pets(query="mi", page_size=1)

    assert page.pets[0].id == "mimi"
    assert page.pets[0].download_url.startswith(pet_share.CODEX_PET_SHARE_API_BASE)


def test_cache_share_pet_thumbnail_downloads_and_converts_once(tmp_path, monkeypatch):
    monkeypatch.setattr(pet_share, "get_hermes_home", lambda: tmp_path)
    calls = {"download": 0, "convert": 0}
    pet = PetSharePet(
        id="mimi",
        display_name="Mimi",
        description="A tiny companion.",
        owner_name="plutoless",
        tags=("cute",),
        like_count=2,
        view_count=3,
        spritesheet_url="https://example.invalid/mimi.webp?v=1",
        download_url="https://example.invalid/download.zip",
    )

    def fake_download(url, path):
        calls["download"] += 1
        path.write_bytes(b"webp")

    def fake_convert(spritesheet, output_dir, *, size):
        calls["convert"] += 1
        assert size == 64
        (output_dir / "hermes_pet_idle_64.png").write_bytes(b"png")

    monkeypatch.setattr(pet_share, "_download_url", fake_download)
    monkeypatch.setattr(pet_share, "_convert_spritesheet", fake_convert)

    first = cache_share_pet_thumbnail(pet, size=64)
    second = cache_share_pet_thumbnail(pet, size=64)

    assert first == second
    assert first is not None and first.exists()
    assert calls == {"download": 1, "convert": 1}


def test_active_asset_dir_prefers_complete_runtime_assets(tmp_path, monkeypatch):
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    monkeypatch.setattr(pet_share, "get_hermes_home", lambda: tmp_path)

    assert active_pet_asset_dir(bundled) == bundled

    current = current_pet_asset_dir()
    current.mkdir(parents=True)
    for filename in pet_share.REQUIRED_ACTIVE_FILES:
        (current / filename).write_bytes(b"png")

    assert active_pet_asset_dir(bundled) == current


def test_clear_active_pet_assets_moves_current_without_deleting(tmp_path, monkeypatch):
    monkeypatch.setattr(pet_share, "get_hermes_home", lambda: tmp_path)
    current = current_pet_asset_dir()
    current.mkdir(parents=True)
    (current / "manifest.json").write_text("{}")

    backup = clear_active_pet_assets()

    assert backup is not None
    assert backup.exists()
    assert not current.exists()
    assert backup.name.startswith("disabled-")


def test_apply_share_pet_extracts_package_and_writes_manifest(tmp_path, monkeypatch):
    package = tmp_path / "mimi.codex-pet.zip"
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr(
            "pet.json",
            json.dumps({
                "id": "mimi",
                "displayName": "Mimi",
                "description": "A tiny companion.",
                "spritesheetPath": "spritesheet.webp",
            }),
        )
        archive.writestr("spritesheet.webp", b"webp")

    pet = PetSharePet(
        id="mimi",
        display_name="Mimi",
        description="A tiny companion.",
        owner_name="plutoless",
        tags=("cute",),
        like_count=2,
        view_count=3,
        spritesheet_url="https://example.invalid/spritesheet.webp",
        download_url="https://example.invalid/download.zip",
    )

    def fake_fetch(identifier):
        assert identifier == "mimi"
        return pet

    def fake_download(url, path):
        path.write_bytes(package.read_bytes())

    def fake_convert(spritesheet, output_dir, *, size):
        assert spritesheet.name == "spritesheet.webp"
        assert size == 84
        for filename in pet_share.REQUIRED_ACTIVE_FILES:
            (output_dir / filename).write_bytes(b"png")

    monkeypatch.setattr(pet_share, "get_hermes_home", lambda: tmp_path)
    monkeypatch.setattr(pet_share, "fetch_share_pet", fake_fetch)
    monkeypatch.setattr(pet_share, "_download_url", fake_download)
    monkeypatch.setattr(pet_share, "_convert_spritesheet", fake_convert)

    result = apply_share_pet("mimi", size=84)

    assert result.pet.id == "mimi"
    assert result.asset_dir == current_pet_asset_dir()
    manifest = json.loads(result.manifest_path.read_text())
    assert manifest["pet"]["id"] == "mimi"
    assert manifest["animations"]["idle"]["loopStartIndex"] == 0
    assert manifest["animations"]["idle"]["frameDurationsMs"] == [1680, 660, 660, 840, 840, 1920]
    assert manifest["animations"]["running-left"]["loopStartIndex"] == 24
    assert len(manifest["animations"]["running-left"]["frames"]) == 30
    assert (tmp_path / "runtime" / "pet_assets" / "library").exists()
    assert artwork_menu_payload()["installed"][0]["pet_id"] == "mimi"
    assert "Mimi" in format_current_pet_manifest()


def test_activate_installed_pet_asset_switches_current_without_deleting(tmp_path, monkeypatch):
    monkeypatch.setattr(pet_share, "get_hermes_home", lambda: tmp_path)
    library = tmp_path / "runtime" / "pet_assets" / "library" / "mimi-20260503"
    library.mkdir(parents=True)
    for filename in pet_share.REQUIRED_ACTIVE_FILES:
        path = library / filename
        if filename == "manifest.json":
            path.write_text(json.dumps({
                "appliedAt": 1,
                "source": "test",
                "pet": {"id": "mimi", "displayName": "Mimi", "ownerName": "tester"},
            }))
        else:
            path.write_bytes(b"png")
    current = current_pet_asset_dir()
    current.mkdir(parents=True)
    for filename in pet_share.REQUIRED_ACTIVE_FILES:
        path = current / filename
        if filename == "manifest.json":
            path.write_text(json.dumps({
                "appliedAt": 0,
                "source": "test",
                "pet": {"id": "old", "displayName": "Old"},
            }))
        else:
            path.write_bytes(b"old")

    asset = activate_installed_pet_asset("mimi-20260503")

    assert asset.pet_id == "mimi"
    assert json.loads((current / "manifest.json").read_text())["pet"]["id"] == "mimi"
    assert any(path.name.startswith("previous-") for path in current.parent.iterdir())


def test_source_pet_skin_maps_source_to_installed_artwork(tmp_path, monkeypatch):
    monkeypatch.setattr(pet_share, "get_hermes_home", lambda: tmp_path)
    library = tmp_path / "runtime" / "pet_assets" / "library" / "mimi-20260503"
    library.mkdir(parents=True)
    for filename in pet_share.REQUIRED_ACTIVE_FILES:
        path = library / filename
        if filename == "manifest.json":
            path.write_text(json.dumps({
                "appliedAt": 1,
                "source": "test",
                "pet": {"id": "mimi", "displayName": "Mimi", "ownerName": "tester"},
            }))
        else:
            path.write_bytes(b"png")

    skin = set_source_pet_skin("remote lab mac", "mimi-20260503")

    assert skin.source_id == "remote-lab-mac"
    assert skin.asset.pet_id == "mimi"
    assert list_source_pet_skins()[0].source_id == "remote-lab-mac"


def test_extract_package_rejects_zip_slip(tmp_path):
    package = tmp_path / "bad.zip"
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("../pet.json", "{}")
        archive.writestr("spritesheet.webp", b"webp")

    with pytest.raises(ValueError, match="Unsafe file"):
        pet_share._extract_package(package, tmp_path / "out")
