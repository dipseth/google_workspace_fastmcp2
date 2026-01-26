#!/usr/bin/env python3
"""
Test script for SmartCardBuilderV2

This script tests the v2 card builder by:
1. Building a card with DSL notation
2. Saving the JSON payload to a file
3. Optionally sending via curl

Usage:
    python scripts/test_v2_card_builder.py

    # Then send with curl:
    curl -X POST 'YOUR_WEBHOOK_URL' -H 'Content-Type: application/json' -d @/tmp/v2_card_test.json
"""

import json
import os
import subprocess
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def build_test_card():
    """Build a test card using the v2 builder."""
    from gchat.unified_card_tool import _build_card_with_smart_builder
    from card_framework.v2 import Message

    # Build card with DSL + Content DSL
    card = _build_card_with_smart_builder(
        '''§[δ×4, Ƀ[ᵬ×3]] V2 Test Card

δ 'Line 1: Green' success
δ 'Line 2: Yellow Bold' warning bold
δ 'Line 3: Red' error
δ 'Line 4: Blue' info

ᵬ Button A https://example.com/a
ᵬ Button B https://example.com/b
ᵬ Button C https://example.com/c''',
        {'title': 'V2 Test Card'}
    )

    return card


def strip_internal_fields(obj):
    """Remove internal fields (starting with _) from card structure."""
    if isinstance(obj, dict):
        return {k: strip_internal_fields(v) for k, v in obj.items() if not k.startswith('_')}
    elif isinstance(obj, list):
        return [strip_internal_fields(i) for i in obj]
    return obj


def prepare_webhook_payload(card):
    """Prepare the card for webhook delivery."""
    from card_framework.v2 import Message

    message_obj = Message()
    message_obj.cards_v2.append(strip_internal_fields(card))
    message_body = message_obj.render()

    # Fix field name for webhook (expects camelCase: cardsV2)
    if 'cards_v_2' in message_body:
        message_body['cardsV2'] = message_body.pop('cards_v_2')
    if 'cards_v2' in message_body:
        message_body['cardsV2'] = message_body.pop('cards_v2')

    return message_body


def save_to_file(payload, filepath='/tmp/v2_card_test.json'):
    """Save payload to JSON file."""
    with open(filepath, 'w') as f:
        json.dump(payload, f, indent=2)
    return filepath


def send_with_curl(filepath, webhook_url):
    """Send the card using curl."""
    cmd = [
        'curl', '-X', 'POST', webhook_url,
        '-H', 'Content-Type: application/json',
        '-d', f'@{filepath}'
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result


def main():
    print("=" * 60)
    print("SmartCardBuilderV2 Test")
    print("=" * 60)

    # Build card
    print("\n1. Building card with v2 builder...")
    card = build_test_card()
    print(f"   Card built: {card.get('cardId', 'unknown')}")

    # Prepare payload
    print("\n2. Preparing webhook payload...")
    payload = prepare_webhook_payload(card)
    print(f"   Payload keys: {list(payload.keys())}")

    # Save to file
    print("\n3. Saving to file...")
    filepath = save_to_file(payload)
    print(f"   Saved to: {filepath}")

    # Show card structure
    print("\n4. Card structure:")
    cards = payload.get('cards_v2', [])
    if cards:
        inner_card = cards[0].get('card', {})
        print(f"   Header: {inner_card.get('header', {}).get('title', 'N/A')}")
        sections = inner_card.get('sections', [])
        print(f"   Sections: {len(sections)}")
        for i, section in enumerate(sections):
            widgets = section.get('widgets', [])
            print(f"     Section {i}: {len(widgets)} widgets")

    # Check for webhook URL in environment
    webhook_url = os.environ.get('TEST_CHAT_WEBHOOK')

    if webhook_url:
        print("\n5. Sending via curl...")
        result = send_with_curl(filepath, webhook_url)
        if result.returncode == 0:
            print("   ✅ Card sent successfully!")
            # Parse response for message ID
            try:
                resp = json.loads(result.stdout)
                print(f"   Message: {resp.get('name', 'unknown')}")
            except:
                pass
        else:
            print(f"   ❌ Error: {result.stderr}")
    else:
        print("\n5. To send the card, run:")
        print(f"   curl -X POST 'YOUR_WEBHOOK_URL' -H 'Content-Type: application/json' -d @{filepath}")
        print("\n   Or set TEST_CHAT_WEBHOOK environment variable and re-run.")

    print("\n" + "=" * 60)
    print("Test complete!")
    print("=" * 60)


if __name__ == '__main__':
    main()
