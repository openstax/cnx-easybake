# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2016, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
"""Implements baking in a subset of CSS3 content spec into HTML."""
from .oven import Oven  # noqa

from ._version import get_versions
__version__ = get_versions()['version']
del get_versions
