# -*- coding: utf-8 -*-
"""
Copyright (C) 2016 Rice University.

This software is subject to the provisions of the
GNU AFFERO GENERAL PUBLIC LICENSE Version 3.0 (AGPL).
See LICENSE.txt for details.
"""
from setuptools import setup, find_packages

install_requires = (
    'cssselect',
    'cssselect2',
    'tinycss2',
    'lxml',
    )

tests_require = (
    'testfixtures',
    )

setup(
    name='cnx-easybake',
    version='0.6.0',
    author='Connexions team',
    author_email='info@cnx.org',
    url="https://github.com/connexions/cnx-easybake",
    license='LGPL, See also LICENSE.txt',
    description='',
    packages=find_packages(),
    tests_require=tests_require,
    test_suite='cnxeasybake.tests',
    install_requires=install_requires,
    include_package_data=True,
    entry_points={
        'console_scripts': [
            'cnx-easybake = cnxeasybake.scripts.main:main',
            ],
        },
    dependency_links=[
        'git+https://github.com/SimonSapin/cssselect2.git#egg=cssselect2']
    )
