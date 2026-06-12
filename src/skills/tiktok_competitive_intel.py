"""TikTok Shop Competitive Intelligence Skill — Malaysia/SEA Market.

Simulates monitoring of competitor pricing, sales velocity, ad campaigns,
and fraud-risk signals across TikTok Shop, Shopee, and Lazada.

!! PRODUCTION NOTE !!
Replace the mock-data providers with real API integrations:
  - TikTok Shop Affiliate / Shop API (REST)
  - Shopee Open Platform API (v2)
  - Lazada Seller Center API (Lazada Open Platform)
The mock layer below returns realistic synthetic data for schema demonstration
and pipeline testing on base-sepolia.
"""

from __future__ import annotations

import logging
import random
import time
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# ── Mock product catalogue — realistic SEA cross-border products ──────────────

PRODUCT_TEMPLATES: list[dict[str, Any]] = [
    {
        "name": "Whitening Vitamin C Serum 30ml",
        "price_range": (3.50, 12.90),
        "velocity_range": (15, 340),
        "rating_range": (3.8, 4.9),
        "review_range": (120, 8500),
        "seller_prefixes": ["SKINTIFIC_ID", "the_originote", "Glorist_official", "AvoskinOfficial", "SomethincOfficial"],
        "follower_range": (5000, 850_000),
    },
    {
        "name": "LED Light Facial Mask Therapy",
        "price_range": (18.00, 89.00),
        "velocity_range": (5, 120),
        "rating_range": (3.5, 4.7),
        "review_range": (40, 3200),
        "seller_prefixes": ["beautyasia_my", "Derma_Expert", "skincare_global_my", "GadgetBeauty"],
        "follower_range": (2000, 120_000),
    },
    {
        "name": "Magnetic Cable 3in1 Fast Charging",
        "price_range": (1.50, 6.90),
        "velocity_range": (50, 900),
        "rating_range": (4.0, 4.8),
        "review_range": (300, 18000),
        "seller_prefixes": ["baseus_my", "ugreen_official", "anker_my", "xiaomi_my_global"],
        "follower_range": (8000, 450_000),
    },
    {
        "name": "Air Fryer Paper Liners 100pcs",
        "price_range": (1.80, 4.50),
        "velocity_range": (80, 1200),
        "rating_range": (4.2, 4.9),
        "review_range": (500, 25000),
        "seller_prefixes": ["daiso_malaysia", "mr_diy_my", "kitchenboss_my", "homeshop_sea"],
        "follower_range": (15000, 620_000),
    },
    {
        "name": "Collagen Gummy Bears Jar 60s",
        "price_range": (8.00, 24.00),
        "velocity_range": (20, 280),
        "rating_range": (3.7, 4.6),
        "review_range": (80, 5200),
        "seller_prefixes": ["blackmores_my", "swisse_sea", "nature_vit_my", "healthlane_official"],
        "follower_range": (12000, 510_000),
    },
    {
        "name": "Stand Mixer 6 Speed 4.5L",
        "price_range": (45.00, 189.00),
        "velocity_range": (3, 60),
        "rating_range": (3.9, 4.7),
        "review_range": (20, 1800),
        "seller_prefixes": ["philips_my", "kitchenaid_sea", "elba_my", "cuckoo_official_my"],
        "follower_range": (5000, 280_000),
    },
]

FRAUD_SIGNALS = [
    "review_timing_anomaly — 80% reviews posted within 48h window",
    "price_below_market_avg_60pct — flagrant underpricing vs. median",
    "seller_account_age_lt_30_days — new store with high velocity",
    "stock_quantity_mismatch — claims >10k stock but <100 reviews",
    "image_reuse_detected — listing images match 3+ other deactivated stores",
]

AD_CAMPAIGN_TEMPLATES = [
    {"seller": "SKINTIFIC_ID", "est_monthly_spend": 45_000, "campaigns": 12, "platforms": ["tiktok", "instagram"]},
    {"seller": "the_originote", "est_monthly_spend": 28_000, "campaigns": 8, "platforms": ["tiktok", "shopee_ads"]},
    {"seller": "baseus_my", "est_monthly_spend": 35_000, "campaigns": 15, "platforms": ["tiktok", "lazada_sponsored"]},
    {"seller": "Glorist_official", "est_monthly_spend": 12_000, "campaigns": 5, "platforms": ["tiktok"]},
    {"seller": "philips_my", "est_monthly_spend": 62_000, "campaigns": 20, "platforms": ["tiktok", "shopee", "lazada", "google"]},
]

