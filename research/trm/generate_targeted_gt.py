"""Generate targeted ground-truth pairs for pool confusion areas.

Focuses on grid_items vs chips, and content_texts vs buttons —
the two biggest confusion zones in the current model.

Produces pairs directly (no webhook needed), with MiniLM embeddings.

Usage:
    cd research/trm/poc
    PYTHONPATH="$(pwd)/.." .venv/bin/python ../generate_targeted_gt.py
"""

from __future__ import annotations

import json
import random
from pathlib import Path

# ── Ground-truth content→pool pairs ──────────────────────────────
# Each entry: (text, correct_pool)
# Organized by confusion boundary

GRID_ITEMS_NOT_CHIPS = [
    # Product names (grid items, not tags)
    "Juvederm Ultra XC", "Juvederm Voluma", "Juvederm Vollure",
    "Botox Cosmetic 50 Units", "Botox Cosmetic 100 Units",
    "Restylane Lyft", "Restylane Silk", "Restylane Defyne",
    "Dysport 300 Units", "Sculptra Aesthetic",
    "Kybella", "Radiesse", "Belotero Balance",
    "Revanesse Versa", "Revanesse Lips+",
    "RHA 2", "RHA 3", "RHA 4", "RHA Redensity",
    # Server/infrastructure names (grid items)
    "web-server-01", "web-server-02", "web-server-03",
    "db-primary", "db-replica-east", "db-replica-west",
    "cache-node-1", "cache-node-2",
    "api-gateway-prod", "api-gateway-staging",
    "load-balancer-01", "worker-queue-main",
    "redis-cluster-01", "kafka-broker-01",
    # File names (grid items)
    "index.html", "styles.css", "app.js", "config.json",
    "README.md", "package.json", "Dockerfile",
    "server.py", "auth_middleware.py", "test_suite.py",
    # People names (grid items)
    "Alice Johnson", "Bob Smith", "Carol Williams",
    "David Brown", "Emily Chen", "Frank Rodriguez",
    # Region/location names (grid items)
    "US West", "US East", "EU Central", "AP Southeast",
    "North America", "Europe", "Asia Pacific",
    # Version strings (grid items)
    "v1.0.0", "v1.1.0", "v2.0.0-beta", "v3.0.0-rc1",
    # Account/merchant names (grid items)
    "Skin Vitality Clinic", "Premier Aesthetics",
    "Radiance Medical Spa", "BeautyFix NYC",
    "Glow Dermatology", "Elite Cosmetic Surgery",
    "LaserAway Downtown", "Ideal Image Westfield",
    # Deal titles (grid items)
    "20 Units of Botox", "1 Syringe of Juvederm",
    "Lip Filler Package", "Full Face Rejuvenation",
    "Micro-needling Session", "Chemical Peel Treatment",
    # Data rows (grid items)
    "$199 per unit", "$450 per syringe", "30-minute session",
    "2-week recovery", "6-month duration", "12-month warranty",
    "4.8 star rating", "127 reviews", "89% satisfaction",
]

CHIPS_NOT_GRID_ITEMS = [
    # Status tags (chips, not grid items)
    "Active", "Inactive", "Pending", "Archived", "Draft",
    "Approved", "Rejected", "In Review", "On Hold", "Expired",
    "Published", "Unpublished", "Scheduled", "Cancelled",
    # Priority tags
    "High Priority", "Medium Priority", "Low Priority",
    "Critical", "Urgent", "Normal", "Deferred",
    # Category tags
    "Cosmetic", "Medical", "Surgical", "Non-Surgical",
    "Injectables", "Laser", "Skincare", "Wellness",
    "Beauty", "Health", "Fitness", "Spa",
    # Compliance tags
    "FDA Approved", "Board Certified Only", "Consultation Required",
    "Medical Director Required", "Licensed Provider",
    "HIPAA Compliant", "Insurance Accepted",
    "Age 18+ Only", "Prescription Required",
    # Technology tags
    "Python", "JavaScript", "Go", "Rust", "TypeScript",
    "React", "Vue", "Angular", "Node.js", "Django",
    # Team/role tags
    "Frontend", "Backend", "DevOps", "QA", "Design",
    "Engineering", "Product", "Marketing", "Sales",
    # Feature tags
    "Beta", "New", "Deprecated", "Experimental",
    "Stable", "LTS", "Preview", "GA",
    # Issue type tags
    "Bug", "Feature", "Enhancement", "Documentation",
    "Security", "Performance", "Refactor", "Tech Debt",
    # Filter tags
    "Today", "This Week", "This Month", "Last 30 Days",
    "Starred", "Unread", "Flagged", "Bookmarked",
    # Deal attribute tags
    "Best Seller", "New Listing", "Limited Time",
    "Staff Pick", "Trending", "Premium", "Value Deal",
    "Auto-Scaling", "High Availability", "Monitoring",
    "SSO Included", "Priority Support", "Custom Branding",
    "API Access", "Unlimited Users",
]

