"""Generate and send highly varied Google Chat cards from Qdrant collection content.

Pulls real content from dev_playbook_cosmetic_injections, creates 70+ card variations
with randomized layouts, widget combos, styling, colors, icons, button types, grid
column counts, and section counts. Saves ground-truth content→pool mappings.

Usage:
    cd research/trm
    export QDRANT_URL="https://637e30ec-4301-45df-9824-d3b74f525818.us-east4-0.gcp.cloud.qdrant.io"
    export QDRANT_KEY="..."
    python test_collection_cards.py [--count 70] [--send] [--save-only]
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import time
from typing import Any

import requests
from qdrant_client import QdrantClient

# ── Config ────────────────────────────────────────────────────────
COLLECTION = "dev_playbook_cosmetic_injections"
WEBHOOK_URL = os.environ.get(
    "TEST_CHAT_WEBHOOK",
    "https://chat.googleapis.com/v1/spaces/AAQAvreVqfs/messages"
    "?key=AIzaSyDdI0hCZtE6vySjMm-WEfRq3CPzqKqqsHI"
    "&token=DeuTMFKt4hXCzGmDhPUo0fT7FWZYFPCTcJC-tk9_6Rg",
)

# ── Styling palettes ─────────────────────────────────────────────

SEMANTIC_COLORS = {
    "success": "#34a853",
    "error": "#ea4335",
    "warning": "#fbbc05",
    "info": "#4285f4",
    "muted": "#9aa0a6",
    "primary": "#1a73e8",
    "accent": "#8430ce",
    "dark": "#3c4043",
}

COLOR_SCHEMES = {
    "google": ["#4285f4", "#34a853", "#fbbc05", "#ea4335"],
    "warm": ["#ea4335", "#fbbc05", "#ff6d01"],
    "cool": ["#4285f4", "#8430ce", "#00acc1"],
    "neutral": ["#5f6368", "#9aa0a6", "#3c4043"],
    "vibrant": ["#ea4335", "#4285f4", "#34a853", "#fbbc05", "#8430ce"],
    "mono_blue": ["#1a73e8", "#4285f4", "#8ab4f8"],
    "mono_green": ["#137333", "#34a853", "#81c995"],
    "mono_red": ["#a50e0e", "#ea4335", "#f28b82"],
}

ICONS = [
    "check_circle",
    "info",
    "warning",
    "error",
    "star",
    "favorite",
    "bookmark",
    "schedule",
    "trending_up",
    "trending_down",
    "analytics",
    "attach_money",
    "medical_services",
    "health_and_safety",
    "science",
    "inventory_2",
    "category",
    "local_offer",
    "storefront",
    "groups",
    "person",
    "verified",
    "thumb_up",
    "thumb_down",
    "flag",
    "bolt",
    "rocket_launch",
    "target",
    "eco",
    "spa",
    "face_retouching_natural",
    "dermatology",
    "clinical_notes",
    "vaccines",
    "medication",
    "assignment",
    "checklist",
    "task_alt",
    "rule",
    "gavel",
    "description",
    "article",
    "summarize",
    "format_list_bulleted",
    "view_list",
    "grid_view",
    "dashboard",
    "bar_chart",
    "pie_chart",
    "show_chart",
    "table_chart",
    "leaderboard",
]

BUTTON_STYLES = ["FILLED", "OUTLINED", "FILLED_TONAL", "BORDERLESS"]

# Real-ish URLs for training signal
URL_TEMPLATES = [
    "https://groupon.com/merchant/{slug}",
    "https://docs.google.com/document/d/{doc_id}/edit",
    "https://app.groupon.com/deals/{deal_id}/options",
    "https://admin.groupon.com/compliance/{section}",
    "https://dashboard.groupon.com/analytics/{metric}",
    "https://training.groupon.com/playbook/{topic}",
    "https://salesforce.groupon.com/accounts/{account}",
    "https://calendar.google.com/event/{event_id}",
    "https://meet.google.com/{meeting_code}",
    "https://drive.google.com/file/d/{file_id}/view",
    "https://sheets.google.com/spreadsheets/d/{sheet_id}",
    "https://slides.google.com/presentation/d/{pres_id}",
    "https://chat.google.com/room/{space_id}",
    "https://jira.groupon.com/browse/{ticket}",
    "https://grafana.groupon.com/d/{dashboard_id}",
]

BUTTON_LABELS = [
    # Action verbs
    "View Details",
    "Open Report",
    "Download CSV",
    "Export PDF",
    "Share Link",
    "Copy URL",
    "Send Email",
    "Schedule Call",
    "Start Review",
    "Submit Feedback",
    "Approve Deal",
    "Reject",
    "Edit Options",
    "Configure",
    "Deploy",
    "Publish",
    "Archive",
    "Restore",
    "Duplicate",
    "Compare",
    # Domain-specific
    "View Deal",
    "Open Playbook",
    "Check Compliance",
    "Run Audit",
    "Contact Merchant",
    "View Account",
    "Open Dashboard",
    "View Metrics",
    "Generate Report",
    "Sync Data",
    "Update Pricing",
    "Apply Template",
    "Review Objection",
    "Add to CRM",
    "Flag for Review",
    "Mark Complete",
    "View Pipeline",
    "Open Ticket",
    "Escalate",
    "Reassign",
]

HEADER_SUBTITLES = [
    "Cosmetic Injections Playbook",
    "Sales Enablement",
    "Category: High-End Beauty",
    "Merchant Operations",
    "Deal Review",
    "Compliance Check",
    "Performance Metrics",
    "Training Material",
    "Onboarding Guide",
    "Best Practices",
    "Quick Reference",
    "Weekly Update",
    "Action Required",
    "For Review",
    "Draft",
]


# ── Content extraction helpers ────────────────────────────────────


def clean_md(text: str, max_len: int = 200) -> str:
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"#{1,6}\s*", "", text)
    text = re.sub(r"\|[^|]*\|", " ", text)
    text = re.sub(r"[-*]\s+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_len]


def extract_list_items(content: str, max_items: int = 8) -> list[str]:
    items = []
    for line in content.split("\n"):
        line = line.strip()
        if re.match(r"^[\*\-\d+\.]\s+", line):
            item = re.sub(r"^[\*\-\d+\.]\s+", "", line)
            item = re.sub(r"\*\*([^*]+)\*\*", r"\1", item).strip()
            if 3 < len(item) < 120:
                items.append(item)
    return items[:max_items]


def extract_table_rows(content: str, max_rows: int = 8) -> list[dict]:
    lines = [line.strip() for line in content.split("\n") if "|" in line]
    if len(lines) < 3:
        return []
    headers = [h.strip() for h in lines[0].split("|") if h.strip() and h.strip() != "-"]
    rows = []
    for line in lines[2 : 2 + max_rows]:
        cells = [c.strip() for c in line.split("|") if c.strip()]
        if len(cells) >= 2:
            row = {}
            for i, cell in enumerate(cells[: len(headers)]):
                cell = re.sub(r"\*\*([^*]+)\*\*", r"\1", cell)
                row[headers[i] if i < len(headers) else f"col{i}"] = cell
            rows.append(row)
    return rows


def extract_checklist_items(content: str, max_items: int = 10) -> list[str]:
    items = []
    for line in content.split("\n"):
        line = line.strip()
        if re.match(r"^[\*\-]\s+", line):
            item = re.sub(r"^[\*\-]\s+", "", line)
            item = re.sub(r"\*\*([^*]+)\*\*", r"\1", item).strip()
            if 3 < len(item) < 60:
                items.append(item[:50])
    return items[:max_items]


# ── Random widget factories ──────────────────────────────────────


def rand_url(rng: random.Random) -> str:
    tpl = rng.choice(URL_TEMPLATES)
    slug = "".join(rng.choices("abcdefghijklmnop0123456789", k=8))
    return tpl.format(
        slug=slug,
        doc_id=slug,
        deal_id=slug,
        section=slug,
        metric=slug,
        topic=slug,
        account=slug,
        event_id=slug,
        meeting_code=f"{slug[:3]}-{slug[3:7]}-{slug[7:]}",
        file_id=slug,
        sheet_id=slug,
        pres_id=slug,
        space_id=slug,
        ticket=f"DEAL-{rng.randint(100, 9999)}",
        dashboard_id=slug,
    )


def rand_color(rng: random.Random, scheme: str | None = None) -> str:
    if scheme and scheme in COLOR_SCHEMES:
        return rng.choice(COLOR_SCHEMES[scheme])
    return rng.choice(list(SEMANTIC_COLORS.values()))


def rand_icon(rng: random.Random) -> dict:
    return {"materialIcon": {"name": rng.choice(ICONS)}}


def color_text(text: str, color: str) -> str:
    return f'<font color="{color}">{text}</font>'


def bold(text: str) -> str:
    return f"<b>{text}</b>"


def make_buttons(
    rng: random.Random, count: int, scheme: str | None = None
) -> tuple[list[dict], list[str]]:
    """Create random buttons. Returns (widget_buttons, label_list)."""
    labels = rng.sample(BUTTON_LABELS, min(count, len(BUTTON_LABELS)))
    buttons = []
    for label in labels:
        btn: dict[str, Any] = {
            "text": label,
            "onClick": {"openLink": {"url": rand_url(rng)}},
        }
        # Randomly add button style
        if rng.random() < 0.6:
            style = rng.choice(BUTTON_STYLES)
            btn["type"] = style
        # Randomly add color
        if rng.random() < 0.3:
            c = rand_color(rng, scheme)
            btn["color"] = {
                "red": int(c[1:3], 16) / 255,
                "green": int(c[3:5], 16) / 255,
                "blue": int(c[5:7], 16) / 255,
                "alpha": 1,
            }
        buttons.append(btn)
    return buttons, labels


def make_decorated_text(
    rng: random.Random, text: str, label: str = "", scheme: str | None = None
) -> dict:
    """Build a decoratedText widget with random styling."""
    dt: dict[str, Any] = {"text": text}

    if label:
        dt["topLabel"] = label

    # Random bottom label
    if rng.random() < 0.3:
        bottom_options = [
            "Updated today",
            "Source: Playbook",
            "Verified",
            "Last reviewed: Mar 2026",
            "Auto-generated",
            "Draft",
        ]
        dt["bottomLabel"] = rng.choice(bottom_options)

    # Random icon
    if rng.random() < 0.5:
        dt["startIcon"] = rand_icon(rng)

    # Random inline button
    if rng.random() < 0.2:
        dt["button"] = {
            "text": rng.choice(["Open", "View", "Edit", "Go"]),
            "onClick": {"openLink": {"url": rand_url(rng)}},
        }

    # Random switch control (mutually exclusive with button)
    elif rng.random() < 0.15:
        dt.pop("button", None)
        dt["switchControl"] = {
            "name": f"toggle_{rng.randint(1, 999)}",
            "selected": rng.choice([True, False]),
            "controlType": rng.choice(["SWITCH", "CHECK_BOX"]),
        }

    # Apply color to text
    if rng.random() < 0.4:
        c = rand_color(rng, scheme)
        dt["text"] = color_text(text, c)

    # Wrap text
    if rng.random() < 0.3:
        dt["wrapText"] = True

    return {"decoratedText": dt}


def make_text_paragraph(
    rng: random.Random, text: str, scheme: str | None = None
) -> dict:
    """Build a textParagraph with random styling."""
    # Randomly bold parts
    if rng.random() < 0.3:
        words = text.split()
        if len(words) > 3:
            idx = rng.randint(0, min(2, len(words) - 1))
            words[idx] = bold(words[idx])
            text = " ".join(words)

    # Randomly color the whole thing
    if rng.random() < 0.25:
        text = color_text(text, rand_color(rng, scheme))

    return {"textParagraph": {"text": text}}


def make_grid(
    rng: random.Random, items: list[str], section_title: str = ""
) -> tuple[dict, list[str]]:
    """Build a grid widget. Returns (widget, item_titles)."""
    col_count = rng.choice([1, 2, 3, 2, 2, 3])  # weighted toward 2-3
    grid_items = []
    for item_text in items:
        gi: dict[str, Any] = {"title": item_text[:50]}
        # Random subtitle
        if rng.random() < 0.5 and section_title:
            gi["subtitle"] = section_title[:30]
        elif rng.random() < 0.3:
            gi["subtitle"] = rng.choice(
                [
                    "Active",
                    "Pending",
                    "Complete",
                    "New",
                    "In Review",
                    "Approved",
                    "High Priority",
                ]
            )
        grid_items.append(gi)

    widget = {
        "grid": {
            "columnCount": col_count,
            "items": grid_items,
        }
    }
    # Random grid title
    if rng.random() < 0.6:
        widget["grid"]["title"] = (
            section_title[:40]
            if section_title
            else rng.choice(
                [
                    "Items",
                    "Results",
                    "Data Points",
                    "Overview",
                    "Details",
                ]
            )
        )

    return widget, [gi["title"] for gi in grid_items]


def make_chips(rng: random.Random, labels: list[str]) -> tuple[dict, list[str]]:
    """Build a chipList widget."""
    chips = []
    for label in labels:
        chip: dict[str, Any] = {"label": label}
        # Chips support icon but via "icon" not "startIcon"
        if rng.random() < 0.3:
            chip["icon"] = rand_icon(rng)
        if rng.random() < 0.2:
            chip["enabled"] = rng.choice([True, False])
        chips.append(chip)
    return {"chipList": {"chips": chips}}, labels


def make_columns(
    rng: random.Random, left_widgets: list[dict], right_widgets: list[dict]
) -> dict:
    """Build a columns widget."""
    return {
        "columns": {
            "columnItems": [
                {
                    "horizontalSizeStyle": "FILL_AVAILABLE_SPACE",
                    "horizontalAlignment": "START",
                    "verticalAlignment": "CENTER",
                    "widgets": left_widgets,
                },
                {
                    "horizontalSizeStyle": "FILL_AVAILABLE_SPACE",
                    "horizontalAlignment": "START",
                    "verticalAlignment": "CENTER",
                    "widgets": right_widgets,
                },
            ]
        }
    }


def make_carousel(
    rng: random.Random, card_contents: list[dict], scheme: str | None = None
) -> tuple[dict, list[str], list[str], list[str]]:
    """Build a carousel. Returns (widget, carousel_names, content_texts, buttons)."""
    carousel_cards = []
    carousel_names = []
    all_texts = []
    all_buttons = []

    for cc in card_contents:
        title = cc.get("title", "")
        text = cc.get("text", "")
        widgets = []

        if title:
            widgets.append({"textParagraph": {"text": bold(title)}})
            carousel_names.append(title)
        if text:
            widgets.append({"textParagraph": {"text": text}})
            all_texts.append(text)

        card_entry: dict[str, Any] = {"widgets": widgets}

        # Random footer button
        if rng.random() < 0.7:
            btn_label = rng.choice(["Open", "View", "Details", "Go", "Learn More"])
            card_entry["footerWidgets"] = [
                {
                    "buttonList": {
                        "buttons": [
                            {
                                "text": btn_label,
                                "onClick": {"openLink": {"url": rand_url(rng)}},
                            }
                        ]
                    }
                }
            ]
            all_buttons.append(btn_label)

        carousel_cards.append(card_entry)

    return (
        {"carousel": {"carouselCards": carousel_cards}},
        carousel_names,
        all_texts,
        all_buttons,
    )


# ── Card layout templates ────────────────────────────────────────

LAYOUT_TEMPLATES = [
    # (name, widget_slots) — each slot is a pool type or "divider"
    ("text_only", ["content_texts"]),
    ("text_buttons", ["content_texts", "buttons"]),
    ("text_chips_buttons", ["content_texts", "chips", "buttons"]),
    ("grid_only", ["grid_items"]),
    ("grid_buttons", ["grid_items", "buttons"]),
    ("grid_text_buttons", ["grid_items", "content_texts", "buttons"]),
    ("chips_only", ["chips"]),
    ("chips_text", ["chips", "content_texts"]),
    ("chips_buttons", ["chips", "buttons"]),
    ("text_grid_chips_buttons", ["content_texts", "grid_items", "chips", "buttons"]),
    ("columns_buttons", ["content_texts", "buttons"]),  # uses columns layout
    ("carousel_buttons", ["carousel_cards", "buttons"]),
    ("carousel_text", ["carousel_cards", "content_texts"]),
    (
        "text_divider_text_buttons",
        ["content_texts", "divider", "content_texts", "buttons"],
    ),
    ("grid_chips", ["grid_items", "chips"]),
    ("grid_text_chips_buttons", ["grid_items", "content_texts", "chips", "buttons"]),
    ("text_text_buttons", ["content_texts", "content_texts", "buttons"]),
    ("heavy_text", ["content_texts", "content_texts", "content_texts"]),
    ("heavy_grid", ["grid_items", "grid_items"]),
    ("heavy_buttons", ["content_texts", "buttons", "buttons"]),
    ("all_pools", ["content_texts", "grid_items", "chips", "buttons"]),
    ("minimal", ["buttons"]),
    ("carousel_chips_buttons", ["carousel_cards", "chips", "buttons"]),
]


# ── Main card generator ──────────────────────────────────────────


class CardGenerator:
    def __init__(self, points_by_type: dict[str, list], rng: random.Random):
        self.by_type = points_by_type
        self.rng = rng
        self._content_idx = {k: 0 for k in points_by_type}

    def _next_point(self, content_type: str) -> dict:
        pts = self.by_type.get(content_type, [])
        if not pts:
            # Fallback to prose
            pts = self.by_type.get(
                "prose",
                self.by_type.get(
                    "list", [{"content": "No content", "section_title": ""}]
                ),
            )
        idx = self._content_idx.get(content_type, 0) % len(pts)
        self._content_idx[content_type] = idx + 1
        return pts[idx]

    def _get_content_texts(self, count: int) -> list[tuple[str, str]]:
        """Get (text, label) pairs from prose/objection content."""
        results = []
        types = ["prose", "objection_response"]
        for _ in range(count):
            ct = self.rng.choice(types)
            pt = self._next_point(ct)
            text = clean_md(pt["content"], max_len=self.rng.randint(60, 250))
            label = pt.get("section_title", "")[:40]
            if text and len(text) > 10:
                results.append((text, label))
        return results or [("Content unavailable", "")]

    def _get_grid_items(self, count: int) -> tuple[list[str], str]:
        """Get grid item texts from list/table content."""
        ct = self.rng.choice(["list", "table", "list"])
        pt = self._next_point(ct)
        section = pt.get("section_title", "Data")

        if ct == "table":
            rows = extract_table_rows(pt["content"], max_rows=count)
            items = []
            for row in rows:
                vals = list(row.values())
                items.append(vals[0][:50] if vals else "—")
        else:
            items = extract_list_items(pt["content"], max_items=count)

        # Pad if needed
        while len(items) < 2:
            items.append(f"Item {len(items) + 1}")

        return items[:count], section

    def _get_chip_labels(self, count: int) -> list[str]:
        """Get chip labels from compliance content."""
        all_items = []
        for _ in range(3):
            pt = self._next_point("compliance_checklist")
            all_items.extend(extract_checklist_items(pt["content"], max_items=count))

        seen = set()
        unique = []
        for item in all_items:
            if item not in seen:
                seen.add(item)
                unique.append(item)

        # Pad with generic if needed
        generic = [
            "Verified",
            "Approved",
            "Pending",
            "Required",
            "Optional",
            "Critical",
            "Active",
            "Flagged",
            "Reviewed",
            "Complete",
        ]
        while len(unique) < count:
            unique.append(self.rng.choice(generic))

        return unique[:count]

    def _get_carousel_items(self, count: int) -> list[dict]:
        """Get carousel card content from archetype/prose content."""
        items = []
        for _ in range(count):
            pt = self._next_point(self.rng.choice(["merchant_archetype", "prose"]))
            title = pt.get("section_title", "")[:50] or f"Card {len(items) + 1}"
            text = clean_md(pt["content"], max_len=self.rng.randint(80, 160))
            items.append({"title": title, "text": text})
        return items

    def generate_card(self, card_idx: int) -> dict[str, Any]:
        """Generate one randomized card with ground-truth mapping."""
        rng = self.rng
        scheme = rng.choice(list(COLOR_SCHEMES.keys()))
        layout_name, slots = rng.choice(LAYOUT_TEMPLATES)

        # Decide section count: 1-4
        n_sections = rng.choice([1, 1, 2, 2, 2, 3, 3, 4])

        # Track ground truth
        mapping: dict[str, list[str]] = {
            "content_texts": [],
            "buttons": [],
            "grid_items": [],
            "chips": [],
            "carousel_cards": [],
        }
        meta = {"layout": layout_name, "scheme": scheme, "n_sections": n_sections}

        all_widgets: list[dict] = []

        # Process each slot in the layout
        for slot in slots:
            if slot == "divider":
                all_widgets.append({"divider": {}})
                continue

            if slot == "content_texts":
                count = rng.randint(1, 4)
                pairs = self._get_content_texts(count)

                # Randomly choose: textParagraph, decoratedText, columns, or mix
                widget_style = rng.choice(
                    ["paragraph", "decorated", "mixed", "columns"]
                )

                if widget_style == "columns" and len(pairs) >= 2:
                    left = []
                    right = []
                    for i, (text, label) in enumerate(pairs):
                        w = make_decorated_text(rng, text, label, scheme)
                        if i % 2 == 0:
                            left.append(w)
                        else:
                            right.append(w)
                        mapping["content_texts"].append(
                            f"{label}: {text}" if label else text
                        )
                    all_widgets.append(make_columns(rng, left, right))

                else:
                    for text, label in pairs:
                        if widget_style == "paragraph" or (
                            widget_style == "mixed" and rng.random() < 0.5
                        ):
                            all_widgets.append(make_text_paragraph(rng, text, scheme))
                        else:
                            all_widgets.append(
                                make_decorated_text(rng, text, label, scheme)
                            )
                        mapping["content_texts"].append(
                            f"{label}: {text}" if label else text
                        )

            elif slot == "grid_items":
                count = rng.choice([2, 3, 4, 5, 6, 4, 3])
                items, section = self._get_grid_items(count)
                grid_widget, grid_titles = make_grid(rng, items, section)
                all_widgets.append(grid_widget)
                mapping["grid_items"].extend(grid_titles)

            elif slot == "chips":
                count = rng.choice([3, 4, 5, 6, 7, 8])
                labels = self._get_chip_labels(count)
                chip_widget, chip_labels = make_chips(rng, labels)
                all_widgets.append(chip_widget)
                mapping["chips"].extend(chip_labels)

            elif slot == "buttons":
                count = rng.choice([1, 2, 3, 2, 1, 4])
                btn_widgets, btn_labels = make_buttons(rng, count, scheme)
                all_widgets.append({"buttonList": {"buttons": btn_widgets}})
                mapping["buttons"].extend(btn_labels)

            elif slot == "carousel_cards":
                count = rng.choice([2, 3, 3, 4])
                items = self._get_carousel_items(count)
                carousel_w, c_names, c_texts, c_btns = make_carousel(rng, items, scheme)
                all_widgets.append(carousel_w)
                mapping["carousel_cards"].extend(c_names)
                mapping["content_texts"].extend(c_texts)
                mapping["buttons"].extend(c_btns)

        # Distribute widgets across sections
        sections = []
        if n_sections == 1 or len(all_widgets) <= 2:
            section: dict[str, Any] = {"widgets": all_widgets}
            if rng.random() < 0.5:
                section["header"] = rng.choice(
                    [
                        "Overview",
                        "Details",
                        "Actions",
                        "Summary",
                        "Data",
                        "Configuration",
                        "Status",
                        "Results",
                        "Items",
                    ]
                )
            sections.append(section)
        else:
            chunk_size = max(1, len(all_widgets) // n_sections)
            for i in range(0, len(all_widgets), chunk_size):
                chunk = all_widgets[i : i + chunk_size]
                if not chunk:
                    continue
                sec: dict[str, Any] = {"widgets": chunk}
                if rng.random() < 0.6:
                    sec["header"] = rng.choice(
                        [
                            "Overview",
                            "Details",
                            "Actions",
                            "Summary",
                            "Info",
                            "Metrics",
                            "Requirements",
                            "Options",
                            "Related",
                            "Key Points",
                            "Recommendations",
                            "Next Steps",
                        ]
                    )
                sections.append(sec)

        # Build header
        header: dict[str, Any] = {
            "title": f"Card #{card_idx + 1}: {layout_name.replace('_', ' ').title()}"[
                :60
            ]
        }
        if rng.random() < 0.7:
            header["subtitle"] = rng.choice(HEADER_SUBTITLES)
        if rng.random() < 0.3:
            header["imageUrl"] = rng.choice(
                [
                    "https://fonts.gstatic.com/s/i/short-term/release/googlesymbols/analytics/default/48px.svg",
                    "https://fonts.gstatic.com/s/i/short-term/release/googlesymbols/dashboard/default/48px.svg",
                    "https://fonts.gstatic.com/s/i/short-term/release/googlesymbols/storefront/default/48px.svg",
                    "https://fonts.gstatic.com/s/i/short-term/release/googlesymbols/description/default/48px.svg",
                ]
            )
            header["imageType"] = rng.choice(["CIRCLE", "SQUARE"])

        card = {"header": header, "sections": sections}

        return {
            "card": card,
            "mapping": mapping,
            "meta": meta,
            "name": f"{card_idx:03d}_{layout_name}",
        }


# ── Qdrant fetch ─────────────────────────────────────────────────


def fetch_collection_points() -> list[dict]:
    url = os.environ.get("QDRANT_URL")
    key = os.environ.get("QDRANT_KEY") or os.environ.get("QDRANT_API_KEY")
    client = QdrantClient(url=url, api_key=key, check_compatibility=False)

    all_points = []
    offset = None
    while True:
        pts, nxt = client.scroll(
            COLLECTION,
            limit=100,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        all_points.extend(pts)
        if nxt is None:
            break
        offset = nxt

    print(f"Fetched {len(all_points)} points from {COLLECTION}")
    return [
        {
            "content": p.payload.get("content", ""),
            "content_type": p.payload.get("content_type", ""),
            "section_title": p.payload.get("section_title", ""),
            "hierarchy_path": p.payload.get("hierarchy_path", ""),
        }
        for p in all_points
    ]


def send_card(card: dict, fallback_text: str = "Collection card") -> dict:
    payload = {
        "cardsV2": [{"cardId": f"gen-{int(time.time() * 1000)}", "card": card}],
        "text": fallback_text,
    }
    resp = requests.post(
        WEBHOOK_URL,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=30,
    )
    return {
        "status": resp.status_code,
        "ok": resp.status_code == 200,
        "error": resp.text[:200] if resp.status_code != 200 else "",
    }


# ── Main ─────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Generate varied cards from collection"
    )
    parser.add_argument(
        "--count", type=int, default=70, help="Number of cards to generate"
    )
    parser.add_argument(
        "--send",
        action="store_true",
        help="Actually send to webhook (default: just generate)",
    )
    parser.add_argument(
        "--save-only", action="store_true", help="Only save ground truth, don't send"
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--delay", type=float, default=1.0, help="Delay between sends (seconds)"
    )
    args = parser.parse_args()

    rng = random.Random(args.seed)
    random.seed(args.seed)

    # Fetch
    all_points = fetch_collection_points()
    by_type: dict[str, list] = {}
    for pt in all_points:
        ct = pt.get("content_type", "unknown")
        by_type.setdefault(ct, []).append(pt)

    print(f"Content types: {', '.join(f'{k}({len(v)})' for k, v in by_type.items())}")

    # Shuffle each type for variety
    for pts in by_type.values():
        rng.shuffle(pts)

    # Generate cards
    gen = CardGenerator(by_type, rng)
    cards = []
    for i in range(args.count):
        cards.append(gen.generate_card(i))

    print(f"\nGenerated {len(cards)} cards")

    # Stats
    layout_counts: dict[str, int] = {}
    pool_totals: dict[str, int] = {}
    for entry in cards:
        layout = entry["meta"]["layout"]
        layout_counts[layout] = layout_counts.get(layout, 0) + 1
        for pool, items in entry["mapping"].items():
            pool_totals[pool] = pool_totals.get(pool, 0) + len(items)

    print(f"\nLayout distribution:")
    for layout, cnt in sorted(layout_counts.items(), key=lambda x: -x[1]):
        print(f"  {layout}: {cnt}")
    print(f"\nPool totals:")
    for pool, cnt in sorted(pool_totals.items(), key=lambda x: -x[1]):
        print(f"  {pool}: {cnt}")

    # Send if requested
    if args.send and not args.save_only:
        print(f"\nSending {len(cards)} cards to webhook...")
        ok = 0
        fail = 0
        for i, entry in enumerate(cards):
            result = send_card(
                entry["card"], f"Card {i + 1}/{len(cards)}: {entry['name']}"
            )
            if result["ok"]:
                ok += 1
                print(f"  [{i + 1}/{len(cards)}] {entry['name']} ✓")
            else:
                fail += 1
                print(
                    f"  [{i + 1}/{len(cards)}] {entry['name']} ✗ {result['error'][:100]}"
                )
            if i < len(cards) - 1:
                time.sleep(args.delay)
        print(f"\nSent: {ok} ok, {fail} failed")

    # Build ground truth
    ground_truth = []
    for entry in cards:
        gt = {
            "card_name": entry["name"],
            "mapping": entry["mapping"],
            "meta": entry["meta"],
            "source_collection": COLLECTION,
        }
        pairs = []
        for pool, texts in entry["mapping"].items():
            for text in texts:
                pairs.append(
                    {
                        "content_text": text,
                        "pool": pool,
                        "label": 1.0,
                        "source": f"card_gen_{COLLECTION}",
                        "layout": entry["meta"]["layout"],
                    }
                )
        gt["pairs"] = pairs
        gt["total_content_items"] = len(pairs)
        ground_truth.append(gt)

    total_pairs = sum(len(g["pairs"]) for g in ground_truth)
    print(
        f"\nGround-truth: {total_pairs} content→pool pairs across {len(ground_truth)} cards"
    )

    out_path = "h2/ground_truth_collection_cards.json"
    with open(out_path, "w") as f:
        json.dump(ground_truth, f, indent=2)
    print(f"Saved to {out_path}")

    # Also save the raw card JSONs for inspection
    raw_path = "h2/generated_cards_raw.json"
    raw = [{"name": e["name"], "card": e["card"], "meta": e["meta"]} for e in cards]
    with open(raw_path, "w") as f:
        json.dump(raw, f, indent=2)
    print(f"Saved raw cards to {raw_path}")


if __name__ == "__main__":
    main()
