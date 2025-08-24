from decimal import Decimal, ROUND_DOWN
from django.db import models, transaction
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

QTY_PLACES = Decimal("0.00000001")
USD_PLACES = Decimal("0.01")

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    balance = models.DecimalField(max_digits=14, decimal_places=2, default=10000.00)  # USD

    def __str__(self):
        return f"{self.user.username}'s Profile"

class Currency(models.Model):
    base_currency = models.CharField(max_length=10)   # e.g. BTC
    quote_currency = models.CharField(max_length=10)  # e.g. USD
    current_rate = models.DecimalField(max_digits=20, decimal_places=8, default=0)  # price in quote

    class Meta:
        unique_together = ("base_currency", "quote_currency")

    def __str__(self):
        return f"{self.base_currency}/{self.quote_currency}"

class PriceHistory(models.Model):
    currency_pair = models.ForeignKey(Currency, on_delete=models.CASCADE, related_name="history")
    price = models.DecimalField(max_digits=20, decimal_places=8)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["timestamp"]

class Holding(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    currency_pair = models.ForeignKey(Currency, on_delete=models.CASCADE)
    quantity = models.DecimalField(max_digits=24, decimal_places=8, default=0)

    class Meta:
        unique_together = ("user", "currency_pair")

    @property
    def market_value(self):
        return (self.quantity * self.currency_pair.current_rate).quantize(USD_PLACES)

class Trade(models.Model):
    BUY = "BUY"
    SELL = "SELL"
    SIDE_CHOICES = ((BUY, "Buy"), (SELL, "Sell"))

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    currency_pair = models.ForeignKey(Currency, on_delete=models.CASCADE)
    side = models.CharField(max_length=4, choices=SIDE_CHOICES)
    amount = models.DecimalField(max_digits=24, decimal_places=8)  # base qty
    price = models.DecimalField(max_digits=20, decimal_places=8)   # exec price
    total_value = models.DecimalField(max_digits=20, decimal_places=8)  # amount * price
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]

    @staticmethod
    @transaction.atomic
    def execute(user, currency, side, amount):
        amount = Decimal(amount).quantize(QTY_PLACES, rounding=ROUND_DOWN)
        if amount <= 0:
            raise ValueError("Amount must be positive.")

        profile = user.profile
        holding, _ = Holding.objects.select_for_update().get_or_create(
            user=user, currency_pair=currency, defaults={"quantity": Decimal("0")}
        )

        price = currency.current_rate
        notional = (amount * price).quantize(Decimal("0.00000001"))

        if side == Trade.BUY:
            cost = notional.quantize(USD_PLACES)
            if profile.balance < cost:
                raise ValueError("Insufficient USD balance.")
            profile.balance = (profile.balance - cost).quantize(USD_PLACES)
            holding.quantity = (holding.quantity + amount).quantize(QTY_PLACES)
            profile.save(update_fields=["balance"])
            holding.save(update_fields=["quantity"])
        elif side == Trade.SELL:
            if holding.quantity < amount:
                raise ValueError("Insufficient crypto to sell.")
            proceeds = notional.quantize(USD_PLACES)
            holding.quantity = (holding.quantity - amount).quantize(QTY_PLACES)
            profile.balance = (profile.balance + proceeds).quantize(USD_PLACES)
            holding.save(update_fields=["quantity"])
            profile.save(update_fields=["balance"])
        else:
            raise ValueError("Invalid side.")

        return Trade.objects.create(
            user=user,
            currency_pair=currency,
            side=side,
            amount=amount,
            price=price,
            total_value=notional,
        )

@receiver(post_save, sender=User)
def create_or_update_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)
    else:
        Profile.objects.get_or_create(user=instance)
