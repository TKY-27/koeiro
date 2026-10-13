"""Build the Linux distribution in Docker (PyInstaller only bundles for its own OS).

Two artifacts, matching the Windows pair:

* ``koeiro-<tag>-linux-app.tar.gz``          the frozen GUI (Koeiro + _internal)
* ``koeiro-<tag>-linux-ai-pack-<n>.tar.gz``  the frozen worker and the model trees,
  split so every file stays under BOOTH's 1.2 GB per-file cap

Linux has no Inno Setup, so an "installer" here is a folder you unpack into. The app
bundle is a directory holding ``Koeiro`` beside ``_internal``, which is exactly the
layout ``src/runtime_paths.py`` expects, and an AI pack unpacks into the same folder.

    .venv\\Scripts\\python tools\\build_linux_bundles.py --tag v0.13.3 --kind all

The build happens inside the container's own filesystem: an NTFS bind mount is far too
slow for a 1 GB bundle, so only the finished tar is streamed out to the host.
"""
import argparse
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
from build_ai_pack import (DEFAULT_VOICE, check_stage, stage_pack)  # noqa: E402
from build_windows_setup import BOOTH_FILE_LIMIT, SetupError, sha256_of, version_of  # noqa: E402

APP_IMAGE = "python:3.12-bookworm"
WORKER_IMAGE = "python:3.11-bookworm"
PIP_CACHE = "koeiro-pip-cache"
TORCH_INDEX = "https://download.pytorch.org/whl/cpu"
# The frozen GUI still needs the system PortAudio (sounddevice loads libportaudio at
# runtime) and Qt's own libraries; verified by running the bundle offscreen in a bare
# Debian container. README's Linux install steps already ask for libportaudio2.
RUNTIME_APT = ["libportaudio2", "libgl1", "libegl1", "libglib2.0-0", "libxkbcommon0",
               "libdbus-1-3", "fontconfig"]
INSTALL_SCRIPT = """#!/bin/sh
# Unpack the Koeiro AI voice pack into the folder that holds the Koeiro binary.
#   sh install-ai-pack.sh /path/to/Koeiro-linux
set -e
target=${1:?usage: install-ai-pack.sh <folder holding the Koeiro binary>}
[ -f "$target/Koeiro" ] || { echo "Koeiro not found in $target - install the app first"; exit 1; }
here=$(cd "$(dirname "$0")" && pwd)
if ls "$here"/*checksums.txt >/dev/null 2>&1; then
  (cd "$here" && sha256sum -c ./*checksums.txt)
fi
for part in "$here"/koeiro-*-linux-ai-pack-*.tar.gz; do
  echo "unpacking $(basename "$part") -> $target"
  tar -xzf "$part" -C "$target"
done
echo "done. Start with: $target/Koeiro"
"""


def docker(arguments, root, out=None, timeout=5400):
    command = ["docker", *arguments]
    stream = open(out, "wb") if out else subprocess.DEVNULL
    try:
        completed = subprocess.run(command, cwd=root, stdout=stream,
                                   stderr=subprocess.PIPE, timeout=timeout,
                                   encoding="utf-8", errors="replace")
    finally:
        if out:
            stream.close()
    if completed.returncode != 0:
        raise SetupError("docker に失敗:\n" + (completed.stderr or "")[-2500:])
    return completed.stderr or ""


