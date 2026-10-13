"""AI voice pack staging: only the weights the route loads, no venv, no CC BY-NC encodec."""
import hashlib
import json
from pathlib import Path
import shutil

import pytest

from tools import build_ai_pack
from tools.build_ai_pack import SetupError, DEFAULT_VOICE as VOICE


def _touch(path, text="x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _fake_source(tmp_path):
    root = tmp_path / "repo"
    for name in ("LICENSE", "README.md", "THIRD_PARTY_NOTICES.md"):
        _touch(root / name, "doc")
    repo = root / "vc_models/meanvc2/repo"
    _touch(repo / "src/infer/infer_e2e.py")
    _touch(repo / "src/model/cfm.py")
    _touch(repo / "preprocess/audio.py")
    _touch(repo / "preprocess/models/ecapa_tdnn.py")
    for name in ("fastu2pp_160ms.pt", "fastu2pp_80ms.pt", "wavlm_large.pt",
                 "wavlm_large_finetune.pth"):
        _touch(repo / "preprocess/ckpts" / name)
    _touch(repo / "ckpts/vocos/vocos.pt")
    _touch(repo / "ckpts/pretrained_models/meanvc2_120ms_40ms.safetensors")
    _touch(repo / "ckpts/pretrained_models/meanvc2_40ms_40ms.safetensors")
    _touch(repo / "figs/diagram.png")
    _touch(repo / "defaults.ini")
    _touch(repo / "default_config.yaml")
    lavasr = root / "vc_models/post_lavasr"
    _touch(lavasr / "repo/LavaSR/model.py")
    _touch(lavasr / "weights/lavasr.pt")
    _touch(lavasr / "vendor/vocos/feature_extractors.py")
    _touch(lavasr / "vendor/encodec/__init__.py")
    _touch(lavasr / "vendor/encodec/model.py")
    _touch(lavasr / "vendor/encodec-0.1.1.dist-info/METADATA")
    _touch(lavasr / "vendor/bin/encodec.exe")
    voice_dir = root / "models/user_voices" / VOICE
    _touch(voice_dir / "reference.wav")
    _touch(voice_dir / "fixed_embedding.npy")
    _touch(voice_dir / "profile.json")
    entries = [
        {"path": "vc_models/meanvc2/repo/preprocess/ckpts/fastu2pp_160ms.pt"},
        {"path": "vc_models/meanvc2/repo/ckpts/pretrained_models/meanvc2_120ms_40ms.safetensors"},
        {"path": "vc_models/meanvc2/repo/ckpts/vocos/vocos.pt"},
        {"path": f"models/user_voices/{VOICE}/reference.wav"},
        {"path": f"models/user_voices/{VOICE}/fixed_embedding.npy"},
    ]
    for entry in entries:
        entry["sha256"] = hashlib.sha256(b"x").hexdigest()
    (voice_dir / "runtime.json").write_text(json.dumps(
        {"backend": "meanvc2", "assets": entries}, ensure_ascii=False), "utf-8")
    _touch(root / "models/user_voices/user_other/reference.wav")
    worker = tmp_path / "dist/KoeiroWorker"
    _touch(worker / "KoeiroWorker.exe", "MZ")
    _touch(worker / "_internal_worker/torch/libtorch_cpu.dll", "dll")
    _touch(worker / "_internal_worker/src/vc/service.py", "code")
    return root, worker


def test_stage_pack_ships_the_route_weights_and_nothing_else(tmp_path):
    root, worker = _fake_source(tmp_path)
    stage, count, _total = build_ai_pack.stage_pack(root, worker, tmp_path / "stage")
    assert (stage / "KoeiroWorker.exe").is_file()
    assert (stage / "_internal_worker/torch/libtorch_cpu.dll").is_file()
    kept = "vc_models/meanvc2/repo/"
    assert (stage / (kept + "preprocess/ckpts/fastu2pp_160ms.pt")).is_file()
    assert (stage / (kept + "ckpts/vocos/vocos.pt")).is_file()
    assert (stage / (kept + "src/infer/infer_e2e.py")).is_file()
    for absent in (kept + "preprocess/ckpts/wavlm_large.pt",
                   kept + "preprocess/ckpts/wavlm_large_finetune.pth",
                   kept + "preprocess/ckpts/fastu2pp_80ms.pt",
                   kept + "ckpts/pretrained_models/meanvc2_40ms_40ms.safetensors",
                   kept + "figs/diagram.png",
                   "vc_models/post_lavasr/vendor/bin/encodec.exe",
                   "models/user_voices/user_other/reference.wav"):
        assert not (stage / absent).exists(), absent
    assert count >= 15


def test_stage_pack_replaces_encodec_with_a_raising_stub(tmp_path):
    root, worker = _fake_source(tmp_path)
    stage, _count, _total = build_ai_pack.stage_pack(root, worker, tmp_path / "stage")
    stub = stage / "vc_models/post_lavasr/vendor/encodec/__init__.py"
    assert stub.is_file()
    assert "encodec is not distributed with Koeiro" in stub.read_text("utf-8")
    assert not (stage / "vc_models/post_lavasr/vendor/encodec/model.py").exists()
    assert not (stage / "vc_models/post_lavasr/vendor/encodec-0.1.1.dist-info").exists()
    build_ai_pack.check_stage(stage)


def test_encodec_stub_imports_like_a_package_and_refuses_use(tmp_path):
    """vocos does `from encodec import EncodecModel`, so the stand-in must import."""
    import importlib
    import sys

    package = tmp_path / "encodec"
    package.mkdir()
    (package / "__init__.py").write_text(build_ai_pack.ENCODEC_STUB, "utf-8")
    sys.path.insert(0, str(tmp_path))
    sys.modules.pop("encodec", None)
    try:
        module = importlib.import_module("encodec")
        assert [str(Path(item)) for item in module.__path__] == [str(package)]
        with pytest.raises(NotImplementedError):
            module.EncodecModel()
        with pytest.raises(NotImplementedError):
            module.EncodecModel.encodec_model_24khz()
        with pytest.raises(AttributeError):
            module.some_unknown_name
    finally:
        sys.path.remove(str(tmp_path))
        sys.modules.pop("encodec", None)


def test_manifest_records_the_pack_contract(tmp_path):
    root, worker = _fake_source(tmp_path)
    stage, _count, _total = build_ai_pack.stage_pack(root, worker, tmp_path / "stage")
    manifest = build_ai_pack.write_manifest(stage, "v9.9.9", "a" * 64)
    build_ai_pack.check_stage(stage)
    on_disk = json.loads((stage / "koeiro-ai-pack.json").read_text("utf-8"))
    assert on_disk == manifest
    assert on_disk["version"] == "9.9.9"
    assert on_disk["requires"]["app_asset"] == "koeiro-v9.9.9-windows-setup.exe"
    assert on_disk["worker_sha256"] == "a" * 64
    assert any("encodec" in item for item in on_disk["excluded"])


def test_a_tampered_checkpoint_stops_the_pack(tmp_path):
    """runtime.json pins the weights; a pack that does not match them must not build."""
    root, worker = _fake_source(tmp_path)
    stage, _count, _total = build_ai_pack.stage_pack(root, worker, tmp_path / "stage")
    build_ai_pack.check_stage(stage)
    victim = stage / "vc_models/meanvc2/repo/ckpts/vocos/vocos.pt"
    victim.write_text("tampered", "utf-8")
    with pytest.raises(SetupError) as caught:
        build_ai_pack.check_stage(stage)
    assert "sha256" in str(caught.value)


def test_check_stage_refuses_a_real_encodec_and_a_build_root(tmp_path):
    root, worker = _fake_source(tmp_path)
    stage, _count, _total = build_ai_pack.stage_pack(root, worker, tmp_path / "stage")
    _touch(stage / "vc_models/post_lavasr/vendor/encodec/model.py")
    with pytest.raises(SetupError):
        build_ai_pack.check_stage(stage)
    _touch(stage / "_internal_worker/koeiro-root.txt", "D:/dev")
    with pytest.raises(SetupError):
        build_ai_pack.check_stage(stage)


def test_check_stage_refuses_a_missing_torch_or_worker(tmp_path):
    root, worker = _fake_source(tmp_path)
    stage, _count, _total = build_ai_pack.stage_pack(root, worker, tmp_path / "stage")
    shutil.rmtree(stage / "_internal_worker/torch")
    with pytest.raises(SetupError):
        build_ai_pack.check_stage(stage)
    with pytest.raises(SetupError):
        build_ai_pack.stage_pack(root, tmp_path / "absent", tmp_path / "stage2")


def test_the_linux_manifest_names_the_linux_artifacts(tmp_path):
    """The same staging builds the Linux pack, so the manifest has to follow."""
    root, worker = _fake_source(tmp_path)
    (worker / "KoeiroWorker").write_bytes(b"\x7fELF")
    stage, _count, _total = build_ai_pack.stage_pack(
        root, worker, tmp_path / "stage", tag="v9.9.9",
        worker_exe="KoeiroWorker", contents_dir="_internal_worker")
    build_ai_pack.check_stage(stage, worker_exe="KoeiroWorker")
    manifest = json.loads((stage / "koeiro-ai-pack.json").read_text("utf-8"))
    assert manifest["worker"] == "KoeiroWorker"
    assert manifest["requires"]["app_asset"] == "koeiro-v9.9.9-linux-app.tar.gz"
    assert manifest["contents"][0] == "KoeiroWorker"
    assert build_ai_pack.app_asset("v1.2.3", "KoeiroWorker.exe") == \
        "koeiro-v1.2.3-windows-setup.exe"


def test_pack_asset_names():
    assert build_ai_pack.pack_name("v1.2.3") == "koeiro-v1.2.3-ai-pack-checksums.txt"
