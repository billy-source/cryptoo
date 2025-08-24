from django.urls import path
from . import views

urlpatterns = [
    path("", views.home_view, name="home"),
    path("signup/", views.signup_view, name="signup"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("history/", views.trade_history, name="trade_history"),
    path("api/price-history/<str:symbol>/", views.price_history_api, name="price_history_api"),
    path("api/update-prices/", views.update_prices_api, name="update_prices_api"),
]
