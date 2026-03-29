"""Send test cards to Google Chat webhook with known content→component mappings.

Each card has explicit, traceable content in specific component types.
This gives us ground-truth for training data: "this text ended up in this widget."

Usage:
    cd research/trm
    python test_card_webhook.py
"""

import json
import os
import sys
import time
from typing import Any

import requests

WEBHOOK_URL = os.environ.get(
    "TEST_CHAT_WEBHOOK",
    "https://chat.googleapis.com/v1/spaces/AAQAvreVqfs/messages"
    "?key=AIzaSyDdI0hCZtE6vySjMm-WEfRq3CPzqKqqsHI"
    "&token=DeuTMFKt4hXCzGmDhPUo0fT7FWZYFPCTcJC-tk9_6Rg",
)


def send_card(card: dict, fallback_text: str = "Test card") -> dict:
    """Send a card to the webhook and return the response."""
    payload = {
        "cardsV2": [{"cardId": f"test-{int(time.time())}", "card": card}],
        "text": fallback_text,
    }
    resp = requests.post(
        WEBHOOK_URL,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=30,
    )
    print(f"  Status: {resp.status_code}")
    if resp.status_code != 200:
        print(f"  Error: {resp.text[:300]}")
    return {"status": resp.status_code, "ok": resp.status_code == 200}


