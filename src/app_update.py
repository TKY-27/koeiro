"""Check, download and stage application updates from GitHub Releases.

Standard library only, so the frozen worker-less updater path and the unit tests
never need Qt, audio or model packages. Network access happens only when the user
asks (or consented to the startup check): nothing here phones home by itself.

Release layout this understands (see PUBLISHING.md):

* tag like ``v1.2.3`` (optionally ``-preview.N``)
* asset ``koeiro-<tag>-windows.zip`` / ``koeiro-<tag>-linux.tar.gz`` — a source tree,
  for a release directory that gets swapped in place by ``src/update_swap.py``
* asset ``koeiro-<tag>-windows-setup.exe`` — the installer, and the only thing a
  frozen ``Koeiro.exe`` may update with. Swapping files around a running executable
  cannot work on Windows (the image and its DLLs are locked), so the frozen path
  downloads the new setup, verifies it against ``-checksums.txt`` and runs it
  silently; Inno Setup closes this copy and relaunches the replaced one.
* package root of a source tree holds ``release.json``
  (``{"app": "Koeiro", "version": ..., ...}``)
"""
import hashlib
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

from .version import APP_VERSION, UPDATE_REPO

API_LATEST = "https://api.github.com/repos/{repo}/releases/latest"
API_ALL = "https://api.github.com/repos/{repo}/releases?per_page=20"
USER_AGENT = "Koeiro-update-check"

PLATFORM_ASSETS = {
    "windows": ("windows", ".zip"),
    "linux": ("linux", ".tar.gz"),
}
SETUP_ASSET = "koeiro-{tag}-windows-setup.exe"
CHECKSUMS_ASSET = "koeiro-{tag}-windows-checksums.txt"


class UpdateError(Exception):
    """Anything that stops an update: network, format or install problem."""


def parse_version(tag):
    """'v1.2.3' / '0.11.0-preview.3' -> comparable tuple.

    A final release compares higher than previews of the same base, so an
    installed preview always offers the final release as an update.
    """
    text = str(tag).strip()
    if text[:1].lower() == "v":
        text = text[1:]
    base, dash, pre = text.partition("-")
    parts = base.split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        raise UpdateError(f"Unparsable version: {tag!r}")
    major, minor, patch = (int(part) for part in parts)
    if not dash:
        return (major, minor, patch, 1, 0)
    kind, num = pre, 0
    if pre[:8] == "preview." and pre[8:].isdigit():
        kind, num = "preview", int(pre[8:])
    return (major, minor, patch, 0, 0 if kind != "preview" else num)


def is_newer(latest_tag, current_tag=APP_VERSION):
    try:
        return parse_version(latest_tag) > parse_version(current_tag)
    except UpdateError:
        return False


def _version_matches(info_version, tag):
    """release.json holds the version without the leading v; tags carry it."""
    try:
        return parse_version(str(info_version)) == parse_version(str(tag))
    except UpdateError:
        return False


def _api_get(url, timeout):
    request = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
    })
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as error:
        raise UpdateError(f"更新情報を取得できませんでした: {error}") from error


def fetch_latest_release(repo=UPDATE_REPO, timeout=15, allow_prerelease=False):
    """Newest published release dict, or None when the repo has no releases."""
    if allow_prerelease:
        try:
            releases = _api_get(API_ALL.format(repo=repo), timeout)
        except UpdateError:
            return None
        for item in releases if isinstance(releases, list) else []:
            if isinstance(item, dict) and not item.get("draft") and item.get("tag_name"):
                return item
        return None
    try:
        release = _api_get(API_LATEST.format(repo=repo), timeout)
    except UpdateError:
        return None
    if not isinstance(release, dict) or not release.get("tag_name"):
        return None
    return release


