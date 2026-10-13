"""Проверки развёртывания: размещение рабочей базы в обычном режиме и в .exe.

Отдельный набор тестов нужен, чтобы зафиксировать поведение приложения после
упаковки в PyInstaller: в одном файле рабочие данные не должны попадать
во временный каталог, который удаляется при закрытии программы.
"""
from pathlib import Path

import pytest

import app.database as database_module
from app.database import (APP_DATA_DIRNAME, DatabaseManager, candidate_data_dirs,
                          default_data_dir)
from app.models import Preset


# ------------------------------------------------- обычный режим разработки


def test_source_mode_uses_project_data_folder(monkeypatch):
    monkeypatch.delattr(database_module.sys, "frozen", raising=False)
    expected = Path(database_module.__file__).resolve().parent.parent / "data"
    assert default_data_dir() == expected


def test_manager_creates_database_in_data_dir():
    manager = DatabaseManager()
    try:
        assert manager.db_path == manager.data_dir / "presets.db"
        assert manager.db_path.exists()
        assert len(manager.list_formats()) == 9
    finally:
        manager.close()


def test_profiles_survive_reopening():
    first = DatabaseManager()
    first.delete_preset("persist-deploy")          # предупреждение о повторе прогона
    first.create_preset(Preset(name="persist-deploy", output_format="PNG",
                               resize_mode="WIDTH", resize_value="321"))
    first.close()

    second = DatabaseManager()
    try:
        assert second.get_preset("persist-deploy").resize_value == "321"
    finally:
        second.delete_preset("persist-deploy")
        second.close()


# ----------------------------------------------------------- режим .exe


def test_frozen_mode_prefers_folder_next_to_executable(tmp_path, monkeypatch):
    executable = tmp_path / "dist" / "BatchImageStudio.exe"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"MZ")
    monkeypatch.setattr(database_module.sys, "frozen", True, raising=False)
    monkeypatch.setattr(database_module.sys, "executable", str(executable))

    candidates = candidate_data_dirs()
    assert candidates[0] == executable.parent / "data"
    assert default_data_dir() == executable.parent / "data"


def test_frozen_mode_falls_back_to_local_appdata(tmp_path, monkeypatch):
    """Если папка рядом с .exe недоступна для записи, выбирается %LOCALAPPDATA%."""
    executable = tmp_path / "dist" / "BatchImageStudio.exe"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"MZ")
    monkeypatch.setattr(database_module.sys, "frozen", True, raising=False)
    monkeypatch.setattr(database_module.sys, "executable", str(executable))

    fallback = tmp_path / "AppData" / "Local"
    fallback.mkdir(parents=True)
    read_only = executable.parent / "data"

    def deny(directory, **kwargs):
        if str(directory).startswith(str(read_only)):
            raise PermissionError(f"Отказано в доступе: {directory}")
        return original_mkdir(directory, **kwargs)

    original_mkdir = Path.mkdir
    monkeypatch.setattr(Path, "mkdir", deny)
    assert default_data_dir([read_only, fallback / APP_DATA_DIRNAME]) == \
        fallback / APP_DATA_DIRNAME


def test_all_candidates_readonly_raises_clear_error(tmp_path):
    blocked = tmp_path / "blocked"
    blocked.write_text("это файл, а не папка", encoding="utf-8")
    with pytest.raises(RuntimeError, match="Не удалось подготовить рабочую папку"):
        default_data_dir([blocked / "data"])


def test_frozen_candidate_order_includes_three_locations(tmp_path, monkeypatch):
    monkeypatch.setattr(database_module.sys, "frozen", True, raising=False)
    monkeypatch.setattr(database_module.sys, "executable",
                        str(tmp_path / "BatchImageStudio.exe"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    candidates = candidate_data_dirs()
    assert len(candidates) == 3
    assert candidates[1] == tmp_path / "Local" / APP_DATA_DIRNAME
    assert str(candidates[2]).endswith(APP_DATA_DIRNAME)