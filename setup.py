# -*- coding: utf-8 -*-
"""
Copyright (C) 2016 Rice University.

This software is subject to the provisions of the
GNU AFFERO GENERAL PUBLIC LICENSE Version 3.0 (AGPL).
See LICENSE.txt for details.
"""
from setuptools import setup, find_packages
import versioneer

install_requires = (
    'cssselect',
    'cssselect2',
    'tinycss2',
    'lxml',
    'PyICU==1.9.8;platform_system=="Darwin"',  # FIXME link/symbol prob OSX
    'PyICU',
    )

tests_require = (
    'testfixtures', 'mock',
    )

setup(
    name='cnx-easybake',
    version=versioneer.get_version(),
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
    cmdclass=versioneer.get_cmdclass(),
    entry_points={
        'console_scripts': [
            'cnx-easybake = cnxeasybake.scripts.main:main',
            ],
        },
    dependency_links=[
        'git+https://github.com/Connexions/cssselect2.git#egg=cssselect2']
    )
