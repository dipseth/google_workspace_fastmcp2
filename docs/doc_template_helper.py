"""
Helper module for creating dynamic Google Docs using Jinja2 templates.
This integrates with the middleware template system for seamless document generation.
"""

import asyncio
from pathlib import Path
from typing import Any, Dict, Optional, Union

from jinja2 import ChoiceLoader, Environment, FileSystemLoader

from docs.docs_tools import create_doc
from docs.docs_types import CreateDocResponse
from tools.common_types import UserGoogleEmail


class DocTemplateEngine:
    """Engine for creating templated Google Docs with middleware integration."""

    def __init__(self, template_dirs: Optional[Union[str, list]] = None):
        """Initialize the template engine with middleware template support.

        Args:
            template_dirs: Directory or list of directories containing template files.
                         Automatically includes middleware/templates for macro access.
        """
        loaders = []

        # Always include middleware templates directory for shared macros
        middleware_templates = Path(__file__).parent.parent / "middleware" / "templates"
        if middleware_templates.exists():
            loaders.append(FileSystemLoader(str(middleware_templates)))

        # Add custom template directories
        if template_dirs:
            if isinstance(template_dirs, str):
                template_dirs = [template_dirs]
            for dir_path in template_dirs:
                if Path(dir_path).exists():
                    loaders.append(FileSystemLoader(dir_path))

        # Use ChoiceLoader to combine multiple template directories
        if loaders:
            self.env = Environment(loader=ChoiceLoader(loaders))
        else:
            self.env = Environment()

        # Load macros from middleware templates
        self._load_middleware_macros()

    def _load_middleware_macros(self):
        """Load macros from middleware template files."""
        try:
            # Load document_templates.j2 if it exists
            if self.env.loader:
                template = self.env.get_template("document_templates.j2")
                module = template.make_module()

                # Register all macros globally
                for attr_name in dir(module):
                    if not attr_name.startswith("_"):
                        attr_value = getattr(module, attr_name)
                        if callable(attr_value):
                            self.env.globals[attr_name] = attr_value
        except Exception:
            # Silently skip if template not found
            pass

    async def create_from_template(
        self,
        title: str,
        template_string: str,
        context: Dict[str, Any],
        user_google_email: UserGoogleEmail = None,
    ) -> CreateDocResponse:
        """Create a Google Doc from a Jinja2 template string.

        Args:
            title: Document title
            template_string: Jinja2 template as string (can use middleware macros)
            context: Dictionary of variables to populate the template
            user_google_email: User's Google email

        Returns:
            CreateDocResponse with document details
        """
        # Create Jinja2 template with access to middleware macros
        template = self.env.from_string(template_string)

        # Render template with context
        rendered_html = template.render(**context)

        # Create Google Doc with rendered HTML
        return await create_doc(
            title=title,
            content=rendered_html,
            user_google_email=user_google_email,
            content_mime_type="text/html",
        )

    async def create_from_file(
        self,
        title: str,
        template_file: str,
        context: Dict[str, Any],
        user_google_email: UserGoogleEmail = None,
    ) -> CreateDocResponse:
        """Create a Google Doc from a Jinja2 template file.

        Args:
            title: Document title
            template_file: Path to template file (can be in middleware/templates)
            context: Dictionary of variables to populate the template
            user_google_email: User's Google email

        Returns:
            CreateDocResponse with document details
        """
        template = self.env.get_template(template_file)
        rendered_html = template.render(**context)

        return await create_doc(
            title=title,
            content=rendered_html,
            user_google_email=user_google_email,
            content_mime_type="text/html",
        )

    async def create_from_macro(
        self,
        title: str,
        macro_name: str,
        context: Dict[str, Any],
        user_google_email: UserGoogleEmail = None,
    ) -> CreateDocResponse:
        """Create a Google Doc using a middleware template macro.

        This is a convenience method for using macros from middleware/templates.

        Args:
            title: Document title
            macro_name: Name of the macro (e.g., 'generate_invoice_doc')
            context: Dictionary of variables for the macro
            user_google_email: User's Google email

        Returns:
            CreateDocResponse with document details

        Example:
            response = await engine.create_from_macro(
                title="Invoice #123",
                macro_name="generate_invoice_doc",
                context={
                    "invoice_number": "INV-2024-123",
                    "client": {"name": "Acme Corp", ...},
                    "line_items": [...],
                    ...
                }
            )
        """
        # Get the macro function from Jinja2 globals
        if macro_name not in self.env.globals:
            raise ValueError(
                f"Macro '{macro_name}' not found. Available macros: {list(self.env.globals.keys())}"
            )

        # Create a simple template that calls the macro
        template_string = f"{{{{ {macro_name}(**context) }}}}"
        template = self.env.from_string(template_string)

        # Render with the context
        rendered_html = template.render(context=context)

        return await create_doc(
            title=title,
            content=rendered_html,
            user_google_email=user_google_email,
            content_mime_type="text/html",
        )


