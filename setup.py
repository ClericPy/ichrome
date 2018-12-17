from setuptools import setup, find_packages
import sys
import codecs

"""
linux:
rm -rf "dist/*";rm -rf "build/*";python3 setup.py bdist_wheel;twine upload "dist/*;rm -rf "dist/*";rm -rf "build/*""
win32:
rm -rf dist;rm -rf build;python3 setup.py bdist_wheel;twine upload "dist/*";rm -rf dist;rm -rf build;rm -rf ichrome.egg-info
"""
version = "0.1.0"
if sys.version_info < (3, 6):
    sys.exit("pypinfo requires Python 3.6+")
py_version = sys.version_info
install_requires = ["psutil", "torequests", "websocket-client"]
with open("README.md", encoding="utf-8") as f:
    README = f.read()

setup(
    name="ichrome",
    version=version,
    keywords=("chrome"),
    description="toy for chrome devtools protocol. Read more: https://github.com/ClericPy/ichrome.",
    license="MIT License",
    install_requires=install_requires,
    long_description=README,
    long_description_content_type="text/markdown",
    py_modules=["ichrome"],
    author="ClericPy",
    author_email="clericpy@gmail.com",
    url="https://github.com/ClericPy/ichrome",
    packages=find_packages(),
    platforms="any",
    classifiers=[
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
    ],
)