def build_ground_truth_cards() -> list[dict[str, Any]]:
    """Build cards with known content→component mappings.

    Returns list of {card, mapping} where mapping tracks
    which content text ended up in which widget type.
    """
    cards = []

    # ── Card 1: Mixed content types ──────────────────────────────
    cards.append({
        "name": "mixed_content",
        "card": {
            "header": {"title": "Server Dashboard", "subtitle": "Production Cluster"},
            "sections": [
                {
                    "header": "Status",
                    "widgets": [
                        {"textParagraph": {"text": "All systems operational. Last incident: 3 days ago."}},
                        {"decoratedText": {
                            "topLabel": "CPU Usage",
                            "text": "45%",
                            "bottomLabel": "Below threshold",
                        }},
                        {"decoratedText": {
                            "topLabel": "Memory",
                            "text": "2.1 GB / 8 GB",
                            "bottomLabel": "26% utilized",
                        }},
                        {"decoratedText": {
                            "topLabel": "Uptime",
                            "text": "14 days 6 hours",
                        }},
                    ],
                },
                {
                    "header": "Actions",
                    "widgets": [
                        {"buttonList": {
                            "buttons": [
                                {"text": "Restart Server", "onClick": {"openLink": {"url": "https://example.com/restart"}}},
                                {"text": "View Logs", "onClick": {"openLink": {"url": "https://example.com/logs"}}},
                                {"text": "Check Health", "onClick": {"openLink": {"url": "https://example.com/health"}}},
                            ]
                        }},
                    ],
                },
            ],
        },
        "mapping": {
            "content_texts": [
                "All systems operational. Last incident: 3 days ago.",
                "CPU Usage: 45% - Below threshold",
                "Memory: 2.1 GB / 8 GB - 26% utilized",
                "Uptime: 14 days 6 hours",
            ],
            "buttons": ["Restart Server", "View Logs", "Check Health"],
            "grid_items": [],
            "chips": [],
            "carousel_cards": [],
        },
    })

    # ── Card 2: Grid + Chips ─────────────────────────────────────
    cards.append({
        "name": "grid_and_chips",
        "card": {
            "header": {"title": "Infrastructure Overview"},
            "sections": [
                {
                    "header": "Servers",
                    "widgets": [
                        {"grid": {
                            "title": "Active Servers",
                            "columnCount": 3,
                            "items": [
                                {"title": "web-server-01", "subtitle": "us-west-2"},
                                {"title": "web-server-02", "subtitle": "us-east-1"},
                                {"title": "db-primary", "subtitle": "us-west-2"},
                                {"title": "db-replica", "subtitle": "eu-central-1"},
                                {"title": "cache-node-1", "subtitle": "us-west-2"},
                                {"title": "api-gateway", "subtitle": "global"},
                            ],
                        }},
                    ],
                },
                {
                    "header": "Tags",
                    "widgets": [
                        {"chipList": {
                            "chips": [
                                {"label": "Production", "enabled": True},
                                {"label": "Auto-Scaling", "enabled": True},
                                {"label": "High Availability", "enabled": True},
                                {"label": "Monitoring", "enabled": True},
                                {"label": "Security", "enabled": False},
                            ]
                        }},
                    ],
                },
                {
                    "widgets": [
                        {"buttonList": {
                            "buttons": [
                                {"text": "Deploy Update", "onClick": {"openLink": {"url": "https://example.com/deploy"}}},
                                {"text": "Scale Out", "onClick": {"openLink": {"url": "https://example.com/scale"}}},
                            ]
                        }},
                    ],
                },
            ],
        },
        "mapping": {
            "content_texts": [],
            "buttons": ["Deploy Update", "Scale Out"],
            "grid_items": [
                "web-server-01", "web-server-02", "db-primary",
                "db-replica", "cache-node-1", "api-gateway",
            ],
            "chips": ["Production", "Auto-Scaling", "High Availability", "Monitoring", "Security"],
            "carousel_cards": [],
        },
    })

    # ── Card 3: Carousel ─────────────────────────────────────────
    cards.append({
        "name": "carousel_pipeline",
        "card": {
            "header": {"title": "Deployment Pipeline"},
            "sections": [
                {
                    "widgets": [
                        {"textParagraph": {"text": "Pipeline #1847 — Branch: main — Commit: a3f2b1c"}},
                    ]
                },
                {
                    "widgets": [
                        {"carousel": {
                            "carouselCards": [
                                {
                                    "widgets": [
                                        {"textParagraph": {"text": "<b>Step 1: Build</b>\nCompile & package"}},
                                        {"textParagraph": {"text": "Docker image built in 2m 14s"}},
                                    ],
                                    "footerWidgets": [{"buttonList": {"buttons": [
                                        {"text": "Build Logs", "onClick": {"openLink": {"url": "https://example.com/build"}}},
                                    ]}}],
                                },
                                {
                                    "widgets": [
                                        {"textParagraph": {"text": "<b>Step 2: Test</b>\nUnit + Integration"}},
                                        {"textParagraph": {"text": "342 tests passed, 0 failed"}},
                                    ],
                                    "footerWidgets": [{"buttonList": {"buttons": [
                                        {"text": "Test Report", "onClick": {"openLink": {"url": "https://example.com/tests"}}},
                                    ]}}],
                                },
                                {
                                    "widgets": [
                                        {"textParagraph": {"text": "<b>Step 3: Deploy</b>\nRolling update"}},
                                        {"textParagraph": {"text": "Deployed to 3/3 pods successfully"}},
                                    ],
                                    "footerWidgets": [{"buttonList": {"buttons": [
                                        {"text": "Rollback", "onClick": {"openLink": {"url": "https://example.com/rollback"}}},
                                    ]}}],
                                },
                            ]
                        }},
                    ],
                },
            ],
        },
        "mapping": {
            "content_texts": [
                "Pipeline #1847 — Branch: main — Commit: a3f2b1c",
                "Docker image built in 2m 14s",
                "342 tests passed, 0 failed",
                "Deployed to 3/3 pods successfully",
            ],
            "buttons": ["Build Logs", "Test Report", "Rollback"],
            "grid_items": [],
            "chips": [],
            "carousel_cards": [
                "Step 1: Build — Compile & package",
                "Step 2: Test — Unit + Integration",
                "Step 3: Deploy — Rolling update",
            ],
        },
    })

    # ── Card 4: Columns + DecoratedText heavy ────────────────────
    cards.append({
        "name": "comparison_card",
        "card": {
            "header": {"title": "Plan Comparison", "subtitle": "Current vs Proposed"},
            "sections": [
                {
                    "widgets": [
                        {"columns": {
                            "columnItems": [
                                {"horizontalSizeStyle": "FILL_AVAILABLE_SPACE", "horizontalAlignment": "START",
                                 "verticalAlignment": "CENTER", "widgets": [
                                    {"decoratedText": {"topLabel": "Current Plan", "text": "Standard"}},
                                    {"decoratedText": {"topLabel": "Price", "text": "$29/month"}},
                                    {"decoratedText": {"topLabel": "Users", "text": "Up to 10"}},
                                    {"decoratedText": {"topLabel": "Storage", "text": "100 GB"}},
                                ]},
                                {"horizontalSizeStyle": "FILL_AVAILABLE_SPACE", "horizontalAlignment": "START",
                                 "verticalAlignment": "CENTER", "widgets": [
                                    {"decoratedText": {"topLabel": "Proposed Plan", "text": "Enterprise"}},
                                    {"decoratedText": {"topLabel": "Price", "text": "$99/month"}},
                                    {"decoratedText": {"topLabel": "Users", "text": "Unlimited"}},
                                    {"decoratedText": {"topLabel": "Storage", "text": "5 TB"}},
                                ]},
                            ]
                        }},
                    ],
                },
                {
                    "widgets": [
                        {"chipList": {
                            "chips": [
                                {"label": "SSO Included"},
                                {"label": "Priority Support"},
                                {"label": "Custom Branding"},
                                {"label": "API Access"},
                            ]
                        }},
                        {"buttonList": {
                            "buttons": [
                                {"text": "Upgrade Now", "onClick": {"openLink": {"url": "https://example.com/upgrade"}}},
                                {"text": "Compare Details", "onClick": {"openLink": {"url": "https://example.com/compare"}}},
                            ]
                        }},
                    ],
                },
            ],
        },
        "mapping": {
            "content_texts": [
                "Current Plan: Standard",
                "Price: $29/month",
                "Users: Up to 10",
                "Storage: 100 GB",
                "Proposed Plan: Enterprise",
                "Price: $99/month",
                "Users: Unlimited",
                "Storage: 5 TB",
            ],
            "buttons": ["Upgrade Now", "Compare Details"],
            "grid_items": [],
            "chips": ["SSO Included", "Priority Support", "Custom Branding", "API Access"],
            "carousel_cards": [],
        },
    })

    # ── Card 5: Simple notification (minimal) ────────────────────
    cards.append({
        "name": "simple_notification",
        "card": {
            "header": {"title": "Build Failed", "subtitle": "CI/CD Alert"},
            "sections": [
                {
                    "widgets": [
                        {"textParagraph": {"text": "<b>Pipeline failed at stage 3: unit tests.</b>\nSee logs for details. 2 tests failed in auth_middleware_test.go"}},
                        {"decoratedText": {
                            "topLabel": "Build",
                            "text": "#1847",
                            "bottomLabel": "Branch: feature/new-auth",
                        }},
                        {"decoratedText": {
                            "topLabel": "Duration",
                            "text": "4m 32s",
                        }},
                        {"divider": {}},
                        {"buttonList": {
                            "buttons": [
                                {"text": "View Logs", "onClick": {"openLink": {"url": "https://example.com/logs"}}},
                                {"text": "Retry Build", "onClick": {"openLink": {"url": "https://example.com/retry"}}},
                                {"text": "Ignore", "onClick": {"openLink": {"url": "https://example.com/ignore"}}},
                            ]
                        }},
                    ],
                },
            ],
        },
        "mapping": {
            "content_texts": [
                "Pipeline failed at stage 3: unit tests. See logs for details. 2 tests failed in auth_middleware_test.go",
                "Build: #1847 - Branch: feature/new-auth",
                "Duration: 4m 32s",
            ],
            "buttons": ["View Logs", "Retry Build", "Ignore"],
            "grid_items": [],
            "chips": [],
            "carousel_cards": [],
        },
    })

    return cards


