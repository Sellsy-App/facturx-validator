from importlib.metadata import PackageNotFoundError, version

from .facturx_validator import (
    extract_facturx_xml,
    validate_xml,
    validate_schematron,
    validate_all,
)

try:
    __version__ = version("facturx-validator")
except PackageNotFoundError:
    __version__ = "unknown"
