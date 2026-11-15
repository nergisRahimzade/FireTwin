"""Provision/verify a portable RAG bundle; weights may download only during prepare.

Run: uv run python docker/rag_bundle.py prepare --output .local/rag-bundle
Runtime copies the immutable store into a writable container directory after verification.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BUNDLE_FORMAT = 1


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_manifest(root: Path) -> None:
    files = {
        p.relative_to(root).as_posix(): sha256(p) for p in sorted(root.rglob("*")) if p.is_file()
    }
    manifest = {"format": BUNDLE_FORMAT, "embedding": "minilm", "files": files}
    (root / "bundle.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")


def verify_bundle(root: Path) -> str:
    manifest_path = root / "bundle.json"
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("format") != BUNDLE_FORMAT or manifest.get("embedding") != "minilm":
        raise ValueError("unsupported RAG bundle format/provider")
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise ValueError("bundle has no file manifest")
    required = {
        "store/CURRENT.json",
        *(
            "model/onnx/" + n
            for n in (
                "config.json",
                "model.onnx",
                "special_tokens_map.json",
                "tokenizer_config.json",
                "tokenizer.json",
                "vocab.txt",
            )
        ),
    }
    if not required.issubset(files):
        raise ValueError("bundle is missing the index pointer or model files")
    if any(p.is_symlink() for p in root.rglob("*")):
        raise ValueError("bundle contains symbolic links")
    actual = {
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if p.is_file() and p != manifest_path
    }
    if actual != set(files):
        raise ValueError("bundle file inventory differs from its manifest")
    for name, expected in files.items():
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("bundle manifest contains an unsafe path")
        path = root / relative
        if not path.resolve().is_relative_to(root.resolve()) or sha256(path) != expected:
            raise ValueError(f"RAG bundle file verification failed: {name}")
    return sha256(manifest_path)


def check_output_location(output: Path, repo: Path) -> None:
    """Refuse a bundle folder inside the repository that Git would track.

    The extracted model alone is ~87 MB, under GitHub's 100 MB limit, so nothing else would stop
    a `git add` from committing it. Outside the repository, or without Git, there is nothing to do.
    """
    output = output.resolve()
    if not output.is_relative_to(repo.resolve()) or not (repo / ".git").exists():
        return
    # Ask about a file inside the folder: the ignore rules match the folder as a directory,
    # which a path that doesn't exist yet can't show on its own.
    probe = output / "bundle.json"
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "check-ignore", "-q", "--", str(probe)], capture_output=True
        )
    except FileNotFoundError:
        return  # no git installed
    if result.returncode == 1:  # 0 = ignored, 1 = would be tracked; other exits are errors.
        raise ValueError(
            f"{output} is inside the repository but not git-ignored; use "
            ".local/rag-bundle-<name> or a folder outside the repository"
        )
    if result.returncode != 0:
        raise RuntimeError(
            f"cannot verify that {output} is git-ignored (git exit {result.returncode}); "
            "fix the Git error or choose a folder outside the repository"
        )


def prepare(output: Path, cache_source: Path | None = None) -> None:
    """Build in a new sibling directory; never overwrite an existing bundle.

    Ingest runs in a child so Chroma/SQLite handles are closed before hashing/copying.
    This is deliberate setup-time network use, not API-query-time provisioning.
    """
    check_output_location(output, Path(__file__).resolve().parents[1])
    if output.exists():
        raise ValueError("output already exists; choose a new bundle directory")
    output.parent.mkdir(parents=True, exist_ok=True)
    candidate = Path(tempfile.mkdtemp(prefix=f".{output.name}-", dir=output.parent))
    try:
        root = Path(__file__).resolve().parents[1]
        if cache_source is not None:
            source = cache_source / "onnx"
            target = candidate / "model/onnx"
            target.mkdir(parents=True)
            for name in (
                "config.json",
                "model.onnx",
                "special_tokens_map.json",
                "tokenizer_config.json",
                "tokenizer.json",
                "vocab.txt",
            ):
                if not (source / name).is_file() or (source / name).stat().st_size == 0:
                    raise ValueError(f"source model cache is incomplete: {name}")
                shutil.copy2(source / name, target / name)
        subprocess.run(
            [
                sys.executable,
                str(root / "ml/ingest_rag.py"),
                "--persist-dir",
                str(candidate / "store"),
                "--embedding",
                "minilm",
                "--cache-dir",
                str(candidate / "model"),
            ],
            cwd=root,
            check=True,
        )
        # Runtime needs the extracted files, not a duplicate downloaded archive.
        (candidate / "model/onnx.tar.gz").unlink(missing_ok=True)
        # The non-root API user must be able to read the host-mounted bundle.
        for path in candidate.rglob("*"):
            path.chmod(0o755 if path.is_dir() else 0o644)
        candidate.chmod(0o755)
        write_manifest(candidate)
        verify_bundle(candidate)
        # Destination must remain absent; use rename rather than replacing an existing bundle.
        if output.exists():
            raise ValueError("output was created concurrently; choose another directory")
        candidate.rename(output)
    finally:
        if candidate.exists():
            shutil.rmtree(candidate, ignore_errors=True)
    print(f"RAG bundle ready: {output}")


def stage_bundle(bundle: Path, runtime: Path) -> bool:
    """Verify source and copy into writable storage once; never mutate the source bundle."""
    if not (bundle / "bundle.json").is_file():
        if runtime.exists():
            raise ValueError("bundle missing with an existing runtime copy; recreate the container")
        return False
    identity = verify_bundle(bundle)
    marker = runtime / ".bundle-sha256"
    if runtime.exists():
        if not marker.is_file() or marker.read_text().strip() != identity:
            raise ValueError("runtime copy belongs to a different bundle; recreate the container")
        return True
    runtime.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".rag-runtime-", dir=runtime.parent))
    try:
        copy = temporary / "store"
        shutil.copytree(bundle / "store", copy)
        (copy / ".bundle-sha256").write_text(identity)
        copy.rename(runtime)
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=["prepare", "verify"])
    parser.add_argument("--output", type=Path, default=Path(".local/rag-bundle"))
    parser.add_argument(
        "--cache-source",
        type=Path,
        help="reuse an extracted MiniLM cache without downloading weights",
    )
    args = parser.parse_args()
    if args.action == "prepare":
        prepare(args.output.resolve(), args.cache_source)
    else:
        verify_bundle(args.output.resolve())
        print("RAG bundle verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
