"""Thin Code Ocean entry point for ophys dF/F estimation.

All logic lives in the ``aind-ophys-dff-library`` package; this wrapper only
parses settings (CLI / environment) and invokes ``run``.
"""

from aind_ophys_dff_library.job import run

if __name__ == "__main__":
    run()
