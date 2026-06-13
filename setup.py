from setuptools import find_packages, setup


setup(
    name="leantex",
    version="2.5.0",
    description="LeanTeX v2.5: native minted Lean code with generated infoview output in LaTeX PDFs",
    python_requires=">=3.9",
    packages=find_packages(include=["leantex*"]),
    entry_points={
        "console_scripts": [
            "leantex=leantex.cli:main",
        ]
    },
)
