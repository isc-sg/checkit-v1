import bootstrap_datepicker_plus
from django import forms
from bootstrap_datepicker_plus import DatePickerInput
from .models import Camera

REGIONS = []
for i in range(1,65):
    REGIONS.append((str(i),str(i)))
# REGIONS = [("1", "1"), ("2", "2"), ("3", "3"), ("4", "4"), ("5", "5"), ("6", "6"), ("7", "7"), ("8", "8")]


CONTACT_PREFERENCE = [
    ('email', 'Email'),
    ('chat', 'Chat'),
    ('call', 'Call'),
]

class DateForm(forms.Form):
    select_date = forms.DateField(widget=DatePickerInput(format='%m/%d/%Y'))


class RegionsForm(forms.Form):
    regions = forms.MultipleChoiceField(required=False, widget=forms.CheckboxSelectMultiple(), choices=REGIONS)



class TestForm(forms.Form):
    image_regions = forms.MultipleChoiceField(
        choices=REGIONS,
        widget=forms.CheckboxSelectMultiple()
    )

    class Meta:
        model = Camera
        fields = ('image_regions',)