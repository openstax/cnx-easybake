# -*- coding: utf-8 -*-
from setuptools import setup, find_packages

install_requires = (
    'cssselect',
    'cssselect2',
    'tinycss2',
    'lxml',
    'tinycss',
    )

setup(
    name='cnx-easybake',
    version='0.0.1',
    author='Connexions team',
    author_email='info@cnx.org',
    url="https://github.com/connexions/cnx-easybake",
    license='LGPL, See also LICENSE.txt',
    description='',
    packages=find_packages(),
    install_requires=install_requires,
    include_package_data=True,
    entry_points={
        'console_scripts': [
            'cnx-easybake = cnxeasybake.scripts.main:main',
            ],
        },
    dependency_links=['git+https://github.com/SimonSapin/cssselect2.git#egg=cssselect2']
    )
