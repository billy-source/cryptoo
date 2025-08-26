from decimal import Decimal
from django.db import models, transaction
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    balance = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal("10000.00"))  # $10,000 start

    def __str__(self):
        return f"{self.user.username} Profile - Balance: {self.balance}"


# Auto-create profile with starting balance on signup
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
    amount = models.DecimalField(max_digits=20, decimal_places=8)
    price = models.DecimalField(max_digits=20, decimal_places=8)
    timestamp = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.user.username} {self.side} {self.amount} {self.currency_pair.base_currency} @ {self.price}"

    @classmethod
    def execute(cls, user, currency, side, amount):
        """Executes a trade (buy/sell) with balance and holding checks."""
        amount = Decimal(amount)
        price = currency.current_price
        cost = amount * price

        with transaction.atomic():
            profile = user.profile
            holding, _ = Holding.objects.get_or_create(user=user, currency_pair=currency)

            if side == "BUY":
                if profile.balance < cost:
                    raise ValueError("Insufficient balance to buy.")
                profile.balance -= cost
                holding.amount += amount
                profile.save()
                holding.save()

            elif side == "SELL":
                if holding.amount < amount:
                    raise ValueError("Insufficient holdings to sell.")
                profile.balance += cost
                holding.amount -= amount
                profile.save()
                holding.save()

            # Save trade record
            return cls.objects.create(
                user=user,
                currency_pair=currency,
                side=side,
                amount=amount,
                price=price,
            )


class PriceHistory(models.Model):
    currency_pair = models.ForeignKey(Currency, on_delete=models.CASCADE)
    price = models.DecimalField(max_digits=20, decimal_places=8)
    timestamp = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.currency_pair.base_currency} @ {self.price} ({self.timestamp})"
