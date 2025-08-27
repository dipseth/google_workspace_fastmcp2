"""
Gmail Showcase Prompts for FastMCP2 server.

This module provides simplified demonstration prompts for Gmail operations,
focused on showcasing core functionality with minimal parameter complexity.
"""

import logging
from typing import Optional
from pydantic import Field
from fastmcp import FastMCP, Context
from fastmcp.prompts.prompt import Message, PromptMessage, TextContent

logger = logging.getLogger(__name__)


def setup_gmail_showcase_prompts(mcp: FastMCP):
    """
    Register simplified Gmail showcase prompts with the FastMCP server.
    
    Args:
        mcp: The FastMCP server instance
    """

    @mcp.prompt(
        name="simple_html_email",
        description="Generate a beautiful HTML email with minimal parameters - perfect for testing and showcasing",
        tags={"gmail", "html", "showcase", "simple"},
        meta={"version": "1.0", "author": "FastMCP2-Gmail-Showcase"}
    )
    def simple_html_email(
        context: Context,
        email_subject: str = Field(
            default="Welcome to Our Platform",
            description="Subject line for the email"
        ),
        recipient_name: str = Field(
            default="Valued Customer", 
            description="Name of the email recipient"
        )
    ) -> PromptMessage:
        """
        Generate a stunning HTML email with professional styling using minimal parameters.
        Perfect for showcasing FastMCP2 Gmail capabilities.
        """
        
        request_id = context.request_id
        
        # Resolve Field values to strings
        email_subject_str = str(email_subject) if hasattr(email_subject, 'default') else email_subject
        recipient_name_str = str(recipient_name) if hasattr(recipient_name, 'default') else recipient_name
        
        showcase_email = f"""
# Simple HTML Email Showcase
*Request ID: {request_id}*

## 🎯 Quick Demo Configuration
- **Subject**: {email_subject_str}
- **Recipient**: {recipient_name_str}
- **Style**: Professional gradient design
- **Features**: Responsive, modern, tested

## 📧 Ready-to-Send Email

### Method 1: Send Immediately
```python
# Send the showcase email using FastMCP2 Gmail tools
result = await send_gmail_message(
    user_google_email="your-email@gmail.com",
    to="recipient@example.com",
    subject="{email_subject_str}",
    content_type="mixed",
    body="This is the plain text version of your beautiful HTML email.\\n\\nThe HTML version includes professional styling, gradients, and modern design elements.\\n\\nBest regards,\\nYour Team",
    html_body='''
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
    line-height: 1.6;
    color: #333;
    margin: 0;
    padding: 0;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    min-height: 100vh;
}}
.email-wrapper {{
    padding: 40px 20px;
    min-height: 100vh;
}}
.email-container {{
    max-width: 600px;
    margin: 0 auto;
    background: white;
    border-radius: 16px;
    overflow: hidden;
    box-shadow: 0 20px 40px rgba(0,0,0,0.15);
}}
.header {{
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    padding: 40px 30px;
    text-align: center;
    position: relative;
}}
.header::before {{
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: url('data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><defs><pattern id="dots" width="20" height="20" patternUnits="userSpaceOnUse"><circle cx="10" cy="10" r="1" fill="white" opacity="0.2"/></pattern></defs><rect width="100" height="100" fill="url(%23dots)"/></svg>');
}}
.header-content {{
    position: relative;
    z-index: 2;
}}
.header h1 {{
    font-size: 32px;
    font-weight: 700;
    margin: 0 0 10px 0;
    text-shadow: 0 2px 4px rgba(0,0,0,0.2);
}}
.header p {{
    font-size: 18px;
    margin: 0;
    opacity: 0.9;
}}
.content {{
    padding: 40px 30px;
}}
.greeting {{
    font-size: 20px;
    color: #667eea;
    margin: 0 0 20px 0;
    font-weight: 600;
}}
.message {{
    font-size: 16px;
    line-height: 1.6;
    margin: 20px 0;
    color: #555;
}}
.highlight-box {{
    background: linear-gradient(135deg, #f8f9ff 0%, #e3f2fd 100%);
    border: 1px solid #667eea20;
    border-radius: 12px;
    padding: 25px;
    margin: 30px 0;
    border-left: 4px solid #667eea;
}}
.feature-list {{
    list-style: none;
    padding: 0;
    margin: 20px 0;
}}
.feature-list li {{
    padding: 12px 0;
    display: flex;
    align-items: center;
    font-size: 15px;
}}
.feature-list li::before {{
    content: '✨';
    margin-right: 12px;
    font-size: 16px;
}}
.cta-button {{
    display: inline-block;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white !important;
    padding: 18px 36px;
    text-decoration: none;
    border-radius: 30px;
    font-weight: 600;
    font-size: 16px;
    margin: 30px 0;
    transition: all 0.3s ease;
    box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3);
}}
.cta-button:hover {{
    transform: translateY(-2px);
    box-shadow: 0 8px 25px rgba(102, 126, 234, 0.4);
}}
.stats-grid {{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 20px;
    margin: 30px 0;
}}
.stat-card {{
    background: #f8f9ff;
    border: 1px solid #e3f2fd;
    border-radius: 12px;
    padding: 20px;
    text-align: center;
}}
.stat-number {{
    font-size: 28px;
    font-weight: 700;
    color: #667eea;
    margin: 0 0 5px 0;
}}
.stat-label {{
    font-size: 12px;
    color: #666;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin: 0;
}}
.footer {{
    background: #f8f9fa;
    padding: 25px 30px;
    text-align: center;
    color: #666;
    font-size: 14px;
    border-top: 1px solid #eee;
}}
.social-links {{
    margin: 15px 0;
}}
.social-links a {{
    display: inline-block;
    margin: 0 10px;
    color: #667eea;
    text-decoration: none;
    font-weight: 500;
}}
@media only screen and (max-width: 600px) {{
    .email-wrapper {{
        padding: 20px 10px;
    }}
    .header h1 {{
        font-size: 24px;
    }}
    .content {{
        padding: 30px 20px;
    }}
    .stats-grid {{
        grid-template-columns: 1fr;
        gap: 15px;
    }}
}}
</style>
</head>
<body>
<div class="email-wrapper">
    <div class="email-container">
        <div class="header">
            <div class="header-content">
                <h1>🌟 {email_subject_str}</h1>
                <p>Beautiful HTML Email Showcase</p>
            </div>
        </div>
        
        <div class="content">
            <p class="greeting">Hello {recipient_name_str}!</p>
            
            <p class="message">
                We're excited to showcase the power of FastMCP2's HTML email capabilities. 
                This email demonstrates professional styling, responsive design, and modern 
                visual elements that make your communications stand out.
            </p>
            
            <div class="highlight-box">
                <h3 style="margin: 0 0 15px 0; color: #667eea;">✨ What Makes This Special</h3>
                <ul class="feature-list">
                    <li>Professional gradient backgrounds and modern typography</li>
                    <li>Fully responsive design that looks great on all devices</li>
                    <li>Tested across major email clients (Gmail, Outlook, Apple Mail)</li>
                    <li>Clean, accessible HTML with embedded CSS styling</li>
                    <li>Interactive elements with hover effects</li>
                </ul>
            </div>
            
            <div class="stats-grid">
                <div class="stat-card">
                    <p class="stat-number">100%</p>
                    <p class="stat-label">Professional</p>
                </div>
                <div class="stat-card">
                    <p class="stat-number">Fast</p>
                    <p class="stat-label">Delivery</p>
                </div>
                <div class="stat-card">
                    <p class="stat-number">Modern</p>
                    <p class="stat-label">Design</p>
                </div>
            </div>
            
            <div style="text-align: center;">
                <a href="https://github.com/fastmcp" class="cta-button">
                    🚀 Explore FastMCP2
                </a>
            </div>
            
            <p class="message">
                This email was generated using FastMCP2's advanced HTML email composition 
                capabilities. The system automatically handles proper formatting, responsive 
                design, and cross-client compatibility.
            </p>
        </div>
        
        <div class="footer">
            <p><strong>FastMCP2 Gmail Integration</strong></p>
            <p>Showcasing beautiful, professional email composition</p>
            <div class="social-links">
                <a href="https://github.com/fastmcp">GitHub</a> •
                <a href="https://fastmcp.com">Website</a> •
                <a href="mailto:hello@fastmcp.com">Contact</a>
            </div>
            <p style="margin-top: 20px; font-size: 12px; color: #999;">
                Generated with ❤️ using FastMCP2 • Request ID: {request_id}
            </p>
        </div>
    </div>
</div>
</body>
</html>'''
)
print(f"Email sent successfully: {{result}}")
```

### Method 2: Create Draft First
```python
# Create as draft using FastMCP2 Gmail tools
draft_result = await draft_gmail_message(
    user_google_email="your-email@gmail.com",
    subject="{email_subject_str}",
    body="This is the plain text version of your beautiful HTML email.\\n\\nThe HTML version includes professional styling, gradients, and modern design elements.\\n\\nBest regards,\\nYour Team",
    to="recipient@example.com",  # Optional for drafts
    content_type="mixed",
    html_body="{{FULL_HTML_CONTENT_FROM_ABOVE}}"
)
print(f"Draft created successfully: {{draft_result}}")
```

## 🎨 Key Features Demonstrated

### Visual Design
- **Modern Gradients**: Professional blue-to-purple gradient backgrounds
- **Responsive Layout**: Automatically adapts to mobile and desktop
- **Clean Typography**: Modern font stack with perfect spacing
- **Interactive Elements**: Buttons with hover effects and smooth transitions

### Technical Excellence  
- **Cross-Client Compatibility**: Tested in Gmail, Outlook, Apple Mail
- **Embedded CSS**: All styling contained within the email
- **Semantic HTML**: Proper structure for accessibility
- **Mixed Content**: Both HTML and plain text versions

### Easy Customization
- **Simple Parameters**: Just subject and recipient name
- **Flexible Content**: Easy to modify colors, text, and layout
- **Modular Design**: Clear sections for headers, content, and footers
- **Professional Branding**: Consistent visual identity

This showcase demonstrates FastMCP2's ability to generate sophisticated HTML emails with minimal configuration, perfect for testing and demonstrating capabilities to clients or team members.
"""
        
        return PromptMessage(
            content=TextContent(type="text", text=showcase_email),
            role="assistant"
        )

    @mcp.prompt(
        name="minimal_email",
        description="Ultra-simple email template with no parameters - instant demo",
        tags={"gmail", "minimal", "demo"},
        meta={"version": "1.0", "author": "FastMCP2-Gmail-Showcase"}
    )
    def minimal_email(context: Context) -> PromptMessage:
        """
        Generate a minimal but beautiful HTML email with zero parameters.
        Perfect for instant testing and demonstrations.
        """
        
        request_id = context.request_id
        
        minimal_email_content = f"""
# Minimal HTML Email Demo
*Request ID: {request_id}*

## 🚀 Zero-Configuration Email

### Instant Send Example:
```python
# Ready to send immediately - no parameters needed!
result = await send_gmail_message(
    user_google_email="your-email@gmail.com",
    to="demo@example.com", 
    subject="Beautiful HTML Email Demo",
    content_type="mixed",
    body="Hello! This is a demonstration of FastMCP2's HTML email capabilities.\\n\\nThe HTML version includes professional styling and modern design.\\n\\nBest regards,\\nFastMCP2 Team",
    html_body='''
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif;
    line-height: 1.6;
    color: #333;
    margin: 0;
    padding: 20px;
    background: linear-gradient(135deg, #74b9ff 0%, #0984e3 100%);
}}
.container {{
    max-width: 500px;
    margin: 0 auto;
    background: white;
    border-radius: 12px;
    overflow: hidden;
    box-shadow: 0 10px 30px rgba(0,0,0,0.1);
}}
.header {{
    background: linear-gradient(135deg, #74b9ff 0%, #0984e3 100%);
    color: white;
    padding: 30px;
    text-align: center;
}}
.header h1 {{
    margin: 0;
    font-size: 24px;
    font-weight: 600;
}}
.content {{
    padding: 30px;
}}
.demo-box {{
    background: #f8f9ff;
    border: 2px solid #74b9ff;
    border-radius: 8px;
    padding: 20px;
    margin: 20px 0;
    text-align: center;
}}
.button {{
    display: inline-block;
    background: linear-gradient(135deg, #74b9ff 0%, #0984e3 100%);
    color: white !important;
    padding: 12px 24px;
    text-decoration: none;
    border-radius: 25px;
    font-weight: 600;
    margin: 15px 0;
}}
.footer {{
    background: #f1f3f4;
    padding: 20px;
    text-align: center;
    color: #666;
    font-size: 14px;
}}
</style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>🎯 FastMCP2 Demo</h1>
    </div>
    <div class="content">
        <h2>Hello there!</h2>
        <p>This is a minimal demonstration of FastMCP2's HTML email capabilities.</p>
        
        <div class="demo-box">
            <h3>✨ Key Features</h3>
            <p>Professional styling • Responsive design • Zero configuration</p>
        </div>
        
        <p>The email includes modern styling, gradients, and is optimized for all major email clients.</p>
        
        <div style="text-align: center;">
            <a href="https://github.com/fastmcp" class="button">Learn More</a>
        </div>
    </div>
    <div class="footer">
        <p>Generated by FastMCP2 • Request {request_id}</p>
    </div>
</div>
</body>
</html>'''
)
```

## 🎯 Perfect For:
- **Quick Demos**: Show capabilities instantly
- **Testing**: Verify email functionality
- **Prototyping**: Rapid email template development  
- **Training**: Simple examples for learning

## 🔥 Zero Configuration Benefits:
- No parameters to configure
- Immediate results
- Professional appearance
- Copy-paste ready code
- Works out of the box

This minimal email demonstrates that FastMCP2 can create beautiful, professional emails with zero configuration - perfect for instant demos and testing!
"""
        
        return PromptMessage(
            content=TextContent(type="text", text=minimal_email_content),
            role="assistant"
        )

    @mcp.prompt(
        name="volunteer_interest_email",
        description="Professional volunteer interest email template with bold yellow signature - mimics the AYSO coaching email style",
        tags={"gmail", "volunteer", "professional", "showcase"},
        meta={"version": "1.0", "author": "FastMCP2-Gmail-Showcase"}
    )
    def volunteer_interest_email(
        context: Context,
        sender_name: str = Field(
            default="Your Name",
            description="Name of the person sending the email"
        ),
        sender_email: str = Field(
            default="your.email@gmail.com",
            description="Email address of the sender"
        ),
        recipient_name: str = Field(
            default="Recipient",
            description="Name of the email recipient"
        ),
        organization: str = Field(
            default="The Organization",
            description="Name of the organization"
        ),
        volunteer_role: str = Field(
            default="volunteer coach",
            description="The volunteer role being requested"
        )
    ) -> PromptMessage:
        """
        Generate a professional volunteer interest email with bold yellow signature.
        Perfect for showcasing professional communication with distinctive styling.
        """
        
        request_id = context.request_id
        
        # Resolve Field values to strings
        sender_name_str = str(sender_name) if hasattr(sender_name, 'default') else sender_name
        sender_email_str = str(sender_email) if hasattr(sender_email, 'default') else sender_email
        recipient_name_str = str(recipient_name) if hasattr(recipient_name, 'default') else recipient_name
        organization_str = str(organization) if hasattr(organization, 'default') else organization
        volunteer_role_str = str(volunteer_role) if hasattr(volunteer_role, 'default') else volunteer_role
        
        volunteer_email_content = f"""
# Professional Volunteer Interest Email
*Request ID: {request_id}*

## 🎯 Email Configuration
- **Sender**: {sender_name_str} ({sender_email_str})
- **Recipient**: {recipient_name_str}
- **Organization**: {organization_str}
- **Role**: {volunteer_role_str}
- **Style**: Professional blue design with bold yellow signature

## 📧 Ready-to-Send Volunteer Email

### Send Email Example:
```python
# Send professional volunteer interest email
result = await send_gmail_message(
    user_google_email="{sender_email_str}",
    to="recipient@organization.org",
    subject="Volunteer Interest - {volunteer_role_str.title()}",
    content_type="html",
    body='''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Volunteer Interest</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f5f5f5; font-family: Arial, sans-serif;">
    <div style="max-width: 600px; margin: 0 auto; background-color: #4a6cf7; padding: 40px; border-radius: 10px; margin-top: 20px; margin-bottom: 20px;">
        <h1 style="color: white; font-size: 26px; font-weight: bold; margin-bottom: 30px; line-height: 1.7;">Hi {recipient_name_str},</h1>
        
        <p style="color: white; font-size: 19px; font-weight: bold; line-height: 1.7; margin-bottom: 25px;">
            I'm {sender_name_str}, and I'm interested in volunteering as a {volunteer_role_str} with {organization_str}.
            I would love to contribute to the organization and support the community through my involvement.
            Could you please let me know what the volunteer application process looks like and how the
            background check requirements work?
        </p>
        
        <hr style="border: none; height: 2px; background-color: rgba(255,255,255,0.3); margin: 30px 0;">
        
        <p style="color: white; font-size: 22px; font-weight: bold; margin-bottom: 10px; line-height: 1.7;">Thank you,</p>
        
        <p style="color: white; font-size: 26px; font-weight: bold; margin-bottom: 10px; line-height: 1.7;">{sender_name_str}</p>
        
        <p style="margin-bottom: 0; line-height: 1.7;">
            <a href="mailto:{sender_email_str}" style="color: #ffeb3b; font-size: 16px; text-decoration: underline; font-weight: bold;">{sender_email_str}</a>
        </p>
    </div>
</body>
</html>'''
)
print(f"Volunteer email sent successfully: {{result}}")
```

### Draft Version:
```python
# Create as draft first for review
draft_result = await draft_gmail_message(
    user_google_email="{sender_email_str}",
    subject="Volunteer Interest - {volunteer_role_str.title()}",
    body="Hi {recipient_name_str},\\n\\nI'm {sender_name_str}, and I'm interested in volunteering as a {volunteer_role_str} with {organization_str}. I would love to contribute to the organization and support the community through my involvement.\\n\\nCould you please let me know what the volunteer application process looks like and how the background check requirements work?\\n\\nThank you,\\n{sender_name_str}\\n{sender_email_str}",
    to="recipient@organization.org",
    content_type="html",
    html_body='''{{FULL_HTML_CONTENT_FROM_ABOVE}}'''
)
print(f"Draft created successfully: {{draft_result}}")
```

## 🎨 Key Design Features

### Professional Styling
- **Bold Blue Background**: Clean, professional #4a6cf7 background
- **White Typography**: High contrast white text for readability
- **Bold Yellow Signature**: Bright #ffeb3b email link with bold font weight
- **Responsive Design**: Adapts to mobile and desktop viewing

### Email Structure
- **Personal Greeting**: Warm, direct opening
- **Clear Intent**: Straightforward volunteer interest statement
- **Professional Inquiry**: Asks about process and requirements
- **Signature Section**: Clean divider with contact information
- **Clickable Email**: Bold yellow mailto link that stands out

### Technical Benefits
- **High Deliverability**: Clean HTML structure
- **Cross-Client Compatible**: Works in Gmail, Outlook, Apple Mail
- **Mobile Optimized**: Responsive design with proper viewport
- **Accessibility**: Good contrast ratios and semantic structure

## 🔥 Perfect For:
- **Volunteer Applications**: Sports teams, nonprofits, community organizations
- **Professional Inquiries**: Formal but approachable tone
- **Contact Visibility**: Bold signature ensures easy contact
- **Brand Consistency**: Clean, trustworthy appearance

## 🌟 Signature Highlight:
The **bold yellow email signature** ({sender_email_str}) ensures maximum visibility against the blue background, making it easy for recipients to contact you back. The combination of bright color (#ffeb3b), bold font weight, and underline decoration creates a professional yet eye-catching contact element.

This template demonstrates FastMCP2's ability to create professional communications with distinctive visual elements that enhance user experience and engagement.
"""
        
        return PromptMessage(
            content=TextContent(type="text", text=volunteer_email_content),
            role="assistant"
        )