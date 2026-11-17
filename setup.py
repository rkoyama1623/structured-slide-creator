"""Bundle canonical non-Python assets in distributions without maintaining copies."""

from pathlib import Path
from shutil import copytree
from setuptools import setup
from setuptools.command.build_py import build_py


class BuildWithAssets(build_py):
    def run(self):
        super().run()
        root = Path(__file__).parent
        target = Path(self.build_lib) / "structured_slide_creator" / "_assets"
        for name in ("styles", "skills", "docs", "examples"):
            copytree(root / name, target / name, dirs_exist_ok=True)


setup(cmdclass={"build_py": BuildWithAssets})