CONTENT_TEXTS_NOT_BUTTONS = [
    # Prose descriptions
    "All systems operational. Last incident: 3 days ago.",
    "Pipeline failed at stage 3: unit tests. See logs for details.",
    "The deployment completed successfully. All health checks passed.",
    "Warning: This action cannot be undone. Please confirm before proceeding.",
    "Maintenance window scheduled for Saturday 2am-4am UTC.",
    "CPU usage has been above 80% for the last 30 minutes.",
    "Memory: 2.1 GB / 8 GB (26% utilized)",
    "Uptime: 14 days 6 hours",
    "Build #1847 — Branch: main — Commit: a3f2b1c",
    "Latency P99: 120ms, Throughput: 5K rps",
    "License: Enterprise, Seats: 50/100, Expires: 2027-01-01",
    "Note: This merchant requires medical director approval before listing.",
    "The injector must hold an active medical license as an MD, DO, NP, PA, or RN.",
    "Groupon's customer service handles all redemption issues.",
    "This balance helps you reach both trial and long-term injection clients.",
    "Increase injector availability and inventory ahead of Q4 and pre-summer peaks.",
    "Plan lighter staffing during January and late summer.",
    "Holiday parties, family photos, end-of-year events drive +25-35% demand.",
    "Total Requests: 1.2M, Error Rate: 0.03%",
    "Created: March 15, Modified: March 20, Owner: platform-team",
    # Labeled values (decorated text content)
    "Status: Online", "Version: 2.4.1", "Last Updated: 2 hours ago",
    "Name: API Gateway", "Type: Service", "Region: us-west-2",
    "Owner: platform-team", "Priority: High", "State: Active",
    "CPU: 45%", "Memory: 2.1GB", "Uptime: 14 days",
    "Email: admin@company.com", "Role: Administrator",
    "Build: #1847", "Branch: main", "Commit: a3f2b1c",
    "Duration: 4m 32s", "Price: $29/month", "Users: Unlimited",
    "Storage: 5 TB", "Current Plan: Standard", "Proposed Plan: Enterprise",
    # Long-form content
    "Capacity Planning: Increase injector availability and inventory ahead of Q4 and pre-summer peaks.",
    "Availability & Lead Time: Expect shorter booking windows during peak periods.",
    "Seasonal Demand: Q4 (Nov-Dec) sees +25-35% demand increase.",
    "This playbook applies only to services explicitly listed as In Scope.",
    "Access to a large, high-intent beauty audience with millions of shoppers.",
]

BUTTONS_NOT_CONTENT_TEXTS = [
    # Action verbs (buttons, not content)
    "Submit", "Deploy", "Approve", "Cancel", "Restart",
    "Send", "Save", "Delete", "Confirm", "Retry",
    "Start", "Stop", "Pause", "Resume", "Reset",
    "Connect", "Disconnect", "Refresh", "Sync",
    "Download", "Upload", "Export", "Import",
    # Compound action labels
    "Deploy Service", "Rollback Version", "View Logs",
    "Check Health", "Run Tests", "Start Pipeline",
    "Stop Pipeline", "View Status", "Submit Form",
    "Save Changes", "Discard Changes", "Download Report",
    "Export CSV", "Export PDF", "Generate Report",
    "Deploy to Staging", "Deploy to Production",
    "Enable Feature", "Disable Feature",
    "Approve Request", "Deny Request",
    "Restart Server", "Scale Out", "Scale In",
    "Contact Merchant", "View Account", "Open Dashboard",
    "View Metrics", "Update Pricing", "Apply Template",
    "Review Objection", "Add to CRM", "Flag for Review",
    "Mark Complete", "Open Ticket", "Escalate", "Reassign",
    "View Deal", "Open Playbook", "Check Compliance",
    "Run Audit", "Sync Data", "Configure",
    "Publish", "Archive", "Restore", "Duplicate", "Compare",
    "Share Link", "Copy URL", "Send Email", "Schedule Call",
    "Start Review", "Submit Feedback",
    "Learn More", "Get Started", "Sign Up", "Log In",
    "View Details", "Read More", "See All",
    "Edit Options", "Manage", "Settings",
    "Go", "Open", "View", "Edit", "Close",
    "Upgrade Now", "Compare Details", "View Table",
    "Practice Script", "Add to Training",
    "Build Logs", "Test Report", "Rollback",
    "Review All", "Mark Complete",
    "View All Archetypes", "Match Merchant",
    "Take Action", "Dismiss", "View Full Section",
]

