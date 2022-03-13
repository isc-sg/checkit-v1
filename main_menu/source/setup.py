from distutils.core import setup
from Cython.Build import cythonize
fileSet = set()
fileSet.add("views.py")
fileSet.add("models.py")
fileSet.add("tables.py")
fileSet.add("admin.py")
fileSet.add("apps.py")
fileSet.add("forms.py")
fileSet.add("urls.py")
fileSet.add("filters.py")
fileSet.add("compare_images_v4.py")
fileSet.add("process_list_v2.py")
fileSet.add("select_region.py")
fileSet.add("a_eye.py")
setup(
   ext_modules=cythonize(fileSet)
)