def pick_asset(release, platform=None, kind=None):
    """Download candidate for this OS and install form, or None when there is none.

    A frozen install must not take the source tree: it holds no ``Koeiro.exe`` and
    would destroy the bundle it lands in. So ``kind == "frozen"`` only ever matches
    the installer asset, and a release without one simply offers no update.
    """
    if platform is None:
        platform = "windows" if sys.platform == "win32" else (
            "linux" if sys.platform.startswith("linux") else None)
    if kind is None:
        kind = "frozen" if getattr(sys, "frozen", False) else "package"
    if not isinstance(release, dict):
        return None
    tag = str(release.get("tag_name", ""))
    assets = release.get("assets") or []
    if kind == "frozen":
        if platform != "windows":
            return None
        wanted = SETUP_ASSET.format(tag=tag)
        checksums = CHECKSUMS_ASSET.format(tag=tag)
        for asset in assets:
            name = str(asset.get("name", ""))
            url = asset.get("browser_download_url")
            if name == wanted and url:
                return {"name": name, "url": url, "size": asset.get("size") or 0,
                        "kind": "setup",
                        "checksums_url": _asset_url(assets, checksums),
                        "checksums_name": checksums}
        return None
    wanted = PLATFORM_ASSETS.get(platform)
    if wanted is None:
        return None
    token, extension = wanted
    prefix = f"koeiro-{tag}-{token}"
    for asset in assets:
        name = str(asset.get("name", ""))
        url = asset.get("browser_download_url")
        if name.startswith(prefix) and name.endswith(extension) and url:
            return {"name": name, "url": url, "size": asset.get("size") or 0,
                    "kind": "package"}
    return None


def _asset_url(assets, name):
    for asset in assets:
        if str(asset.get("name", "")) == name and asset.get("browser_download_url"):
            return str(asset["browser_download_url"])
    return ""