CAROUSEL_CARDS_ITEMS = [
    # Step/stage names (carousel cards)
    "Step 1: Build", "Step 2: Test", "Step 3: Deploy",
    "Step 1: Configure", "Step 2: Validate", "Step 3: Launch",
    "Overview", "Details", "Metrics", "Logs", "Settings",
    "Configuration Panel", "Deployment Status", "Metric Dashboard",
    "Getting Started", "Advanced Setup", "Troubleshooting",
    # Profile/archetype cards
    "Established Medical Spa", "Solo Practitioner",
    "Plastic Surgery Practice", "Multi-Location Chain",
    "New Market Entrant", "Premium Provider",
    # Plan comparison cards
    "Basic Plan", "Standard Plan", "Professional Plan", "Enterprise Plan",
    "Free Tier", "Growth Tier", "Scale Tier",
]


def build_pairs() -> list[dict]:
    """Build all (text, pool, label) pairs with negatives."""
    rng = random.Random(42)
    all_pools = ["buttons", "content_texts", "grid_items", "chips", "carousel_cards"]
    pairs = []

    def add(items: list[str], correct_pool: str, augment: int = 2):
        for item in items:
            for _ in range(augment):
                # Positive
                pairs.append({
                    "content_text": item,
                    "pool": correct_pool,
                    "label": 1.0,
                    "source": "targeted_gt",
                })
                # Hard negative: random wrong pool
                neg_pool = rng.choice([p for p in all_pools if p != correct_pool])
                pairs.append({
                    "content_text": item,
                    "pool": neg_pool,
                    "label": 0.0,
                    "source": "targeted_gt_neg",
                })

    # Extra weight on confusion boundaries (augment=3)
    add(GRID_ITEMS_NOT_CHIPS, "grid_items", augment=3)
    add(CHIPS_NOT_GRID_ITEMS, "chips", augment=3)
    add(CONTENT_TEXTS_NOT_BUTTONS, "content_texts", augment=2)
    add(BUTTONS_NOT_CONTENT_TEXTS, "buttons", augment=2)
    add(CAROUSEL_CARDS_ITEMS, "carousel_cards", augment=2)

    rng.shuffle(pairs)
    return pairs


def main():
    from h2.slot_assigner import POOL_VOCAB

    pairs = build_pairs()
    print(f"Generated {len(pairs)} targeted pairs")

    # Count by pool
    from collections import Counter
    pool_counts = Counter()
    label_counts = Counter()
    for p in pairs:
        pool_counts[p["pool"]] += 1
        label_counts[p["label"]] += 1
    print(f"By pool: {dict(pool_counts)}")
    print(f"By label: {dict(label_counts)}")

    # Embed
    unique_texts = list({p["content_text"] for p in pairs})
    print(f"\nEmbedding {len(unique_texts)} unique texts...")

    from fastembed import TextEmbedding
    embedder = TextEmbedding("sentence-transformers/all-MiniLM-L6-v2")
    embeddings = list(embedder.embed(unique_texts))
    text_to_emb = {t: e.tolist() for t, e in zip(unique_texts, embeddings)}
    print(f"Embedded {len(text_to_emb)} texts")

    # Convert to slot training format
    slot_pairs = []
    for p in pairs:
        pool = p["pool"]
        if pool not in POOL_VOCAB:
            continue
        emb = text_to_emb.get(p["content_text"])
        if not emb:
            continue
        slot_pairs.append({
            "content_text": p["content_text"],
            "slot_type": pool,
            "slot_type_id": POOL_VOCAB[pool],
            "label": p["label"],
            "source": p["source"],
            "content_embedding": emb,
        })

    print(f"\nSlot training pairs: {len(slot_pairs)}")

    # Load existing and merge
    slot_path = Path("../h2/slot_training_data.json")
    with open(slot_path) as f:
        existing = json.load(f)
    print(f"Existing: {len(existing)}")

    merged = existing + slot_pairs
    random.Random(42).shuffle(merged)
    print(f"Merged: {len(merged)}")

    with open(slot_path, "w") as f:
        json.dump(merged, f)
    print(f"Saved {slot_path}")

    # Also update unified training data
    unified_path = Path("../h2/unified_training_data.json")
    with open(unified_path) as f:
        unified = json.load(f)

    unified["build_pairs"].extend(slot_pairs)
    unified["metadata"]["n_build_pairs"] = len(unified["build_pairs"])
    print(f"Unified build_pairs: {unified['metadata']['n_build_pairs']}")

    with open(unified_path, "w") as f:
        json.dump(unified, f)
    print(f"Saved {unified_path}")


if __name__ == "__main__":
    main()