# Example usage with middleware integration
TEMPLATE_WITH_MACROS = """
{# This template uses macros from middleware/templates/document_templates.j2 #}
{% if document_type == 'report' %}
    {{ generate_report_doc(
        report_title=title,
        metrics=metrics,
        table_headers=headers,
        table_data=data,
        company_name=company
    ) }}
{% elif document_type == 'invoice' %}
    {{ generate_invoice_doc(
        invoice_number=invoice_num,
        client=client_info,
        line_items=items,
        total=total_amount
    ) }}
{% else %}
    <h1>{{ title }}</h1>
    <p>{{ content }}</p>
{% endif %}
"""

# Legacy templates kept for backward compatibility
REPORT_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <style>
        body { font-family: Arial, sans-serif; }
        .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                  color: white; padding: 30px; border-radius: 10px; }
        .metric { display: inline-block; margin: 20px; padding: 20px; 
                  background: #f7f7f7; border-radius: 8px; min-width: 150px; }
        .metric-value { font-size: 32px; font-weight: bold; color: #333; }
        .metric-label { color: #666; margin-top: 5px; }
        table { width: 100%; border-collapse: collapse; margin: 20px 0; }
        th { background: #667eea; color: white; padding: 12px; text-align: left; }
        td { padding: 10px; border-bottom: 1px solid #ddd; }
        .chart { margin: 20px 0; padding: 20px; background: #f9f9f9; border-radius: 8px; }
    </style>
</head>
<body>
    <div class="header">
        <h1>{{ report_title }}</h1>
        <p>Generated: {{ generation_date }}</p>
        <p>Period: {{ start_date }} to {{ end_date }}</p>
    </div>
    
    <h2>📊 Key Metrics</h2>
    <div>
        {% for metric in metrics %}
        <div class="metric">
            <div class="metric-value">{{ metric.value }}</div>
            <div class="metric-label">{{ metric.label }}</div>
            {% if metric.change %}
            <div style="color: {% if metric.change > 0 %}green{% else %}red{% endif %};">
                {{ metric.change }}% change
            </div>
            {% endif %}
        </div>
        {% endfor %}
    </div>
    
    <h2>📈 Performance Data</h2>
    <table>
        <tr>
            {% for header in table_headers %}
            <th>{{ header }}</th>
            {% endfor %}
        </tr>
        {% for row in table_data %}
        <tr>
            {% for cell in row %}
            <td>{{ cell }}</td>
            {% endfor %}
        </tr>
        {% endfor %}
    </table>
    
    {% if charts %}
    <h2>📉 Visualizations</h2>
    {% for chart in charts %}
    <div class="chart">
        <h3>{{ chart.title }}</h3>
        <p>{{ chart.description }}</p>
        <!-- In real usage, you could embed chart images or use Chart.js -->
        <div style="height: 200px; background: linear-gradient(to right, #667eea20, #764ba220); 
                    display: flex; align-items: center; justify-content: center; border-radius: 8px;">
            [{{ chart.type }} Chart: {{ chart.data_points }} data points]
        </div>
    </div>
    {% endfor %}
    {% endif %}
    
    <footer style="margin-top: 40px; padding: 20px; background: #f0f0f0; border-radius: 8px;">
        <p><strong>{{ company_name | default('Your Company') }}</strong></p>
        <p>{{ footer_text | default('Confidential Report') }}</p>
    </footer>
</body>
</html>
"""

INVOICE_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <style>
        body { font-family: 'Segoe UI', sans-serif; max-width: 800px; margin: 0 auto; }
        .invoice-header { display: flex; justify-content: space-between; margin-bottom: 30px; }
        .company-info { text-align: right; }
        .invoice-details { background: #f5f5f5; padding: 20px; border-radius: 8px; margin: 20px 0; }
        .line-items { margin: 30px 0; }
        table { width: 100%; border-collapse: collapse; }
        th { background: #333; color: white; padding: 10px; text-align: left; }
        td { padding: 10px; border-bottom: 1px solid #ddd; }
        .total-section { text-align: right; margin-top: 20px; }
        .total-row { font-size: 18px; font-weight: bold; color: #333; }
        .payment-info { background: #e8f4fd; padding: 20px; border-radius: 8px; margin-top: 30px; }
    </style>
</head>
<body>
    <div class="invoice-header">
        <div>
            <h1 style="color: #333;">INVOICE</h1>
            <p>Invoice #: {{ invoice_number }}</p>
            <p>Date: {{ invoice_date }}</p>
            <p>Due Date: {{ due_date }}</p>
        </div>
        <div class="company-info">
            <h2>{{ company.name }}</h2>
            <p>{{ company.address }}</p>
            <p>{{ company.city }}, {{ company.state }} {{ company.zip }}</p>
            <p>{{ company.email }}</p>
            <p>{{ company.phone }}</p>
        </div>
    </div>
    
    <div class="invoice-details">
        <h3>Bill To:</h3>
        <p><strong>{{ client.name }}</strong></p>
        <p>{{ client.address }}</p>
        <p>{{ client.city }}, {{ client.state }} {{ client.zip }}</p>
        <p>{{ client.email }}</p>
    </div>
    
    <div class="line-items">
        <table>
            <tr>
                <th>Item Description</th>
                <th>Quantity</th>
                <th>Rate</th>
                <th>Amount</th>
            </tr>
            {% for item in line_items %}
            <tr>
                <td>{{ item.description }}</td>
                <td>{{ item.quantity }}</td>
                <td>${{ "%.2f"|format(item.rate) }}</td>
                <td>${{ "%.2f"|format(item.quantity * item.rate) }}</td>
            </tr>
            {% endfor %}
        </table>
    </div>
    
    <div class="total-section">
        <p>Subtotal: ${{ "%.2f"|format(subtotal) }}</p>
        {% if tax_rate %}
        <p>Tax ({{ tax_rate }}%): ${{ "%.2f"|format(tax_amount) }}</p>
        {% endif %}
        {% if discount %}
        <p>Discount: -${{ "%.2f"|format(discount) }}</p>
        {% endif %}
        <p class="total-row">Total Due: ${{ "%.2f"|format(total) }}</p>
    </div>
    
    <div class="payment-info">
        <h3>Payment Information</h3>
        <p>{{ payment_instructions | default('Please make payment by the due date.') }}</p>
        {% if bank_details %}
        <p><strong>Bank Details:</strong></p>
        <p>Account Name: {{ bank_details.account_name }}</p>
        <p>Account Number: {{ bank_details.account_number }}</p>
        <p>Routing Number: {{ bank_details.routing_number }}</p>
        {% endif %}
    </div>
    
    {% if notes %}
    <div style="margin-top: 30px; padding: 20px; background: #fffbf0; border-radius: 8px;">
        <h3>Notes</h3>
        <p>{{ notes }}</p>
    </div>
    {% endif %}
    
    <footer style="margin-top: 40px; text-align: center; color: #666;">
        <p>Thank you for your business!</p>
        <p style="font-size: 12px;">{{ terms | default('Payment is due within 30 days. Late payments subject to 1.5% monthly interest.') }}</p>
    </footer>
</body>
</html>
"""


async def example_usage():
    """Example of using the template engine with middleware integration."""
    engine = DocTemplateEngine()

    # Example 1: Using middleware macros directly
    print("\n📄 Example 1: Using middleware macros for a report")
    response = await engine.create_from_macro(
        title="Q4 2024 Performance Report",
        macro_name="generate_report_doc",
        context={
            "report_title": "Q4 2024 Performance Report",
            "generation_date": "2024-01-08",
            "start_date": "2024-10-01",
            "end_date": "2024-12-31",
            "metrics": [
                {"value": "$1.2M", "label": "Revenue", "change": 15},
                {"value": "847", "label": "New Customers", "change": 22},
            ],
            "table_headers": ["Month", "Revenue", "Customers", "Growth"],
            "table_data": [
                ["October", "$380K", "265", "+12%"],
                ["November", "$405K", "289", "+18%"],
                ["December", "$415K", "293", "+20%"],
            ],
            "company_name": "TechCorp Analytics",
            "footer_text": "Confidential - Internal Use Only",
        },
        user_google_email="user@example.com",
    )
    print(f"✅ Report created: {response['webViewLink']}")

    # Example 2: Using middleware macros for an invoice
    print("\n💰 Example 2: Using middleware macros for an invoice")
    response = await engine.create_from_macro(
        title="Invoice INV-2024-001",
        macro_name="generate_invoice_doc",
        context={
            "invoice_number": "INV-2024-001",
            "invoice_date": "2024-01-08",
            "due_date": "2024-02-08",
            "company": {
                "name": "Tech Solutions Inc.",
                "address": "123 Tech Street",
                "city": "San Francisco",
                "state": "CA",
                "zip": "94105",
                "email": "billing@techsolutions.com",
                "phone": "(555) 123-4567",
            },
            "client": {
                "name": "Acme Corporation",
                "address": "456 Business Ave",
                "city": "New York",
                "state": "NY",
                "zip": "10001",
                "email": "accounts@acme.com",
            },
            "line_items": [
                {
                    "description": "Web Development Services",
                    "quantity": 40,
                    "rate": 150,
                },
                {"description": "UI/UX Design", "quantity": 20, "rate": 125},
            ],
            "subtotal": 8500,
            "tax_rate": 8.5,
            "tax_amount": 722.50,
            "total": 9222.50,
            "payment_instructions": "Please pay via wire transfer or check.",
        },
        user_google_email="user@example.com",
    )
    print(f"✅ Invoice created: {response['webViewLink']}")

    # Example 3: Using template with conditional macro selection
    print("\n🔄 Example 3: Template with conditional macro selection")
    response = await engine.create_from_template(
        title="Dynamic Document",
        template_string=TEMPLATE_WITH_MACROS,
        context={
            "document_type": "report",
            "title": "Sales Report",
            "metrics": [{"value": "500", "label": "Units Sold"}],
            "headers": ["Product", "Sales"],
            "data": [["Widget A", "250"], ["Widget B", "250"]],
            "company": "Dynamic Corp",
        },
        user_google_email="user@example.com",
    )
    print(f"✅ Dynamic document created: {response['webViewLink']}")

    # Example 4: Using meeting notes macro
    print("\n📋 Example 4: Meeting notes document")
    response = await engine.create_from_macro(
        title="Team Standup - January 8",
        macro_name="generate_meeting_notes_doc",
        context={
            "meeting_title": "Daily Standup",
            "meeting_date": "2024-01-08",
            "meeting_time": "9:00 AM PST",
            "location": "Zoom",
            "attendees": ["Alice", "Bob", "Charlie", "Diana"],
            "discussion_points": [
                {"topic": "Sprint Progress", "summary": "On track for Friday release"},
                {"topic": "Blockers", "summary": "Waiting on API documentation"},
            ],
            "action_items": [
                {
                    "task": "Complete API integration",
                    "assignee": "Alice",
                    "due_date": "Jan 10",
                },
                {"task": "Review PR #123", "assignee": "Bob", "due_date": "Jan 8"},
            ],
            "next_meeting": "Tomorrow, 9:00 AM PST",
        },
        user_google_email="user@example.com",
    )
    print(f"✅ Meeting notes created: {response['webViewLink']}")

    print("\n🎉 All documents created successfully using middleware templates!")


if __name__ == "__main__":
    # Run examples
    asyncio.run(example_usage())
