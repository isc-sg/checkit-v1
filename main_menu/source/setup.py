from distutils.core import setup
from Cython.Build import cythonize
fileSet = set()
fileSet.add("a_eye.py")
fileSet.add("admin.py")
fileSet.add("apps.py")
fileSet.add("compare_images_v4.py")
fileSet.add("filters.py")
fileSet.add("forms.py")
fileSet.add("models.py")
fileSet.add("process_list_v2.py")
fileSet.add("resources.py")
fileSet.add("select_region.py")
fileSet.add("tables.py")
fileSet.add("urls.py")
fileSet.add("views.py")
setup(
   ext_modules=cythonize(fileSet)
)
