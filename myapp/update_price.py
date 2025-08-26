from django.core.management.base import BaseCommand
from myapp.tasks import fetch_and_update_prices

class Command(BaseCommand):
    help = "Fetch latest crypto prices from CoinGecko and store to DB."

    def handle(self, *args, **options):
        fetch_and_update_prices()
        self.stdout.write(self.style.SUCCESS("Prices updated."))