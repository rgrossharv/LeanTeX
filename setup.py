from setuptools import find_packages, setup


setup(
    name="leantex",
    version="0.1.0",
    description="LeanTeX: embed Lean 4 diagnostics and messages in LaTeX PDFs",
    python_requires=">=3.9",
    packages=find_packages(include=["leantex*"]),
    entry_points={
        "console_scripts": [
            "leantex=leantex.cli:main",
        ]
    },
)
