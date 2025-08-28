from decimal import Decimal
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseBadRequest
from django.shortcuts import render, redirect, get_object_or_404

from .models import Currency, Holding, Trade, PriceHistory, Profile
from .forms import TradeForm
from .tasks import fetch_and_update_prices


def home_view(request):
    return render(request, "home.html")


def signup_view(request):
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "")
        confirm = request.POST.get("confirm_password", "")

        from django.contrib.auth.models import User
        if not username or not password:
            messages.error(request, "Username and password required.")
            return redirect("signup")
        if password != confirm:
            messages.error(request, "Passwords do not match.")
            return redirect("signup")
        if User.objects.filter(username=username).exists():
            messages.error(request, "Username already taken.")
            return redirect("signup")

        # Create user
        user = User.objects.create_user(username=username, email=email, password=password)

        # Create profile with $10,000
        Profile.objects.get_or_create(user=user, defaults={"balance": Decimal("10000.00")})

        login(request, user)
        return redirect("dashboard")
    return render(request, "signup.html")


def login_view(request):
    if request.method == "POST":
        username = request.POST.get("username", "")
        password = request.POST.get("password", "")
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            return redirect("dashboard")
        messages.error(request, "Invalid credentials.")
        return redirect("login")
    return render(request, "login.html")


def logout_view(request):
    logout(request)
    return redirect("login")


@login_required
def dashboard(request):
    if request.GET.get("refresh") == "1":
        try:
            fetch_and_update_prices()
            messages.info(request, "Prices refreshed.")
        except Exception as e:
            messages.error(request, f"Price refresh failed: {e}")

    currencies = Currency.objects.all().order_by("base_currency")
    holdings = Holding.objects.filter(user=request.user).select_related("currency_pair")
    recent_trades = Trade.objects.filter(user=request.user).order_by("-timestamp")[:10]

    # Always ensure profile exists
    profile, _ = Profile.objects.get_or_create(
        user=request.user, defaults={"balance": Decimal("10000.00")}
    )
    cash = profile.balance

    portfolio_value = sum(h.market_value for h in holdings)
    total_equity = cash + portfolio_value

    if request.method == "POST":
        form = TradeForm(request.POST)
        if form.is_valid():
            currency = form.cleaned_data["currency_pair"]
            side = form.cleaned_data["side"]
            amount = Decimal(form.cleaned_data["amount"])

            # ✅ Ensure amount > 0
            if amount <= 0:
                messages.error(request, "Amount must be greater than 0.")
                return redirect("dashboard")

            try:
                # Use Trade.execute which must handle real balance checks
                Trade.execute(request.user, currency, side, amount)
                messages.success(
                    request,
                    f"{side.upper()} {amount} {currency.base_currency} executed successfully.",
                )
                return redirect("dashboard")
            except ValueError as e:
                messages.error(request, str(e))
        else:
            messages.error(request, "Fix form errors.")
    else:
        form = TradeForm()

    return render(
        request,
        "dashboard.html",
        {
            "currencies": currencies,
            "holdings": holdings,
            "trades": recent_trades,
            "form": form,
            "cash": cash,
            "portfolio_value": portfolio_value,
            "total_equity": total_equity,
        },
    )


@login_required
def trade_history(request):
    trades = Trade.objects.filter(user=request.user).select_related("currency_pair").order_by("-timestamp")
    return render(request, "trade_history.html", {"trades": trades})


def price_history_api(request, symbol):
    symbol = symbol.upper()
    pair = get_object_or_404(Currency, base_currency=symbol, quote_currency="USD")
    rows = PriceHistory.objects.filter(currency_pair=pair).order_by("timestamp").values("timestamp", "price")[:500]
    return JsonResponse(
        {
            "symbol": symbol,
            "timestamps": [r["timestamp"].isoformat() for r in rows],
            "prices": [str(r["price"]) for r in rows],
        }
    )


def update_prices_api(request):
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")
    try:
        fetch_and_update_prices()
        return JsonResponse({"ok": True})
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)
