from setuptools import setup

setup(
    name='fsrsync',
    version='#TAG_VERSION#',
    description='FSRsync is a Python package that provides a simple way to synchronize files between two directories based on inotify with locks.',
    author='Derek Demuro',
    author_email='fsrsync@detrashme.com',
    url='https://www.takelan.com/',
    license='Copyright 2019-2022 Derek Demuro',
    include_package_data=True,
    packages=['fsrsync', 'config', 'fsrsync.utils'],
    package_dir={
        'fsrsync': 'fsrsync',
        'fsrsync.utils': 'fsrsync/utils',
        'config': 'config',
        },
    package_data={
        'fsrsync': ['*'],
        'fsrsync.utils': ['*'],
        'config': ['*'],
    },
    install_requires=[
        'inotify_simple==1.3.5',
        'psutil==6.1.0',
        'sentry-sdk==2.17.0',
        'fastapi==0.115.3',
        'uvicorn==0.32.0',
        'python-multipart==0.0.16',
        'paramiko==3.5.0',
        'requests==2.32.3',
    ],
    zip_safe=True,
    entry_points={
        'console_scripts': [
            'fsrsync=fsrsync.app:main',
        ],
    },
)
