python setup.py build_ext --inplace
cp main_menu/*.py ~/py-modded/
rm main_menu/*.py
cp ~/py-modded/__init__.py ~/py-modded/start.py main_menu

