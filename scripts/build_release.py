# [Module: scripts.build_release] [Status: 已完成] [Brief: 固定依赖与校验值的 Windows 三后端发布包组装]
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tomllib
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "packaging/backends.json"
BUILD = ROOT / "build/release"
OUTPUT = ROOT / "dist/release"


def run(*args: str, **kwargs):
    subprocess.run(list(map(str, args)), cwd=ROOT, check=True, **kwargs)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, expected: str, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / url.rsplit("/", 1)[-1]
    if not path.is_file() or sha256(path) != expected:
        request = urllib.request.Request(url, headers={"User-Agent": "MCPackLocalizer-release"})
        with urllib.request.urlopen(request, timeout=120) as response, path.open("wb") as stream:
            shutil.copyfileobj(response, stream)
    if sha256(path) != expected:
        raise ValueError(f"下载文件校验失败：{path.name}")
    return path


def project_version() -> str:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    version = project["project"]["version"]
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?", version):
        raise ValueError("版本必须采用 2.0.0 或 2.0.0rc1 等格式")
    source = (ROOT / "src/mcpacklocalizer/__init__.py").read_text(encoding="utf-8")
    if f'__version__ = "{version}"' not in source:
        raise ValueError("pyproject.toml 与包内 __version__ 不一致")
    return version


def source_commit() -> str:
    commit = os.getenv("GITHUB_SHA") or subprocess.check_output(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("无法确定构建提交")
    return commit


def desktop_licenses(destination: Path):
    """冻结程序不保留 dist-info，显式携带桌面依赖的许可文件。"""
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    packages = {p["name"]: p for p in lock["package"]}
    pending = [re.split(r"[<>=!~;\[]", item, maxsplit=1)[0].strip().lower().replace("_", "-")
               for item in project["project"]["dependencies"]]
    included = set()
    while pending:
        name = pending.pop()
        if name in included:
            continue
        included.add(name)
        pending.extend(d["name"] for d in packages[name].get("dependencies", []))
        distribution = importlib.metadata.distribution(name)
        for file in distribution.files or []:
            relative = Path(file)
            if relative.is_absolute() or ".." in relative.parts:
                continue
            if not any(part.lower().startswith(("license", "licence", "copying", "notice"))
                       for part in relative.parts):
                continue
            target = destination / name / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(distribution.locate_file(file), target)


def native_runtime(backend: str, config: dict, directory: Path, libraries: Path):
    """仅收集 NVIDIA 官方 wheel 中的运行 DLL 和许可证，不带开发头文件。"""
    for component in config.get("runtime_wheels", []):
        archive = download(component["url"], component["sha256"], ROOT / "build/downloads" / backend)
        with zipfile.ZipFile(archive) as bundle:
            for entry in bundle.infolist():
                relative = Path(entry.filename)
                if entry.is_dir() or relative.is_absolute() or ".." in relative.parts:
                    continue
                if relative.suffix.lower() == ".dll":
                    target = libraries / relative.name
                elif any(part.lower().startswith(("license", "licence", "copying", "notice"))
                         for part in relative.parts):
                    target = directory / "licenses" / component["name"] / relative
                else:
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(entry) as source, target.open("wb") as destination:
                    shutil.copyfileobj(source, destination)
    for name in config.get("runtime_dlls", []):
        if not (libraries / name).is_file():
            raise ValueError(f"缺少后端运行库：{name}")


def windows_runtime(runtime: Path):
    import PyQt6

    qt_bin = Path(PyQt6.__path__[0]) / "Qt6/bin"
    for source in qt_bin.glob("*140*.dll"):
        shutil.copy2(source, runtime / source.name)
    openmp = Path(os.environ["SystemRoot"]) / "System32/vcomp140.dll"
    if not openmp.is_file():
        raise ValueError("构建机缺少 VC++ OpenMP 运行库，请先安装 Microsoft VC++ x64 Redistributable")
    shutil.copy2(openmp, runtime / "vcomp140.dll")


def validate_native_dependencies(runtime: Path, backend: str):
    """GPU 驱动由系统提供，其它推理运行库必须在发行包内，系统 DLL 校验来源。"""
    import pefile

    libraries = runtime / "Lib/site-packages/llama_cpp/lib"
    binaries = [*runtime.glob("*.dll"), *runtime.glob("*.pyd"), *libraries.glob("*.dll")]
    bundled = {path.name.lower() for path in binaries}
    drivers = {"nvcuda.dll"} if backend == "cuda" else {"vulkan-1.dll"} if backend == "vulkan" else set()
    system = Path(os.environ["SystemRoot"]) / "System32"
    for binary in binaries:
        with pefile.PE(str(binary), fast_load=True) as pe:
            pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]])
            for dependency in getattr(pe, "DIRECTORY_ENTRY_IMPORT", []):
                name = dependency.dll.decode("ascii").lower()
                if name in bundled or name in drivers or name.startswith(("api-ms-win-", "ext-ms-win-")):
                    continue
                if name.startswith(("msvcp", "vcruntime", "vcomp", "cublas", "cudart")) or not (system / name).is_file():
                    raise ValueError(f"{binary.name} 缺少随包运行库：{name}")


def runtime_requirements(destination: Path):
    """从同一锁文件导出后台所需的依赖闭包，不把 Qt 安装进内置解释器。"""
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    packages = {p["name"]: p for p in lock["package"]}
    pending = [re.split(r"[<>=!~;\[]", item, maxsplit=1)[0].strip().lower().replace("_", "-")
               for item in project["project"]["dependencies"] if not item.lower().startswith("pyqt")]
    pending += [re.split(r"[<>=!~;\[]", item, maxsplit=1)[0].strip().lower().replace("_", "-")
                for item in project["dependency-groups"]["inference-runtime"]]
    needed = set()
    while pending:
        name = pending.pop()
        if name in needed:
            continue
        needed.add(name)
        pending.extend(d["name"] for d in packages[name].get("dependencies", []))
    args = ["uv", "export", "--frozen", "--no-dev", "--group", "inference-runtime",
            "--no-emit-project", "--output-file", str(destination)]
    for name in sorted(packages.keys() - needed):
        args += ["--no-emit-package", name]
    run(*args, stdout=subprocess.DEVNULL)


