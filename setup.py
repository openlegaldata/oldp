#!/usr/bin/env python

from __future__ import print_function

import codecs
import os
import re

from setuptools import setup, find_packages


def read(*parts):
    filename = os.path.join(os.path.dirname(__file__), *parts)
    with codecs.open(filename, encoding='utf-8') as fp:
        return fp.read()


def find_version(*file_paths):
    version_file = read(*file_paths)
    version_match = re.search(r"^__version__ = ['\"]([^'\"]*)['\"]",
                              version_file, re.M)
    if version_match:
        return version_match.group(1)
    raise RuntimeError("Unable to find version string.")


setup(
    name="oldp",
    version=find_version("oldp", "__init__.py"),
    url='https://github.com/legalresearch-io/oldp',
    license='MIT',
    description="Open Legal Data Platform",
    long_description=read('README.md'),
    author='Malte Schwarzer',
    author_email='hello@legalresearch.io',
    packages=find_packages(),
    install_requires=[
        'cssselect',
        'dj-database-url',
        'Django',
        'django-appconf',
        'django-compressor',
        'django-configurations',
        'django-filter',
        'django-mathfilters',
        'django-sass-processor',
        'django-stronghold',
        'django-tellme',
        'django-widget-tweaks',
        'djangorestframework',
        'elasticsearch',
        'elasticsearch-dsl',
        'gunicorn',
        'isodate',
        'libsass',
        'lxml',
        'Markdown',
        'mysqlclient',
        'nltk',
        'pdfminer.six',
        'Pillow',
        'pycryptodome',
        'pypandoc',
        'python-dateutil',
        'requests',
        'requests-toolbelt',
        'six',
        'SOAPpy',
        'stem',
        'urllib3',
        'whitenoise',
        'wstools',
        'zeep',
    ],
    include_package_data=True,
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Framework :: Django',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3.5',
        'Topic :: Utilities',
    ],
    zip_safe=False,
)
