import bootstrap_datepicker_plus
from django import forms
from bootstrap_datepicker_plus.widgets import DatePickerInput
from .models import Camera, EngineState

__version__ = 2.1


REGIONS = []
for i in range(1, 65):
    REGIONS.append((str(i),str(i)))
# REGIONS = [("1", "1"), ("2", "2"), ("3", "3"), ("4", "4"), ("5", "5"), ("6", "6"), ("7", "7"), ("8", "8")]


class DateForm(forms.Form):
    select_date = forms.DateField(widget=DatePickerInput(options={"format": "%m/%d/%Y"}))


class RegionsForm(forms.Form):
    regions = forms.MultipleChoiceField(required=False, widget=forms.CheckboxSelectMultiple(), choices=REGIONS)


class FilterForm(forms.Form):
    # Define fields for each filter you want to provide
    # status = forms.ChoiceField(choices=[('active', 'Active'), ('inactive', 'Inactive')], required=False)
    # category = forms.ChoiceField(choices=[('category1', 'Category 1'), ('category2', 'Category 2')], required=False)
    camera_number = forms.IntegerField(widget=forms.NumberInput)
    version = forms.ChoiceField(
        required=False,
        choices=[],  # set at runtime
        widget=forms.Select(attrs={'disabled': 'disabled'})
    )

    def __init__(self, *args, version_choices=None, **kwargs):
        super().__init__(*args, **kwargs)
        if version_choices:
            self.fields['version'].choices = version_choices
            # enable when actually have versions
            self.fields['version'].widget.attrs.pop('disabled', None)

