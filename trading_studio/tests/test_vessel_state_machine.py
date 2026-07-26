"""First test — verifies the package installs and imports cleanly."""

from arbitr8der_package import __version__


def test_package_version_is_set():
    assert __version__ == "0.1.0"


def test_package_is_importable():
    import arbitr8der_package
    assert hasattr(arbitr8der_package, "__version__")
