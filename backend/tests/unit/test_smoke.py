import importlib


def test_app_package_imports() -> None:
    assert importlib.import_module("app") is not None
