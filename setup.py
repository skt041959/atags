# encoding: utf-8

from setuptools import setup

setup(
    name='atags',
    version='0.0.1',
    description='Yet another tagging system',
    url='https://github.com/skt041959/atags',
    author='skt041959',
    author_email='skt041959@gmail.com',
    license='GPLv3',
    packages=['atags'],
    install_requires=['aiomultiprocess', 'pygments'],
    classifiers=[
        'Development Status :: 1 - Planning',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)',
        'Operating System :: POSIX :: Linux',
        'Programming Language :: Python :: 3.9',
    ],
    entry_points={'console_scripts': ['atags=atags:main']},
)
