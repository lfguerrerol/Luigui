"""
Deterministic sample catalog so the system runs without any API keys.

Prices/ranks are illustrative but internally consistent (real discounts,
plausible Amazon prices) so the profitability math produces realistic output.
Replace these connectors with live API calls by setting the relevant API keys.
"""
from __future__ import annotations

from .models import RetailProduct, AmazonInsight


# Each entry: retail product + the Amazon insight it maps to.
SAMPLE_CATALOG = [
    {
        "product": RetailProduct(
            source="Walmart", source_sku="WM-55231", upc="0819396021133",
            title="Ninja Air Fryer 4-Qt", category="home_kitchen",
            url="https://www.walmart.com/ip/55231", list_price=99.00, sale_price=59.00,
            weight_lb=8.0, dimensions_cuft=0.55,
        ),
        "insight": AmazonInsight(
            asin="B07FDJMC9Q", amazon_price=109.99, sales_rank=420,
            est_monthly_sales=2100, rating=4.7, review_count=48210,
            offer_count=6, is_amazon_selling=False, provider="Keepa",
        ),
    },
    {
        "product": RetailProduct(
            source="Target", source_sku="TG-88120", upc="0490000021211",
            title="LEGO Botanical Wildflower Bouquet", category="toys_games",
            url="https://www.target.com/p/88120", list_price=59.99, sale_price=41.99,
            weight_lb=1.6, dimensions_cuft=0.20,
        ),
        "insight": AmazonInsight(
            asin="B0C4F7YM12", amazon_price=59.99, sales_rank=310,
            est_monthly_sales=1800, rating=4.9, review_count=12040,
            offer_count=4, is_amazon_selling=False, provider="Helium10",
        ),
    },
    {
        "product": RetailProduct(
            source="Home Depot", source_sku="HD-33417", upc="0885911632119",
            title="DEWALT 20V MAX Cordless Drill Kit", category="tools_home_improvement",
            url="https://www.homedepot.com/p/33417", list_price=169.00, sale_price=99.00,
            weight_lb=5.2, dimensions_cuft=0.40,
        ),
        "insight": AmazonInsight(
            asin="B00ET5VMTU", amazon_price=159.00, sales_rank=210,
            est_monthly_sales=3400, rating=4.8, review_count=31900,
            offer_count=9, is_amazon_selling=True, provider="JungleScout",
        ),
    },
    {
        "product": RetailProduct(
            source="Costco", source_sku="CO-71190", upc="0722252186102",
            title="Waterpik Aquarius Water Flosser (2-pack)", category="health_beauty",
            url="https://www.costco.com/71190", list_price=89.99, sale_price=64.99,
            weight_lb=4.4, dimensions_cuft=0.60,
        ),
        "insight": AmazonInsight(
            asin="B00HFQQ0VU", amazon_price=99.99, sales_rank=680,
            est_monthly_sales=1500, rating=4.6, review_count=88120,
            offer_count=7, is_amazon_selling=False, provider="Keepa",
        ),
    },
    {
        "product": RetailProduct(
            source="Sam's Club", source_sku="SC-40028", upc="0681131721103",
            title="Instant Pot Duo 6-Qt Pressure Cooker", category="home_kitchen",
            url="https://www.samsclub.com/p/40028", list_price=99.00, sale_price=69.00,
            weight_lb=11.8, dimensions_cuft=0.80,
        ),
        "insight": AmazonInsight(
            asin="B00FLYWNYQ", amazon_price=99.95, sales_rank=520,
            est_monthly_sales=1900, rating=4.7, review_count=152000,
            offer_count=12, is_amazon_selling=False, provider="SellerAmp",
        ),
    },
    {
        "product": RetailProduct(
            source="Walmart", source_sku="WM-90311", upc="0193575024113",
            title="Crayola Ultimate Crayon Collection 152ct", category="toys_games",
            url="https://www.walmart.com/ip/90311", list_price=24.99, sale_price=13.99,
            weight_lb=2.1, dimensions_cuft=0.15,
        ),
        "insight": AmazonInsight(
            asin="B00XNXRQK6", amazon_price=29.99, sales_rank=1250,
            est_monthly_sales=900, rating=4.8, review_count=22400,
            offer_count=5, is_amazon_selling=False, provider="Keepa",
        ),
    },
    {
        "product": RetailProduct(
            source="Target", source_sku="TG-51002", upc="0885909950126",
            title="Anker PowerCore 10000 Portable Charger", category="electronics",
            url="https://www.target.com/p/51002", list_price=25.99, sale_price=15.99,
            weight_lb=0.5, dimensions_cuft=0.05,
        ),
        "insight": AmazonInsight(
            asin="B0194WDVHI", amazon_price=27.99, sales_rank=95,
            est_monthly_sales=5200, rating=4.7, review_count=201000,
            offer_count=15, is_amazon_selling=True, provider="Helium10",
        ),
    },
    {
        "product": RetailProduct(
            source="Home Depot", source_sku="HD-77410", upc="0648846011113",
            title="Husky 46-in 9-Drawer Tool Chest", category="tools_home_improvement",
            url="https://www.homedepot.com/p/77410", list_price=498.00, sale_price=348.00,
            weight_lb=210.0, dimensions_cuft=18.0,
        ),
        "insight": AmazonInsight(
            asin="B08XXXXOVR", amazon_price=629.00, sales_rank=8800,
            est_monthly_sales=120, rating=4.5, review_count=1400,
            offer_count=3, is_amazon_selling=False, provider="JungleScout",
        ),
    },
    {
        "product": RetailProduct(
            source="Costco", source_sku="CO-22087", upc="0037000930112",
            title="Dyson V8 Cordless Vacuum", category="home_kitchen",
            url="https://www.costco.com/22087", list_price=429.00, sale_price=299.00,
            weight_lb=5.8, dimensions_cuft=0.90,
        ),
        "insight": AmazonInsight(
            asin="B0748GHXQK", amazon_price=419.00, sales_rank=340,
            est_monthly_sales=2600, rating=4.7, review_count=64000,
            offer_count=8, is_amazon_selling=False, provider="Keepa",
        ),
    },
    {
        "product": RetailProduct(
            source="Sam's Club", source_sku="SC-60155", upc="0037000112211",
            title="Tide PODS Laundry Detergent 112ct", category="grocery",
            url="https://www.samsclub.com/p/60155", list_price=27.98, sale_price=19.98,
            weight_lb=4.9, dimensions_cuft=0.30,
        ),
        "insight": AmazonInsight(
            asin="B00OI0V9SU", amazon_price=32.99, sales_rank=60,
            est_monthly_sales=7400, rating=4.8, review_count=98000,
            offer_count=11, is_amazon_selling=True, provider="SellerAmp",
        ),
    },
]
