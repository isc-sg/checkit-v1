import bootstrap_datepicker_plus
from django import forms
from bootstrap_datepicker_plus.widgets import DatePickerInput
from .models import Camera, EngineState

REGIONS = []
for i in range(1, 65):
    REGIONS.append((str(i),str(i)))
# REGIONS = [("1", "1"), ("2", "2"), ("3", "3"), ("4", "4"), ("5", "5"), ("6", "6"), ("7", "7"), ("8", "8")]


class DateForm(forms.Form):
    select_date = forms.DateField(widget=DatePickerInput(options={"format": "%m/%d/%Y"}))


class RegionsForm(forms.Form):
    regions = forms.MultipleChoiceField(required=False, widget=forms.CheckboxSelectMultiple(), choices=REGIONS)