CATEGORY_TRENDS: dict[str, str] = {
    "skincare": "Rising — Vitamin C/Retinol serums dominate MY TikTok Shop with 34% QoQ growth",
    "electronics": "Stable — magnetic cables and earbuds maintain >200 units/day velocity",
    "kitchen": "Growing — Air fryer accessories + stand mixers peak ahead of 11.11 and CNY",
    "health": "Steady — Collagen and vitamin gummies see 12% MoM growth across Shopee/Lazada",
    "beauty": "High — LED masks and sheet masks sustain top-10 category ranking in MY region",
}


# ── Public entry point ───────────────────────────────────────────────────────


def execute(params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run TikTok Shop competitive intelligence scan.

    Args:
        params: Must contain ``keyword`` (str). Optional fields:
            market, platforms, max_competitors, include_ad_creatives, fraud_screening.

    Returns:
        Strict JSON Schema per ``output_schema`` in manifest:
        status, keyword, market, competitor_metrics, fraud_risk_score,
        market_insights, raw_timestamp.
    """
    if not params or "keyword" not in params:
        return {
            "status": "error",
            "error": "Missing required parameter: keyword",
            "raw_timestamp": time.time(),
        }

    keyword: str = params["keyword"]
    market: str = params.get("market", "malaysia")
    platforms: list[str] = params.get("platforms", ["tiktok_shop", "shopee", "lazada"])
    max_competitors: int = min(params.get("max_competitors", 10), 50)
    include_ads: bool = params.get("include_ad_creatives", False)
    fraud_screening: bool = params.get("fraud_screening", True)

    scan_ts = datetime.now(timezone.utc).isoformat()
    epoch_now = time.time()

    # ── Seed RNG deterministically from keyword for reproducible mocks ─────
    rng = random.Random(keyword + market)

    # ── Match product template ─────────────────────────────────────────────
    template: dict[str, Any] | None = None
    for t in PRODUCT_TEMPLATES:
        if any(word.lower() in keyword.lower() for word in t["name"].split()):
            template = t
            break
    if template is None:
        template = rng.choice(PRODUCT_TEMPLATES)

    # ── Generate synthetic competitors ─────────────────────────────────────
    competitor_count = min(rng.randint(4, 18), max_competitors)
    top_competitors: list[dict[str, Any]] = []
    total_velocity = 0
    total_price = 0.0
    prices: list[float] = []

    for rank in range(1, competitor_count + 1):
        platform = rng.choice(platforms)
        price = round(rng.uniform(*template["price_range"]), 2)
        velocity = rng.randint(*template["velocity_range"])
        rating = round(rng.uniform(*template["rating_range"]), 1)
        reviews = rng.randint(*template["review_range"])
        seller = rng.choice(template["seller_prefixes"])

        entry: dict[str, Any] = {
            "rank": rank,
            "product_name": f"{template['name']} — {seller}",
            "platform": platform,
            "price_usd": price,
            "sales_velocity": velocity,
            "rating": rating,
            "review_count": reviews,
            "seller_name": seller,
            "seller_followers": rng.randint(*template["follower_range"]),
            "ad_active": rng.random() > 0.55,
            "listing_url": f"https://www.{platform.replace('_', '.')}.com/products/{rng.randint(100000, 999999)}",
        }

        if include_ads and entry["ad_active"]:
            entry["ad_creatives"] = [
                f"https://ads.{platform}.com/creative/{rng.randint(10000, 99999)}.jpg"
                for _ in range(rng.randint(1, 3))
            ]

        top_competitors.append(entry)
        total_velocity += velocity
        total_price += price
        prices.append(price)

    prices.sort()
    median_price = prices[len(prices) // 2] if prices else 0.0
    avg_price = round(total_price / len(prices), 2) if prices else 0.0
    avg_velocity = total_velocity // len(top_competitors) if top_competitors else 0

    # ── Fraud screening ─────────────────────────────────────────────────────
    fraud_score: dict[str, Any] = {
        "overall_risk": "low",
        "suspicious_listings": [],
        "price_anomaly_detected": False,
        "review_manipulation_flag": False,
    }

    if fraud_screening:
        suspicious: list[dict[str, Any]] = []
        price_anomaly = False
        review_flag = False

        for comp in top_competitors:
            risk_factors: list[str] = []
            # Price anomaly heuristic
            if comp["price_usd"] < avg_price * 0.4:
                risk_factors.append(FRAUD_SIGNALS[1])
                price_anomaly = True
            # Review-to-velocity ratio heuristic
            if comp["review_count"] > 0 and comp["sales_velocity"] > 0:
                ratio = comp["review_count"] / comp["sales_velocity"]
                if ratio < 0.3 and comp["review_count"] > 500:
                    risk_factors.append(FRAUD_SIGNALS[0])
                    review_flag = True
            # New seller heuristic
            if rng.random() < 0.12:
                risk_factors.append(FRAUD_SIGNALS[2])

            if risk_factors:
                suspicious.append({
                    "product_name": comp["product_name"],
                    "risk_factors": risk_factors,
                    "confidence": round(rng.uniform(0.55, 0.95), 2),
                })

        fraud_score = {
            "overall_risk": "critical" if len(suspicious) > 5 else (
                "high" if len(suspicious) > 3 else (
                    "medium" if len(suspicious) > 1 else "low"
                )
            ),
            "suspicious_listings": suspicious[:8],
            "price_anomaly_detected": price_anomaly,
            "review_manipulation_flag": review_flag,
        }

    # ── Market insights ────────────────────────────────────────────────────
    category_key = "skincare" if any(w in keyword.lower() for w in ["serum", "cream", "skin"]) else \
                   "electronics" if any(w in keyword.lower() for w in ["cable", "charger", "magnetic"]) else \
                   "kitchen" if any(w in keyword.lower() for w in ["fryer", "mixer", "liner"]) else \
                   "health" if any(w in keyword.lower() for w in ["collagen", "vitamin", "gummy"]) else \
                   "beauty"
    trend = CATEGORY_TRENDS.get(category_key, "Stable — no significant deviation detected")

    top_advertisers: list[dict[str, Any]] = []
    if include_ads:
        for ad in AD_CAMPAIGN_TEMPLATES:
            if any(comp["seller_name"] == ad["seller"] for comp in top_competitors):
                top_advertisers.append({
                    "seller_name": ad["seller"],
                    "est_monthly_ad_spend_usd": ad["est_monthly_spend"],
                    "active_campaigns": ad["campaigns"],
                })
        top_advertisers.sort(key=lambda x: x["est_monthly_ad_spend_usd"], reverse=True)

    market_insights = {
        "category_trend": trend,
        "top_advertisers": top_advertisers[:5],
        "recommended_Price_range_usd": {
            "suggested_min": round(max(avg_price * 0.85, template["price_range"][0]), 2),
            "suggested_max": round(min(avg_price * 1.25, template["price_range"][1]), 2),
            "rationale": (
                f"Based on {competitor_count} competing listings across "
                f"{', '.join(platforms)} in {market}. Median price ${median_price:.2f}. "
                f"Suggested range positions you within 1 std deviation of market mean."
            ),
        },
    }

    # ── Assemble response ──────────────────────────────────────────────────
    result = {
        "status": "success",
        "keyword": keyword,
        "market": market,
        "scan_timestamp": scan_ts,
        "competitor_metrics": {
            "total_products_scanned": competitor_count,
            "avg_price_usd": avg_price,
            "price_range": {
                "min": prices[0] if prices else 0,
                "max": prices[-1] if prices else 0,
                "median": median_price,
            },
            "avg_sales_velocity": avg_velocity,
            "top_competitors": top_competitors[:max_competitors],
        },
        "fraud_risk_score": fraud_score,
        "market_insights": market_insights,
        "raw_timestamp": epoch_now,
    }

    logger.info(
        "tiktok_competitive_intel scan complete — keyword=%s market=%s competitors=%d fraud_risk=%s",
        keyword, market, competitor_count, fraud_score["overall_risk"],
    )
    return result
