"""
Setup файл для установки плагина netbox-obudozer

Используется для установки плагина в NetBox.
"""
import os
from setuptools import find_packages, setup

setup(
    name='netbox-obudozer',
    version='0.2.1',
    description='Плагин управления ресурсами ЦОД с интеграцией VMware vCenter',
    long_description=open('README.md').read() if os.path.exists('README.md') else '',
    long_description_content_type='text/markdown',
    author='Виктор Стеганцев',
    author_email='your.email@example.com',
    license='Apache 2.0',
    url='https://github.com/Braminn/netbox-obudozer',
    install_requires=[],
    packages=find_packages(),
    include_package_data=True,
    zip_safe=False,
    python_requires='>=3.10',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Framework :: Django',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: Apache Software License',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
    ],
)
