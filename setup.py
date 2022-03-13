from distutils.core import setup
from Cython.Build import cythonize
fileSet = set()
fileSet.add("main_menu/views.py")
fileSet.add("main_menu/models.py")
fileSet.add("main_menu/tables.py")
fileSet.add("main_menu/admin.py")
fileSet.add("main_menu/apps.py")
fileSet.add("main_menu/forms.py")
fileSet.add("main_menu/urls.py")
fileSet.add("main_menu/filters.py")
fileSet.add("main_menu/resources.py")
setup(
   ext_modules=cythonize(fileSet)
)
