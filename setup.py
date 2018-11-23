#! coding:utf-8
from setuptools import setup, find_packages
import sys
import codecs

"""
linux:
rm -rf "dist/*";rm -rf "build/*";python3 setup.py bdist_wheel;python2 setup.py bdist_wheel;twine upload "dist/*;rm -rf "dist/*";rm -rf "build/*""
win32:
rm -rf dist&rm -rf build&python3 setup.py bdist_wheel&python2 setup.py bdist_wheel&twine upload "dist/*"&rm -rf dist&rm -rf build
"""

py_version = sys.version_info
install_requires = ["psutil", "torequests", "websocket-client"]

setup(
    name="ichrome",
    version="0.0.1",
    keywords=("chrome"),
    description="toy for chrome devtools protocol. Read more: https://github.com/ClericPy/ichrome.",
    license="MIT License",
    install_requires=install_requires,
    py_modules=["ichrome"],
    author="ClericPy",
    author_email="clericpy@gmail.com",
    url="https://github.com/ClericPy/ichrome",
    packages=find_packages(),
    platforms="any",
)
