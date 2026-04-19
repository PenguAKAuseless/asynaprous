#
# Copyright (C) 2026 pdnguyen of HCMC University of Technology VNU-HCM.
# All rights reserved.
# This file is part of the CO3093/CO3094 course.
#
# AsynapRous release
#
# The authors hereby grant to Licensee personal permission to use
# and modify the Licensed Source Code for the sole purpose of studying
# while attending the course
#

"""Application package entrypoints."""


def create_sampleapp(ip, port):
	"""Lazy loader to avoid circular imports during daemon bootstrapping."""
	from .sampleapp import create_sampleapp as _create_sampleapp

	return _create_sampleapp(ip, port)
