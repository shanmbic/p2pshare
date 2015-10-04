from setuptools import setup

setup(name='p2pshare',
      version='0.1',
      description='Peer to Peer file sharing Network',
      long_description=open("README.rst").read(), 
      url='http://github.com/shanmbic/p2pshare',
      author='Shantanu',
      author_email='shantanu1002@gmail.com',
      license="LICENSE.rst",
      packages=['p2pshare'],
      scripts=['bin/p2pshare'],
      zip_safe=False)