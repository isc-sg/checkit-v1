from distutils.core import setup
from Cython.Build import cythonize
fileSet = set()
fileSet.add("process_list_v3.py")
setup(description='Checkit Application',
      author='Sam Corbo',
      author_email='sam.corbo@isc.sg',
      ext_modules=cythonize(fileSet, language_level=3)
)