def main():
    print(f"Sending {5} test cards to webhook...\n")

    cards = build_ground_truth_cards()
    results = []

    for i, entry in enumerate(cards):
        name = entry["name"]
        card = entry["card"]
        mapping = entry["mapping"]

        print(f"[{i+1}/{len(cards)}] Sending: {name}")
        result = send_card(card, fallback_text=f"Test card: {name}")
        result["name"] = name
        result["mapping"] = mapping
        results.append(result)

        # Rate limit - don't spam the webhook
        if i < len(cards) - 1:
            time.sleep(1.5)

    # Summary
    ok = sum(1 for r in results if r["ok"])
    print(f"\n{'='*60}")
    print(f"Sent {ok}/{len(results)} cards successfully")

    # Save ground-truth mappings
    ground_truth = []
    for entry in cards:
        gt = {"card_name": entry["name"], "mapping": entry["mapping"]}
        # Flatten to training pairs
        pairs = []
        for pool, texts in entry["mapping"].items():
            for text in texts:
                pairs.append({"content_text": text, "pool": pool, "label": 1.0})
                # Could add negatives here too
        gt["pairs"] = pairs
        gt["total_content_items"] = sum(len(v) for v in entry["mapping"].values())
        ground_truth.append(gt)

    total_pairs = sum(len(g["pairs"]) for g in ground_truth)
    print(f"Ground-truth: {total_pairs} content→pool pairs across {len(ground_truth)} cards")
    print()

    # Print mapping summary
    for gt in ground_truth:
        print(f"  {gt['card_name']}: {gt['total_content_items']} items")
        for pool in ["content_texts", "buttons", "grid_items", "chips", "carousel_cards"]:
            items = gt["mapping"][pool]
            if items:
                print(f"    {pool}: {len(items)} items")
                for t in items[:3]:
                    print(f"      - \"{t[:60]}\"")
                if len(items) > 3:
                    print(f"      ... +{len(items)-3} more")

    # Save to file for potential training use
    out_path = "h2/ground_truth_card_mappings.json"
    with open(out_path, "w") as f:
        json.dump(ground_truth, f, indent=2)
    print(f"\nSaved ground-truth to {out_path}")


if __name__ == "__main__":
    main()