def desktop():
    BUILD.mkdir(parents=True, exist_ok=True)
    run("uv", "build", "--wheel", "--out-dir", str(BUILD / "wheel"))
    env = os.environ.copy()
    windows = Path(os.environ["SystemRoot"])
    # 禁止从开发机的 Poppler、CUDA SDK 等工具目录误收集同名 DLL。
    env["PATH"] = os.pathsep.join(map(str, [windows / "System32", windows,
                                          Path(sys.executable).parent, Path(sys.base_prefix)]))
    run(sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", str(BUILD / "desktop"),
        "--workpath", str(BUILD / "pyinstaller"), str(ROOT / "packaging/desktop.spec"), env=env)
    metadata = {"version": project_version(), "commit": source_commit()}
    (BUILD / "desktop/desktop-build.json").write_text(json.dumps(metadata), encoding="utf-8")


def assemble(backend: str):
    version, commit = project_version(), source_commit()
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    common = json.loads((BUILD / "desktop/desktop-build.json").read_text(encoding="utf-8"))
    if common != {"version": version, "commit": commit}:
        raise ValueError("桌面产物与当前提交或版本不一致，请重新构建")
    name = f"MCPackLocalizer-{version}-win-x64-{backend}"
    directory = BUILD / backend / name
    if directory.exists():
        raise ValueError(f"组装目录已存在，请换用干净的构建目录：{directory}")
    shutil.copytree(BUILD / "desktop/MCPackLocalizer", directory)
    python_config, backend_config = config["python"], config["backends"][backend]
    archive = download(python_config["url"], python_config["sha256"], ROOT / "build/downloads")
    runtime = directory / "runtime"
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(runtime)
    (runtime / "python312._pth").write_text("python312.zip\n.\napp\nLib/site-packages\nimport site\n", encoding="utf-8")
    requirements = directory / "runtime-requirements.txt"
    runtime_requirements(requirements)
    site = runtime / "Lib/site-packages"
    run("uv", "pip", "install", "--python", sys.executable, "--target", str(site), "--no-deps",
        "--only-binary", ":all:", "--require-hashes", "-r", str(requirements))
    wheel = BUILD / "wheel" / f"mcpacklocalizer-{version}-py3-none-any.whl"
    run("uv", "pip", "install", "--python", sys.executable, "--target", str(runtime / "app"), "--no-deps", str(wheel))
    inference = download(backend_config["url"], backend_config["sha256"], ROOT / "build/downloads" / backend)
    run("uv", "pip", "install", "--python", sys.executable, "--target", str(site), "--no-deps", str(inference))
    native_runtime(backend, backend_config, directory, site / "llama_cpp/lib")
    windows_runtime(runtime)
    validate_native_dependencies(runtime, backend)
    libraries = [p.name for p in (site / "llama_cpp/lib").glob("*.dll")]
    if not any(backend_config["library"] in name.lower() for name in libraries):
        raise ValueError(f"推理 wheel 缺少 {backend} 后端 DLL")
    metadata = {"version": version, "commit": commit, "backend": backend, "python": python_config["version"],
                "llama_cpp_python": config["llama_cpp_python"], "wheel_sha256": backend_config["sha256"],
                "requirements": backend_config["requirements"], "libraries": libraries,
                "runtime_wheels": [{"name": item["name"], "version": item["version"], "sha256": item["sha256"]}
                                   for item in backend_config.get("runtime_wheels", [])],
                "native_sha256": {path.relative_to(directory).as_posix(): sha256(path)
                                  for path in [*runtime.glob("*.dll"), *(site / "llama_cpp/lib").glob("*.dll")]},
                "run_id": os.getenv("GITHUB_RUN_ID", "local"), "run_attempt": os.getenv("GITHUB_RUN_ATTEMPT", "local")}
    (directory / "runtime.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    (directory / "models").mkdir()
    shutil.copy2(ROOT / "LICENSE", directory / "LICENSE")
    desktop_licenses(directory / "licenses")
    run(sys.executable, str(ROOT / "scripts/export_docs.py"), "--output", str(directory / "使用说明.html"))
    # wheel 的 dist-info/licenses 和 Python 自带许可证随运行时保留。
    run(str(runtime / "python.exe"), str(ROOT / "scripts/smoke_release.py"), str(directory), backend)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    zip_path = Path(shutil.make_archive(str(OUTPUT / name), "zip", directory.parent, directory.name))
    (OUTPUT / f"{name}.sha256").write_text(f"{sha256(zip_path)}  {zip_path.name}\n", encoding="ascii")
    (OUTPUT / f"{name}.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已生成：{zip_path}", flush=True)


def main():
    parser = argparse.ArgumentParser(description="构建 Windows 多目录发布包")
    parser.add_argument("stage", choices=["desktop", "assemble"])
    parser.add_argument("--backend", choices=["cpu", "vulkan", "cuda"], default="cpu")
    args = parser.parse_args()
    if sys.platform != "win32" or platform.machine().lower() not in {"amd64", "x86_64"}:
        raise SystemExit("发布包只能在 Windows x64 上构建")
    if sys.version_info[:2] != (3, 12):
        raise SystemExit("构建需要 Python 3.12")
    project_version()
    desktop() if args.stage == "desktop" else assemble(args.backend)


if __name__ == "__main__":
    main()
