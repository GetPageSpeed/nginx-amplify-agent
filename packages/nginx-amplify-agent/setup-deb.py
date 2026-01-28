# -*- coding: utf-8 -*-
"""
Simplified setup.py for DEB builds.
This version doesn't import from the amplify package to avoid circular dependencies.
"""
from setuptools import setup, find_packages

__author__ = "GetPageSpeed"
__copyright__ = "Copyright (C) GetPageSpeed. All rights reserved."
__maintainer__ = "GetPageSpeed"
__email__ = "info@getpagespeed.com"

# For DEB builds, use lsb-base init script
data_files = [
    (
        "/etc/amplify-agent/",
        [
            "etc/agent.conf.default",
        ],
    ),
    ("/etc/logrotate.d/", ["etc/logrotate.d/amplify-agent"]),
    ("/etc/init.d/", ["etc/init.d/amplify-agent"]),
]

setup(
    name="nginx-amplify-agent",
    version="1.8.3",
    author="GetPageSpeed",
    author_email="info@getpagespeed.com",
    description="GetPageSpeed Amplify Agent",
    keywords="amplify agent nginx",
    url="https://amplify.getpagespeed.com/",
    packages=find_packages(
        exclude=[
            "*.test",
            "*.test.*",
            "test.*",
            "test",
            "tools",
            "tools.*",
            "packages",
            "packages.*",
        ]
    ),
    package_data={
        "amplify": [
            "certifi/*.pem",
            "gevent/*.so",
            "gevent/libev/*.so",
            "greenlet/*.so",
            "psutil/*.so",
            "*.so",
        ]
    },
    data_files=data_files,
    scripts=["nginx-amplify-agent.py"],
    entry_points={},
    long_description="GetPageSpeed Amplify Agent",
)
