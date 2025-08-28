from decimal import Decimal
from django.db import models, transaction
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
import requests


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    balance = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal("10000.00"))  # $10,000 start

    def __str__(self):
        return f"{self.user.username} Profile - Balance: {self.balance}"


@receiver(post_save, sender=User)
def create_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)


class Currency(models.Model):
    base_currency = models.CharField(max_length=10)  # e.g. BTC
    quote_currency = models.CharField(max_length=10, default="USD")
    current_price = models.DecimalField(max_digits=20, decimal_places=8, default=Decimal("0.0"))

    class Meta:
        unique_together = ("base_currency", "quote_currency")

    def __str__(self):
        return f"{self.base_currency}/{self.quote_currency}"

    def update_price(self):
        """Fetch real-time price from CoinGecko API."""
        try:
            url = f"https://api.coingecko.com/api/v3/simple/price?ids={self.base_currency.lower()}&vs_currencies={self.quote_currency.lower()}"
            response = requests.get(url).json()
            new_price = Decimal(str(response[self.base_currency.lower()][self.quote_currency.lower()]))
            self.current_price = new_price
            self.save()

            PriceHistory.objects.create(currency_pair=self, price=new_price)
            return new_price
        except Exception:
            return self.current_price  # fallback if API fails


class Holding(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    currency_pair = models.ForeignKey(Currency, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=20, decimal_places=8, default=Decimal("0.0"))

    @property
    def market_value(self):
        return self.amount * self.currency_pair.current_price

    def __str__(self):
        return f"{self.user.username} - {self.currency_pair.base_currency}: {self.amount}"


class Trade(models.Model):
    SIDE_CHOICES = (("BUY", "Buy"), ("SELL", "Sell"))

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    currency_pair = models.ForeignKey(Currency, on_delete=models.CASCADE)
    side = models.CharField(max_length=4, choices=SIDE_CHOICES)
    amount = models.DecimalField(max_digits=20, decimal_places=8)  # crypto amount (BTC, ETH)
    usd_value = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal("0.00"))  # new field
    price = models.DecimalField(max_digits=20, decimal_places=8)
    timestamp = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.user.username} {self.side} {self.amount} {self.currency_pair.base_currency} @ {self.price}"

    @classmethod
    def execute(cls, user, currency, side, usd_amount):
        """
        Executes a trade (buy/sell).
        Users enter USD value they want to trade, not raw crypto amount.
        """
        usd_amount = Decimal(usd_amount)
        price = currency.update_price()

        # Convert USD value to crypto units (e.g. $100 / $60,000 = 0.001666 BTC)
        crypto_amount = usd_amount / price

        with transaction.atomic():
            profile = user.profile
            holding, _ = Holding.objects.get_or_create(user=user, currency_pair=currency)

            if side == "BUY":
                if profile.balance < usd_amount:
                    raise ValueError("Insufficient balance to buy.")
                profile.balance -= usd_amount
                holding.amount += crypto_amount
                profile.save()
                holding.save()

            elif side == "SELL":
                if holding.amount < crypto_amount:
                    raise ValueError("Insufficient holdings to sell.")
                profile.balance += usd_amount
                holding.amount -= crypto_amount
                profile.save()
                holding.save()

            return cls.objects.create(
                user=user,
                currency_pair=currency,
                side=side,
                amount=crypto_amount,
                usd_value=usd_amount,
                price=price,
            )


class PriceHistory(models.Model):
    currency_pair = models.ForeignKey(Currency, on_delete=models.CASCADE)
    price = models.DecimalField(max_digits=20, decimal_places=8)
    timestamp = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.currency_pair.base_currency} @ {self.price} ({self.timestamp})"