def require_docker(root):
    try:
        subprocess.run(["docker", "version", "--format", "{{.ServerVersion}}"],
                       cwd=root, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as error:
        raise SetupError(f"docker が使えません（Linux ビルドには Docker Desktop が要ります）: {error}") from error


def container(kind, root, out_path, timeout):
    """Run one PyInstaller build in Docker and stream the bundle tar to out_path."""
    script = _script(kind)
    image = APP_IMAGE if kind == "app" else WORKER_IMAGE
    name = "Koeiro" if kind == "app" else "KoeiroWorker"
    # A fixed, own-suffixed name: nothing here ever touches another container.
    container_name = f"koeiro-linux-{kind}"
    subprocess.run(["docker", "rm", "-f", container_name], cwd=root,
                   capture_output=True, timeout=180)
    arguments = ["run", "--rm", "--name", container_name,
                 "-v", f"{root}:/work", "-w", "/work",
                 "-v", f"{PIP_CACHE}:/root/.cache/pip", image, "bash", "-ec", script]
    log = docker(arguments, root, out_path, timeout=timeout)
    with open(out_path, "rb") as stream:
        header = stream.read(2)
    if header != b"\x1f\x8b" or Path(out_path).stat().st_size < 1024 * 1024:
        raise SetupError(f"{name}.tar.gz が出来ません（先頭 {header!r}）:\n{log[-2000:]}")
    return log


def _script(kind):
    """What runs inside the container: venv, deps, PyInstaller, then tar to stdout.

    Every step but the final tar writes to stderr: stdout is the artifact stream, and
    one stray "Selecting previously unselected package" line from apt corrupts the
    gzip member headers behind it.
    """
    apt = ("apt-get update -qq && apt-get install -y -qq " + " ".join(RUNTIME_APT)
           + " 1>&2")
    if kind == "app":
        build = ("python -m venv /tmp/gui 1>&2\n"
                 "/tmp/gui/bin/pip install --no-cache-dir -q -r requirements.txt "
                 "pyinstaller 1>&2\n"
                 "/tmp/gui/bin/python -m PyInstaller Koeiro.spec --noconfirm --log-level WARN "
                 "--distpath /tmp/dist --workpath /tmp/pb 1>&2\n")
    else:
        # Install straight from the AI environment's own lock, with the CPU torch index
        # as an extra index: the lock pins `torch==2.5.1+cpu`, which plain PyPI does not
        # carry, and installing an unpinned torch first would pull a newer build that the
        # lock then cannot satisfy. Windows-only pins are dropped by the same helper
        # setup_release uses.
        build = ("python -m venv /tmp/ai 1>&2\n"
                 "python -c \"import sys; sys.path.insert(0, '/work');"
                 "from tools.setup_release import filter_lock_lines;"
                 "open('/tmp/lock.txt','w').write(filter_lock_lines("
                 "open('/work/vc_models/meanvc2/requirements.lock.txt',"
                 "encoding='utf-8').read(), False))\" 1>&2\n"
                 "/tmp/ai/bin/pip install --no-cache-dir -q -r /tmp/lock.txt "
                 f"--extra-index-url {TORCH_INDEX} 1>&2\n"
                 "/tmp/ai/bin/pip install --no-cache-dir -q pyinstaller 1>&2\n"
                 "/tmp/ai/bin/python -m PyInstaller KoeiroWorker.spec --noconfirm "
                 "--log-level WARN --distpath /tmp/dist --workpath /tmp/pb 1>&2\n")
    name = "Koeiro" if kind == "app" else "KoeiroWorker"
    # The build root marker records where this machine's tree sits: meaningless, and
    # actively wrong, on a distribution (runtime_paths then looks for a Windows path).
    return (f"{apt}\n{build}"
            f"rm -f /tmp/dist/{name}/_internal/koeiro-root.txt "
            f"/tmp/dist/{name}/_internal_worker/koeiro-root.txt\n"
            f"ls -la /tmp/dist/{name} | head -4 >&2\n"
            f"du -sh /tmp/dist/{name} >&2\n"
            f"tar -C /tmp/dist -czf - {name}\n")


def tar_stream(tar_path, source_dir, arcname, members=None):
    """Write one gzip tar of `source_dir` (or selected members) with a fixed root name."""
    source_dir = Path(source_dir)
    with tarfile.open(tar_path, "w:gz") as bundle:
        if members is None:
            bundle.add(str(source_dir), arcname=arcname)
        else:
            for relative in members:
                path = source_dir / relative
                if not path.exists():
                    raise SetupError(f"tar の対象がありません: {relative}")
                bundle.add(str(path), arcname=(Path(arcname) / relative).as_posix())
    return tar_path


def build_app(root, tag, out_dir, timeout=5400):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"koeiro-{tag}-linux-app.tar.gz"
    container("app", root, target, timeout)
    return target


def extract(tar_path, destination):
    destination = Path(destination)
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    with tarfile.open(tar_path, "r:gz") as bundle:
        bundle.extractall(destination, filter="data")
    return destination


def build_pack(root, tag, worker_bundle, out_dir, stage_dir, voice=DEFAULT_VOICE):
    """Stage the Linux AI pack (shared allowlist with the Windows builder) into tars."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stage, count, total = stage_pack(root, worker_bundle, stage_dir, voice=voice, tag=tag,
                                     worker_exe="KoeiroWorker", contents_dir="_internal_worker")
    check_stage(stage, voice=voice, worker_exe="KoeiroWorker", contents_dir="_internal_worker")
    script = stage / "install-ai-pack.sh"
    script.write_text(INSTALL_SCRIPT, "utf-8", newline="\n")
    script.chmod(0o755)
    runtime_members = ("KoeiroWorker", "_internal_worker", "install-ai-pack.sh",
                       "koeiro-ai-pack.json", "LICENSE.txt", "README.md",
                       "THIRD_PARTY_NOTICES.md")
    first = out_dir / f"koeiro-{tag}-linux-ai-pack-1.tar.gz"
    second = out_dir / f"koeiro-{tag}-linux-ai-pack-2.tar.gz"
    tar_stream(first, stage, ".", members=runtime_members)
    tar_stream(second, stage, ".", members=("vc_models", "models"))
    for part in (first, second):
        if part.stat().st_size > BOOTH_FILE_LIMIT:
            raise SetupError(f"{part.name} が {BOOTH_FILE_LIMIT} バイト超（BOOTH の1ファイル上限）")
    return [first, second], {"files": count, "raw_bytes": total}


def write_checksums(out_dir, tag, files):
    path = Path(out_dir) / f"koeiro-{tag}-linux-checksums.txt"
    lines = [f"{sha256_of(item)}  {Path(item).name}" for item in files]
    path.write_text("\n".join(lines) + "\n", "ascii", newline="\n")
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True, help="例: v0.13.3")
    parser.add_argument("--kind", default="all", choices=("all", "app", "worker"))
    parser.add_argument("--root", default=".", help="リポジトリの場所")
    parser.add_argument("--out", default=None, help="出力先（既定: dist/linux）")
    parser.add_argument("--timeout", type=int, default=5400, help="1ビルドの上限秒")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    out_dir = Path(args.out or root / "dist" / "linux")
    produced = []
    try:
        require_docker(root)
        sys.path.insert(0, str(root))
        from src.version import APP_VERSION
        if version_of(args.tag) != APP_VERSION:
            raise SetupError(f"src/version.py の APP_VERSION={APP_VERSION} がタグ {args.tag} と違います")
        if args.kind in ("all", "app"):
            target = build_app(root, args.tag, out_dir, args.timeout)
            print(f"app: {target} ({target.stat().st_size / 1024 / 1024:.1f} MB)")
            produced.append(target)
        if args.kind in ("all", "worker"):
            raw = out_dir / "KoeiroWorker.tar.gz"
            container("worker", root, raw, args.timeout)
            bundle = extract(out_dir / "KoeiroWorker.tar.gz", root / "build" / "linux-worker")
            parts, staged = build_pack(root, args.tag, bundle, out_dir,
                                       root / "build" / "linux-pack-stage")
            print(f"worker bundle: {staged['files']} files, "
                  f"{staged['raw_bytes'] / 1024 / 1024:.1f} MB staged")
            for part in parts:
                print(f"part: {part} ({part.stat().st_size / 1024 / 1024:.1f} MB)")
            produced.extend(parts)
            (out_dir / "KoeiroWorker.tar.gz").unlink(missing_ok=True)
        if produced:
            checksums = write_checksums(out_dir, args.tag, produced)
            print(f"checksums: {checksums}")
    except SetupError as error:
        print(f"error: {error}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
