import re
from setuptools import setup, find_packages


def get_version():
    with open('agentframe/__init__.py', 'r') as f:
        version_match = re.search(r"^__version__ = ['\"]([^'\"]*)['\"]", f.read(), re.M)
        if version_match:
            return version_match.group(1)
    raise RuntimeError("Unable to find version string.")


setup(
    name="agentframe",
    version=get_version(),
    packages=find_packages(),
    # Include additional data files from the package
    package_data={
        'agentframe': ['prompts/*.md'],
    },
    # The rest of the metadata is in pyproject.toml
)
