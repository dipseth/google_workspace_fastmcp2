"""
Google Chat Card Examples
Demonstrates usage of the enhanced card-based messaging functionality.
"""

# Example card configurations for testing

SIMPLE_CARD_EXAMPLE = {
    "title": "Project Update",
    "subtitle": "Weekly Status Report",
    "text": "The project is progressing well. All milestones are on track and the team is performing excellently.",
    "image_url": "https://via.placeholder.com/300x200/4285f4/ffffff?text=Project+Status",
}

INTERACTIVE_CARD_EXAMPLE = {
    "title": "Meeting Request",
    "text": "Would you like to schedule a meeting to discuss the project details?",
    "buttons": [
        {
            "text": "Accept",
            "action": {
                "actionMethodName": "accept_meeting",
                "parameters": [{"key": "response", "value": "accepted"}],
            },
        },
        {
            "text": "Decline",
            "action": {
                "actionMethodName": "decline_meeting",
                "parameters": [{"key": "response", "value": "declined"}],
            },
        },
        {
            "text": "Suggest Alternative",
            "action": {
                "actionMethodName": "suggest_alternative",
                "parameters": [{"key": "response", "value": "alternative"}],
            },
        },
    ],
}

FORM_CARD_EXAMPLE = {
    "title": "Feedback Collection",
    "fields": [
        {
            "type": "text",
            "name": "name",
            "label": "Your Name",
            "hint": "Please enter your full name",
        },
        {
            "type": "text",
            "name": "email",
            "label": "Email Address",
            "hint": "We'll use this to follow up",
        },
        {
            "type": "selection",
            "name": "department",
            "label": "Department",
            "options": [
                {"text": "Engineering", "value": "eng"},
                {"text": "Product", "value": "product"},
                {"text": "Design", "value": "design"},
                {"text": "Marketing", "value": "marketing"},
            ],
        },
        {
            "type": "text",
            "name": "feedback",
            "label": "Your Feedback",
            "hint": "Please share your thoughts and suggestions",
        },
        {
            "type": "selection",
            "name": "rating",
            "label": "Overall Rating",
            "options": [
                {"text": "Excellent (5/5)", "value": "5"},
                {"text": "Good (4/5)", "value": "4"},
                {"text": "Average (3/5)", "value": "3"},
                {"text": "Poor (2/5)", "value": "2"},
                {"text": "Very Poor (1/5)", "value": "1"},
            ],
        },
    ],
    "submit_action": {
        "text": "Submit Feedback",
        "action": {
            "actionMethodName": "submit_feedback_form",
            "parameters": [{"key": "form_type", "value": "feedback"}],
        },
    },
}

NOTIFICATION_CARD_EXAMPLE = {
    "title": "System Alert",
    "text": "A new version of the application is available. Please update at your earliest convenience.",
    "buttons": [
        {
            "text": "Update Now",
            "action": {
                "actionMethodName": "update_application",
                "parameters": [{"key": "action", "value": "update_now"}],
            },
        },
        {
            "text": "Remind Later",
            "action": {
                "actionMethodName": "remind_later",
                "parameters": [
                    {"key": "action", "value": "remind_later"},
                    {"key": "delay", "value": "1_hour"},
                ],
            },
        },
        {
            "text": "Skip This Version",
            "action": {
                "actionMethodName": "skip_version",
                "parameters": [{"key": "action", "value": "skip"}],
            },
        },
    ],
}

WELCOME_CARD_EXAMPLE = {
    "title": "Welcome to the Team!",
    "subtitle": "Getting Started Guide",
    "text": "We're excited to have you join our team. Here are some resources to help you get started.",
    "image_url": "https://via.placeholder.com/400x200/34a853/ffffff?text=Welcome",
    "buttons": [
        {
            "text": "View Onboarding Guide",
            "action": {
                "actionMethodName": "open_onboarding",
                "parameters": [{"key": "resource", "value": "onboarding_guide"}],
            },
        },
        {
            "text": "Meet the Team",
            "action": {
                "actionMethodName": "view_team",
                "parameters": [{"key": "resource", "value": "team_directory"}],
            },
        },
    ],
}


# Helper function to demonstrate card usage
def get_example_card(card_type: str):
    """
    Get an example card configuration by type.

    Args:
        card_type: Type of card ("simple", "interactive", "form", "notification", "welcome")

    Returns:
        Dict containing card configuration
    """
    examples = {
        "simple": SIMPLE_CARD_EXAMPLE,
        "interactive": INTERACTIVE_CARD_EXAMPLE,
        "form": FORM_CARD_EXAMPLE,
        "notification": NOTIFICATION_CARD_EXAMPLE,
        "welcome": WELCOME_CARD_EXAMPLE,
    }

    return examples.get(card_type, SIMPLE_CARD_EXAMPLE)


# Test scenarios for different use cases
TEST_SCENARIOS = {
    "project_update": {
        "description": "Send a project status update with visual elements",
        "card_type": "simple",
        "config": SIMPLE_CARD_EXAMPLE,
    },
    "meeting_request": {
        "description": "Interactive meeting request with response options",
        "card_type": "interactive",
        "config": INTERACTIVE_CARD_EXAMPLE,
    },
    "feedback_collection": {
        "description": "Comprehensive feedback form with multiple input types",
        "card_type": "form",
        "config": FORM_CARD_EXAMPLE,
    },
    "system_notification": {
        "description": "System alert with action buttons",
        "card_type": "interactive",
        "config": NOTIFICATION_CARD_EXAMPLE,
    },
    "team_welcome": {
        "description": "Welcome message for new team members",
        "card_type": "interactive",
        "config": WELCOME_CARD_EXAMPLE,
    },
}


def get_test_scenario(scenario_name: str):
    """
    Get a test scenario configuration.

    Args:
        scenario_name: Name of the test scenario

    Returns:
        Dict containing scenario configuration
    """
    return TEST_SCENARIOS.get(scenario_name)


def list_available_examples():
    """
    List all available card examples and test scenarios.

    Returns:
        Dict with examples and scenarios
    """
    return {
        "examples": list(TEST_SCENARIOS.keys()),
        "card_types": ["simple", "interactive", "form", "notification", "welcome"],
        "scenarios": {
            name: scenario["description"] for name, scenario in TEST_SCENARIOS.items()
        },
    }
