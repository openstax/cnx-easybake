# -*- coding: utf-8 -*-
from setuptools import setup, find_packages

install_requires = (
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
        },
    )
