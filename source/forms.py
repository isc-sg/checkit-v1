import bootstrap_datepicker_plus
from django import forms
<<<<<<< HEAD
from bootstrap_datepicker_plus import DatePickerInput
from .models import Camera, EngineState

REGIONS = []
for i in range(1,65):
=======
from bootstrap_datepicker_plus.widgets import DatePickerInput
from .models import Camera, EngineState

REGIONS = []
for i in range(1, 65):
>>>>>>> added heap of changes that were not pushed up since september 2022.  Some known - fixed bug with pdf creation where log or reference image were deleted.  Added code to push message to synergy. Current version has Synergy skin
    REGIONS.append((str(i),str(i)))
# REGIONS = [("1", "1"), ("2", "2"), ("3", "3"), ("4", "4"), ("5", "5"), ("6", "6"), ("7", "7"), ("8", "8")]


class DateForm(forms.Form):
<<<<<<< HEAD
    select_date = forms.DateField(widget=DatePickerInput(format='%m/%d/%Y'))
=======
    select_date = forms.DateField(widget=DatePickerInput(options={"format": "%m/%d/%Y"}))
>>>>>>> added heap of changes that were not pushed up since september 2022.  Some known - fixed bug with pdf creation where log or reference image were deleted.  Added code to push message to synergy. Current version has Synergy skin


class RegionsForm(forms.Form):
    regions = forms.MultipleChoiceField(required=False, widget=forms.CheckboxSelectMultiple(), choices=REGIONS)
