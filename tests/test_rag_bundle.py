"""Portable bundle checks use synthetic files and no model/network/Docker engine."""

import json
import os
from pathlib import Path
from runpy import run_path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = run_path(str(ROOT / "docker/rag_bundle.py"))


@pytest.fixture
def bundle(tmp_path):
    root = tmp_path / "bundle"
    (root / "store").mkdir(parents=True)
    (root / "store/CURRENT.json").write_text(json.dumps({"generation": "a" * 32}))
    for name in (
        "config.json",
        "model.onnx",
        "special_tokens_map.json",
        "tokenizer_config.json",
        "tokenizer.json",
        "vocab.txt",
    ):
        p = root / "model/onnx" / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("synthetic fixture, not actual weights")
    BUNDLE["write_manifest"](root)
    return root


def test_bundle_is_verified_and_copied_to_writable_runtime(bundle, tmp_path):
    before = {p.relative_to(bundle): p.read_bytes() for p in bundle.rglob("*") if p.is_file()}
    target = tmp_path / "runtime"
    assert BUNDLE["stage_bundle"](bundle, target)
    (target / "runtime-only.sqlite").write_text("synthetic runtime write")
    assert not (bundle / "store/runtime-only.sqlite").exists()
    assert {
        p.relative_to(bundle): p.read_bytes() for p in bundle.rglob("*") if p.is_file()
    } == before
    assert BUNDLE["stage_bundle"](bundle, target)  # same bundle on a restart


@pytest.mark.parametrize("change", ["corrupt", "extra", "missing"])
def test_bundle_rejects_corruption_or_changed_inventory(bundle, change):
    file = bundle / "model/onnx/model.onnx"
    if change == "corrupt":
        file.write_text("changed synthetic file")
    elif change == "missing":
        file.unlink()
    else:
        (bundle / "extra.txt").write_text("not in manifest")
    with pytest.raises(ValueError, match="verification failed|inventory"):
        BUNDLE["verify_bundle"](bundle)


def test_missing_manifest_does_not_create_an_empty_runtime_index(tmp_path):
    runtime = tmp_path / "runtime"
    assert not BUNDLE["stage_bundle"](tmp_path / "missing", runtime)
    assert not runtime.exists()


def test_existing_unmanaged_index_is_never_overwritten(bundle, tmp_path):
    target = tmp_path / "existing"
    target.mkdir()
    (target / "keep.txt").write_text("existing data")
    with pytest.raises(ValueError, match="different bundle"):
        BUNDLE["stage_bundle"](bundle, target)
    assert (target / "keep.txt").read_text() == "existing data"


def test_prepare_refuses_existing_bundle_before_launching_ingest(bundle, monkeypatch):
    def forbid(*args, **kwargs):
        pytest.fail("existing bundle was rebuilt")

    monkeypatch.setattr(BUNDLE["subprocess"], "run", forbid)
    with pytest.raises(ValueError, match="already exists"):
        BUNDLE["prepare"](bundle)


def test_prepare_failure_leaves_no_published_bundle(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("synthetic preparation failure")

    monkeypatch.setattr(BUNDLE["subprocess"], "run", fail)
    target = tmp_path / "bundle"
    with pytest.raises(RuntimeError, match="synthetic"):
        BUNDLE["prepare"](target)
    assert not target.exists()


@pytest.mark.skipif(os.name != "posix", reason="symlink permissions differ on Windows")
def test_bundle_rejects_symlinks_even_if_the_file_hash_matches(bundle, tmp_path):
    external = tmp_path / "external"
    external.write_text("synthetic")
    p = bundle / "store/link"
    p.symlink_to(external)
    BUNDLE["write_manifest"](bundle)
    with pytest.raises(ValueError, match="symbolic links"):
        BUNDLE["verify_bundle"](bundle)


def test_incomplete_cache_source_never_starts_downloading(tmp_path, monkeypatch):
    def forbid(*args, **kwargs):
        pytest.fail("incomplete supplied cache started an ingest/download")

    monkeypatch.setattr(BUNDLE["subprocess"], "run", forbid)
    target = tmp_path / "bundle"
    with pytest.raises(ValueError, match="source model cache is incomplete"):
        BUNDLE["prepare"](target, tmp_path / "incomplete-cache")
    assert not target.exists()


@pytest.mark.parametrize("name", ["rag-bundle", "rag-bundle-demo"])
def test_prepare_accepts_git_ignored_bundle_folders(name):
    # RAG-005: the documented .local/rag-bundle* names are ignored, so prepare allows them.
    BUNDLE["check_output_location"](ROOT / ".local" / name, ROOT)


@pytest.mark.parametrize("folder", [".local/demo-bundle", "bundles/rag"])
def test_prepare_refuses_tracked_folders_inside_the_repo(folder):
    # RAG-005: anywhere else in the repo, `git add` would pick up the ~87 MB model.
    with pytest.raises(ValueError, match="not git-ignored"):
        BUNDLE["check_output_location"](ROOT / folder, ROOT)


def test_prepare_allows_folders_outside_the_repo(tmp_path):
    BUNDLE["check_output_location"](tmp_path / "rag-bundle", ROOT)


def test_prepare_refuses_a_tracked_folder_before_creating_anything():
    # The check runs first: no bundle folder, temporary build folder or ingest run is created.
    target = ROOT / ".local/demo-bundle"
    with pytest.raises(ValueError, match="not git-ignored"):
        BUNDLE["prepare"](target)
    assert not target.exists()
    assert not list(target.parent.glob(".demo-bundle-*")) if target.parent.exists() else True
