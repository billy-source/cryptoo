from django import forms
from decimal import Decimal
from .models import Currency, Trade

class TradeForm(forms.Form):
    currency_pair = forms.ModelChoiceField(
        queryset=Currency.objects.all(),
        widget=forms.Select(attrs={"class":"w-full border p-2 rounded"})
    )
    side = forms.ChoiceField(
        choices=Trade.SIDE_CHOICES,
        widget=forms.Select(attrs={"class":"w-full border p-2 rounded"})
    )
    amount = forms.DecimalField(
        min_value=Decimal("0.00000001"),
        decimal_places=8,
        max_digits=24,
        widget=forms.NumberInput(attrs={"class":"w-full border p-2 rounded","step":"0.00000001"})
    )
