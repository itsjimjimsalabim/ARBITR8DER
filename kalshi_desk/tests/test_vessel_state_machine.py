"""First test — verifies the package installs and imports cleanly."""

from kalshi_desk_package import __version__


def test_package_version_is_set():
    assert __version__ == "0.1.0"


def test_package_is_importable():
    import kalshi_desk_package
    assert hasattr(kalshi_desk_package, "__version__")