def download_asset(url, destination, progress=None, timeout=120):
    """Stream an asset to disk. progress(done_bytes, total_bytes|0) is optional."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            total = int(response.headers.get("Content-Length") or 0)
            done = 0
            with open(destination, "wb") as stream:
                while True:
                    chunk = response.read(1024 * 256)
                    if not chunk:
                        break
                    stream.write(chunk)
                    done += len(chunk)
                    if callable(progress):
                        progress(done, total)
    except Exception as error:
        try:
            destination.unlink()
        except OSError:
            pass
        raise UpdateError(f"ダウンロードに失敗しました: {error}") from error
    return destination


def extract_package(archive, destination):
    """Unpack a release asset; zip for Windows, tar.gz for Linux.

    Members that would escape the destination (absolute paths, ``..``) abort
    the extraction instead of writing outside it.
    """
    archive, destination = Path(archive), Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    try:
        if archive.suffix == ".zip":
            with zipfile.ZipFile(archive) as bundle:
                for member in bundle.infolist():
                    target = (destination / member.filename).resolve()
                    if target != destination.resolve() and destination.resolve() not in target.parents:
                        raise UpdateError(f"不正な同梱物です: {member.filename}")
                bundle.extractall(destination)
        else:
            with tarfile.open(archive, "r:gz") as bundle:
                bundle.extractall(destination, filter="data")
    except UpdateError:
        raise
    except Exception as error:
        raise UpdateError(f"展開に失敗しました: {error}") from error
    # A package may wrap everything in one top folder; unwrap it.
    children = [path for path in destination.iterdir()]
    if len(children) == 1 and children[0].is_dir():
        return children[0]
    return destination


def read_package_release(package_dir):
    """release.json of an extracted package, validated."""
    try:
        info = json.loads((Path(package_dir) / "release.json").read_text("utf-8"))
    except (OSError, ValueError) as error:
        raise UpdateError(f"更新パッケージが壊れています: {error}") from error
    if not isinstance(info, dict) or info.get("app") != "Koeiro":
        raise UpdateError("更新パッケージが壊れています")
    try:
        parse_version(info.get("version", ""))
    except UpdateError:
        raise UpdateError("更新パッケージが壊れています") from None
    if not (Path(package_dir) / "app.py").is_file():
        raise UpdateError("更新パッケージが壊れています")
    return info


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_checksums(text):
    """``<sha256>  <filename>`` lines (sha256sum format) -> {filename: digest}."""
    table = {}
    for line in str(text).splitlines():
        line = line.strip()
        if len(line) < 66 or line[64] != " ":
            continue
        name = line[65:].lstrip(" *").strip()
        if name:
            table[name] = line[:64].lower()
    return table


def verify_downloaded(path, name, table):
    """Refuse an installer whose digest is missing or differs. Never runs unverified."""
    expected = table.get(str(name))
    if not expected:
        raise UpdateError("更新ファイルの検証情報がありません")
    try:
        actual = sha256_of(path)
    except OSError as error:
        raise UpdateError(f"更新ファイルを読みけません: {error}") from error
    if actual != expected.lower():
        raise UpdateError("更新ファイルの検証に失敗しました（ダウンロードが壊れている可能性があります）")
    return actual


def update_log_path():
    """Where updater attempts and failures are recorded (per-user, next to app.log)."""
    from .runtime_paths import data_dir
    target = data_dir() / "logs"
    target.mkdir(parents=True, exist_ok=True)
    return target / "update.log"


def log_update(message):
    """Best-effort audit line. An updater that cannot write its log still updates."""
    try:
        with open(update_log_path(), "a", encoding="utf-8") as stream:
            stream.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")
    except OSError:
        pass


def prune_old_installers(keep):
    """Drop previous setup downloads so the staging folder does not grow per version."""
    keep = Path(keep)
    for path in updates_dir().glob("koeiro-*-windows-setup.exe"):
        if path == keep:
            continue
        try:
            path.unlink()
        except OSError:
            pass


def prepare_installer(asset, tag, progress=None):
    """Download and verify a setup asset. Runs on a worker thread; returns the path."""
    if not isinstance(asset, dict) or asset.get("kind") != "setup":
        raise UpdateError("この実行形式では自動更新できません")
    name = str(asset.get("name") or SETUP_ASSET.format(tag=tag))
    checksums_name = str(asset.get("checksums_name") or CHECKSUMS_ASSET.format(tag=tag))
    checksums_url = str(asset.get("checksums_url") or "")
    if not checksums_url:
        raise UpdateError("この版には検証情報（checksums）が同梱されていないため、自動更新できません")
    checksums_path = updates_dir() / checksums_name
    download_asset(checksums_url, checksums_path, timeout=30)
    try:
        table = parse_checksums(checksums_path.read_text("utf-8"))
        target = updates_dir() / name
        download_asset(str(asset["url"]), target, progress=progress)
        verify_downloaded(target, name, table)
    finally:
        try:
            checksums_path.unlink()
        except OSError:
            pass
    prune_old_installers(target)
    log_update(f"verified {name} ({target.stat().st_size} bytes)")
    return target


def installer_command(setup_path):
    """Silent install: no wizard, no reboot prompt, no per-file prompt."""
    return [str(Path(setup_path).resolve()), "/VERYSILENT", "/NORESTART",
            "/SUPPRESSMSGBOXES", "/SP-"]


def run_installer_and_restart(setup_path):
    """Hand the update to the installer and return; the caller must quit right away.

    The setup program is outside the install folder, so nothing it replaces is locked
    by this process. Inno Setup closes the running copy itself (CloseApplications) and
    starts the new one when it is done.
    """
    from .runtime_paths import is_frozen
    if not is_frozen():
        raise UpdateError("実行ファイル版以外では使えません")
    path = Path(setup_path)
    if path.suffix.lower() != ".exe" or not path.is_file():
        raise UpdateError("更新パッケージが壊れています")
    command = installer_command(path)
    log_update(f"launching installer: {path.name}")
    try:
        if sys.platform == "win32":
            flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
            subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             stdin=subprocess.DEVNULL, creationflags=flags, close_fds=True)
        else:
            subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             stdin=subprocess.DEVNULL, start_new_session=True, close_fds=True)
    except Exception as error:
        log_update(f"installer launch failed: {error}")
        raise UpdateError(f"インストーラを起動できませんでした: {error}") from error
    return command


def current_kind():
    """'frozen' (installed exe), 'release-dir' (marked copy) or 'source'."""
    from .runtime_paths import asset_root, is_frozen
    if is_frozen():
        return "frozen"
    if (asset_root() / "release.json").is_file():
        return "release-dir"
    return "source"


def install_dir():
    """Directory an in-place swap would replace, or None when there is none.

    Only a release directory (a marked source tree copy) can be swapped: a frozen
    install updates through its installer instead, see ``run_installer_and_restart``.
    """
    from .runtime_paths import asset_root, is_frozen
    if is_frozen():
        return None
    if (asset_root() / "release.json").is_file():
        return asset_root()
    return None


def updates_dir():
    """Writable staging area for downloads (per-user, never the install dir)."""
    from .runtime_paths import data_dir
    target = data_dir() / "updates"
    target.mkdir(parents=True, exist_ok=True)
    return target


def launch_command():
    """How this running copy was started, for the post-update relaunch."""
    root = Path(__file__).resolve().parents[1]
    return [sys.executable, str(root / "app.py")]


def begin_update_and_restart(staging_dir, version):
    """Hand a validated staging dir to the apply helper and return its plan path.

    The helper waits for this process to exit, swaps the install, then launches
    the new copy. The caller must quit the app right after this returns.
    """
    target = install_dir()
    if target is None:
        raise UpdateError("この実行形式では自動更新できません")
    info = read_package_release(staging_dir)
    if not _version_matches(info.get("version"), version):
        raise UpdateError("更新パッケージが壊れています")
    plan = {
        "staging": str(Path(staging_dir).resolve()),
        "install": str(Path(target).resolve()),
        "launch": launch_command(),
        "parent_pid": os.getpid(),
    }
    plan_path = Path(staging_dir) / "update-plan.json"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False), "utf-8")
    root = Path(__file__).resolve().parents[1]
    command = [sys.executable, str(root / "app.py"), "--apply-update", str(plan_path)]
    try:
        if sys.platform == "win32":
            flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
            subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             stdin=subprocess.DEVNULL, creationflags=flags, close_fds=True)
        else:
            subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             stdin=subprocess.DEVNULL, start_new_session=True, close_fds=True)
    except Exception as error:
        raise UpdateError(f"更新ヘルパーを起動できませんでした: {error}") from error
    return plan_path


def check_now(current=APP_VERSION, repo=UPDATE_REPO, timeout=15):
    """One update check: 'uptodate' | {'tag', 'notes', 'url', 'asset'} | {'error'}.

    Returns plain data (JSON-safe) so a background thread can hand it to the GUI.
    The asset carries a ``kind``: ``setup`` for an installed executable, ``package``
    for a release directory.
    """
    kind = current_kind()
    release = fetch_latest_release(repo, timeout)
    if release is None:
        return {"status": "error", "message": "更新情報を取得できませんでした"}
    tag = str(release.get("tag_name", ""))
    try:
        newer = parse_version(tag) > parse_version(current)
    except UpdateError:
        return {"status": "error", "message": "更新情報を取得できませんでした"}
    if not newer:
        return {"status": "uptodate", "tag": tag}
    asset = pick_asset(release, kind=kind)
    if asset is None:
        if kind == "frozen":
            return {"status": "error",
                    "message": "この版には実行ファイル用のインストーラがありません"}
        return {"status": "error", "message": "このOS用の配布がありません"}
    notes = str(release.get("body") or "")
    return {"status": "found", "tag": tag, "notes": notes[:2000],
            "url": str(release.get("html_url") or ""), "asset": asset}
