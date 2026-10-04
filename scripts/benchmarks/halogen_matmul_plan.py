"""CLI for the managed backend's read-only HGNTUNE3 validator; no inference."""
import importlib.util
from pathlib import Path


def main():
    path = (Path(__file__).resolve().parents[2] /
            'backends/halogen-wsl2-0.16.2/scripts/matmul_plan.py')
    spec = importlib.util.spec_from_file_location('halogen_matmul_plan_backend', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.main()


if __name__ == '__main__':
    raise SystemExit(main())
