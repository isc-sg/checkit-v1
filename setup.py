from distutils.core import setup
from Cython.Build import cythonize
fileSet = set()
fileSet.add("main_menu/a_eye.py")
fileSet.add("main_menu/admin.py")
fileSet.add("main_menu/apps.py")
fileSet.add("main_menu/compare_images_v4.py")
fileSet.add("main_menu/filters.py")
fileSet.add("main_menu/forms.py")
fileSet.add("main_menu/models.py")
fileSet.add("main_menu/process_list_v2.py")
fileSet.add("main_menu/mysql_connection_pool_test.py")
fileSet.add("main_menu/resources.py")
fileSet.add("main_menu/select_region.py")
fileSet.add("main_menu/tables.py")
fileSet.add("main_menu/urls.py")
fileSet.add("main_menu/views.py")
fileSet.add("main_menu/serializers.py")
setup(description='Checkit Application',
      author='Sam Corbo',
      author_email='sam.corbo@isc.sg',
      ext_modules=cythonize(fileSet, language_level=3)
)

