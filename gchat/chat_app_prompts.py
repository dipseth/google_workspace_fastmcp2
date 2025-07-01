"""
Enhanced Google Chat Application Prompts with Advanced FastMCP Capabilities
=======================================================================

This module provides sophisticated prompt functions for Google Chat app development that demonstrate
the full capabilities of the FastMCP prompt system including:

- Advanced parameter handling with comprehensive Field() descriptions
- Sophisticated enum classes for structured parameters
- Simple typed parameters (list[str], dict[str, str], bool, float with constraints)
- Context object support for accessing MCP information
- Enhanced return types (PromptMessage, list[Message])
- Practical, real-world defaults showcasing capabilities

Author: Enhanced FastMCP Implementation
Version: 2.0
"""

from typing import Optional, Union
from pydantic import Field
from fastmcp import FastMCP, Context
from fastmcp.prompts.prompt import Message, PromptMessage, TextContent


# ============================================================================
# SETUP FUNCTION FOR FASTMCP REGISTRATION
# ============================================================================

def setup_chat_app_prompts(mcp: FastMCP):
    """
    Register all Google Chat app prompts with the FastMCP server.
    
    Args:
        mcp: The FastMCP server instance
    """

    @mcp.prompt(
        name="google_chat_complex_card_advanced",
        description="Generate sophisticated interactive card creation guidance with advanced FastMCP capabilities",
        tags={"google_chat", "cards", "interactive", "advanced"}
    )
    def google_chat_complex_card_advanced(
        context: Context,
        card_type: str = Field(default="approval_workflow", description="Type of sophisticated card to create"),
        integration_services: str = Field(
            default="drive,calendar",
            description="Comma-separated list of Google services to integrate with the card"
        ),
        complexity_level: float = Field(
            default=0.75,
            ge=0.0,
            le=1.0,
            description="Complexity level from 0.0 (basic) to 1.0 (highly advanced)"
        ),
        use_interactive_elements: bool = Field(
            default=True,
            description="Include interactive elements like buttons, forms, and widgets"
        ),
        styling_theme: str = Field(
            default="professional",
            description="Styling theme for the card"
        ),
        custom_actions: str = Field(
            default="approve,reject,comment",
            description="Comma-separated list of custom action buttons to include"
        )
    ) -> PromptMessage:
        """
        Generate comprehensive guidance for creating sophisticated interactive Google Chat cards
        with advanced capabilities and real-world integration examples.
        """
        
        # Access context information
        request_id = context.request_id
        
        # Parse comma-separated strings
        services_list = [s.strip() for s in integration_services.split(',')]
        actions_list = [a.strip() for a in custom_actions.split(',')]
        
        services_text = ", ".join(services_list)
        actions_text = ", ".join(actions_list)
        
        complexity_description = "basic" if complexity_level < 0.3 else "intermediate" if complexity_level < 0.7 else "advanced"
        
        card_guidance = f"""
# Advanced Google Chat Card Creation Guide

## Card Configuration (Request ID: {request_id})
- **Card Type**: {card_type.replace('_', ' ').title()}
- **Complexity Level**: {complexity_description} ({complexity_level:.2f})
- **Interactive Elements**: {'Enabled' if use_interactive_elements else 'Disabled'}

## Service Integrations
Integrated Services: {services_text}

## Interactive Elements
Custom Actions: {actions_text}

## Styling Configuration
Theme: {styling_theme}

## Implementation Code

```python
def create_{card_type}_card():
    card = {{
        "header": {{
            "title": "{card_type.replace('_', ' ').title()} Card",
            "subtitle": "Powered by FastMCP Advanced Capabilities",
            "imageUrl": "https://developers.google.com/chat/images/chat-product-icon.png"
        }},
        "sections": [
            {{
                "widgets": [
                    {{
                        "textParagraph": {{
                            "text": "<b>Status:</b> Active | <b>Priority:</b> High<br><b>Services:</b> {services_text}"
                        }}
                    }},
                    {{
                        "buttons": [
                            {{"textButton": {{"text": action.title(), "onClick": {{"action": {{"actionMethodName": f"handle_{action}"}}}}}}}}
                            for action in {actions_list}
                        ]
                    }}
                ]
            }}
        ]
    }}
    return card
```

## Advanced Features

### Dynamic Content Loading
- Real-time data integration from {services_text}
- Automatic refresh capabilities
- Context-aware content updates

### Workflow Integration
- Approval workflows with multi-step processes
- Notification cascading
- Data validation and processing

### Security Considerations
- OAuth 2.0 authentication
- Service account permissions
- Data encryption in transit

## Deployment Checklist
- [ ] Configure service account credentials
- [ ] Set up webhook endpoints
- [ ] Test interactive elements
- [ ] Validate service integrations
- [ ] Deploy to target environment

This {complexity_description} implementation showcases FastMCP's advanced parameter handling capabilities.
"""
        
        return PromptMessage(
            content=TextContent(text=card_guidance),
            role="assistant"
        )

    @mcp.prompt(
        name="google_chat_app_setup_guide",
        description="Comprehensive Google Chat app setup guide with deployment options and advanced configuration",
        tags={"google_chat", "setup", "deployment", "configuration"}
    )
    def google_chat_app_setup_guide(
        context: Context,
        deployment_target: str = Field(default="cloud_run", description="Target deployment platform"),
        authentication_type: str = Field(default="service_account", description="Authentication method to use"),
        required_services: str = Field(
            default="chat,drive",
            description="Comma-separated list of Google Workspace services to enable"
        ),
        enable_monitoring: bool = Field(default=True, description="Enable comprehensive monitoring and logging"),
        environment: str = Field(default="development", description="Target deployment environment"),
        custom_scopes: str = Field(
            default="https://www.googleapis.com/auth/chat.bot",
            description="Comma-separated list of custom OAuth scopes required"
        ),
        app_name: str = Field(default="ChatBot", description="Application name"),
        app_version: str = Field(default="1.0.0", description="Application version")
    ) -> list[Message]:
        """
        Generate comprehensive setup guide for Google Chat applications with platform-specific
        deployment instructions and advanced configuration options.
        """
        
        request_id = context.request_id
        services_list = ", ".join(required_services)
        scopes_list = "\n".join([f"- {scope}" for scope in custom_scopes])
        
        setup_messages = [
            Message(
                role="assistant",
                content=TextContent(text=f"""
# Google Chat App Setup Guide
*Request ID: {request_id}*

## Project Configuration
- **App Name**: {app_configuration.get('name', 'ChatBot')}
- **Version**: {app_configuration.get('version', '1.0.0')}
- **Environment**: {environment.value.title()}
- **Deployment Target**: {deployment_target.value.replace('_', ' ').title()}

## Prerequisites
1. Google Cloud Project with billing enabled
2. Google Chat API enabled
3. Service account with appropriate permissions
4. Development environment set up

## Required Services
{services_list}

## OAuth Scopes
{scopes_list}

## Authentication Setup ({authentication_type.value.replace('_', ' ').title()})
""")
            ),
            Message(
                role="assistant", 
                content=TextContent(text=f"""
## Step-by-Step Setup

### 1. Enable Google Chat API
```bash
gcloud services enable chat.googleapis.com
gcloud services enable drive.googleapis.com  # If Drive integration needed
```

### 2. Create Service Account
```bash
gcloud iam service-accounts create chat-bot-service \\
    --display-name="Chat Bot Service Account"
    
gcloud iam service-accounts keys create service-account-key.json \\
    --iam-account=chat-bot-service@PROJECT_ID.iam.gserviceaccount.com
```

### 3. Deploy to {deployment_target.value.replace('_', ' ').title()}
""")
            ),
            Message(
                role="assistant",
                content=TextContent(text=f"""
## Platform-Specific Deployment

### {deployment_target.value.replace('_', ' ').title()} Configuration

```yaml
# app.yaml or cloudbuild.yaml
service: {app_configuration.get('name', 'chatbot').lower()}
runtime: python39
env_variables:
  GOOGLE_APPLICATION_CREDENTIALS: service-account-key.json
  ENVIRONMENT: {environment.value}
  MONITORING_ENABLED: {str(enable_monitoring).lower()}

automatic_scaling:
  min_instances: 1
  max_instances: 10
```

## Monitoring Setup
{'Enabled' if enable_monitoring else 'Disabled'}

## Security Checklist
- [ ] Service account permissions configured
- [ ] OAuth scopes properly set
- [ ] Webhook URLs secured with HTTPS
- [ ] Environment variables properly configured
- [ ] Monitoring and logging enabled

This setup guide demonstrates FastMCP's sophisticated parameter handling and multi-message responses.
""")
            )
        ]
        
        return setup_messages

    @mcp.prompt(
        name="google_chat_service_integration",
        description="Advanced Google Workspace service integration patterns with workflow automation",
        tags={"google_chat", "integration", "workflow", "automation"}
    )
    def google_chat_service_integration(
          context: Context,
        primary_service: str = Field(default="drive", description="Primary Google service to integrate"),
        secondary_services: str = Field(
            default="calendar,gmail",
            description="Comma-separated list of additional services for workflow integration"
        ),
        workflow_type: str = Field(default="collaborative", description="Type of workflow to implement"),
        automation_level: float = Field(
            default=0.6,
            ge=0.0,
            le=1.0,
            description="Automation level from 0.0 (manual) to 1.0 (fully automated)"
        ),
        enable_notifications: bool = Field(default=True, description="Enable automated notifications"),
        sync_frequency: str = Field(default="realtime", description="Synchronization frequency"),
        data_format: str = Field(default="json", description="Data format for integration"),
        trigger_events: str = Field(
            default="file_created,calendar_updated",
            description="Comma-separated list of events that trigger workflow actions"
        ),
      
    ) -> PromptMessage:
        """
        Generate advanced integration patterns for Google Workspace services with
        automated workflow capabilities and real-time synchronization.
        """
        
        request_id = context.request_id
        secondary_list = ", ".join(secondary_services)
        triggers_list = ", ".join(trigger_events)
        automation_desc = "manual" if automation_level < 0.3 else "semi-automated" if automation_level < 0.7 else "fully automated"
        
        integration_guide = f"""
# Advanced Google Workspace Service Integration
*Request ID: {request_id}*

## Integration Overview
- **Primary Service**: {primary_service.value.title()}
- **Secondary Services**: {secondary_list}
- **Workflow Type**: {workflow_type.value.replace('_', ' ').title()}
- **Automation Level**: {automation_desc} ({automation_level:.2f})

## Configuration Settings
{chr(10).join([f"- **{k.replace('_', ' ').title()}**: {v}" for k, v in integration_settings.items()])}

## Trigger Events
{triggers_list}

## Implementation Architecture

### Service Integration Pattern
```python
class GoogleWorkspaceIntegrator:
    def __init__(self, primary_service="{primary_service.value}"):
        self.primary = self.get_service(primary_service)
        self.secondary_services = {{
            {chr(10).join([f'            "{service}": self.get_service("{service}"),' for service in secondary_services])}
        }}
        self.workflow_type = "{workflow_type.value}"
        self.automation_level = {automation_level}
    
    def setup_workflow(self):
        workflow_config = {{
            "triggers": {trigger_events},
            "actions": self.get_workflow_actions(),
            "notifications": {str(enable_notifications).lower()}
        }}
        return workflow_config
```

### Workflow Implementation

#### {workflow_type.value.replace('_', ' ').title()} Workflow
```python
async def handle_workflow_event(event_type, event_data):
    if event_type in {trigger_events}:
        # Primary service action
        result = await process_primary_action(event_data)
        
        # Secondary service updates
        for service in {secondary_services}:
            await sync_with_service(service, result)
        
        # Notification handling
        if {str(enable_notifications).lower()}:
            await send_chat_notification(result)
    
    return result
```

## Advanced Features

### Real-time Synchronization
- **Sync Frequency**: {integration_settings.get('sync_frequency', 'realtime')}
- **Data Format**: {integration_settings.get('data_format', 'json')}
- **Conflict Resolution**: Automatic with rollback capability

### Automation Capabilities
- **Level**: {automation_desc} ({automation_level:.2f})
- **Smart Triggers**: Event-based activation
- **Workflow Orchestration**: Multi-service coordination
- **Error Handling**: Automatic retry with exponential backoff

### Security & Compliance
- OAuth 2.0 with service account delegation
- Data encryption in transit and at rest
- Audit logging for all operations
- GDPR compliance for data handling

## Deployment Considerations

### Performance Optimization
- Connection pooling for API calls
- Caching strategies for frequently accessed data
- Rate limiting and quota management
- Asynchronous processing for long-running operations

### Monitoring & Alerting
- Service health checks
- Performance metrics tracking
- Error rate monitoring
- Custom alerting rules

This integration pattern showcases FastMCP's advanced typing system and complex parameter handling capabilities.
"""
        
        return PromptMessage(
            content=TextContent(text=integration_guide),
            role="assistant"
        )

    @mcp.prompt(
        name="google_chat_deployment_guide",
        description="Production deployment guide with monitoring, scaling, and security best practices",
        tags={"google_chat", "deployment", "production", "monitoring", "security"}
    )
    def google_chat_deployment_guide(
        context: Context,
        deployment_target: str = Field(default="cloud_run", description="Target deployment platform"),
        environment: str = Field(default="production", description="Deployment environment"),
        monitoring_level: str = Field(default="comprehensive", description="Level of monitoring to implement"),
        enable_auto_scaling: bool = Field(default=True, description="Enable automatic scaling based on load"),
        security_features: str = Field(
            default="oauth,encryption,audit_logging",
            description="Comma-separated list of security features to enable"
        ),
        max_instances: str = Field(default="50", description="Maximum number of instances"),
        memory: str = Field(default="2Gi", description="Memory allocation per instance"),
        cpu: str = Field(default="1000m", description="CPU allocation per instance"),
        backup_strategy: str = Field(
            default="automated,cross_region",
            description="Comma-separated list of backup and disaster recovery strategies"
        ),
        compliance_requirements: bool = Field(default=True, description="Enable compliance features (GDPR, SOC2, etc.)")
    ) -> list[Message]:
        """
        Generate comprehensive production deployment guide with enterprise-grade
        monitoring, security, and scaling configurations.
        """
        
        request_id = context.request_id
        security_list = ", ".join(security_features)
        backup_list = ", ".join(backup_strategy)
        
        deployment_messages = [
            Message(
                role="assistant",
                content=TextContent(text=f"""
# Production Deployment Guide
*Request ID: {request_id}*

## Deployment Configuration
- **Platform**: {deployment_target.value.replace('_', ' ').title()}
- **Environment**: {environment.value.title()}
- **Monitoring**: {monitoring_level.value.title()}
- **Auto Scaling**: {'Enabled' if enable_auto_scaling else 'Disabled'}

## Resource Allocation
{chr(10).join([f"- **{k.replace('_', ' ').title()}**: {v}" for k, v in performance_settings.items()])}

## Security Features
{security_list}

## Backup Strategy
{backup_list}

## Compliance
{'Enabled (GDPR, SOC2, HIPAA compatible)' if compliance_requirements else 'Basic compliance only'}
""")
            ),
            Message(
                role="assistant",
                content=TextContent(text=f"""
## Infrastructure as Code

### {deployment_target.value.replace('_', ' ').title()} Configuration
```yaml
# deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: google-chat-app
  labels:
    app: google-chat-app
    environment: {environment.value}
spec:
  replicas: {3 if enable_auto_scaling else 1}
  selector:
    matchLabels:
      app: google-chat-app
  template:
    metadata:
      labels:
        app: google-chat-app
    spec:
      containers:
      - name: chat-app
        image: gcr.io/PROJECT_ID/chat-app:latest
        ports:
        - containerPort: 8080
        resources:
          requests:
            memory: "{performance_settings.get('memory', '1Gi')}"
            cpu: "{performance_settings.get('cpu', '500m')}"
          limits:
            memory: "{performance_settings.get('memory', '1Gi')}"
            cpu: "{performance_settings.get('cpu', '500m')}"
        env:
        - name: ENVIRONMENT
          value: "{environment.value}"
        - name: MONITORING_LEVEL
          value: "{monitoring_level.value}"
```

### Auto Scaling Configuration
```yaml
# hpa.yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: google-chat-app-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: google-chat-app
  minReplicas: 1
  maxReplicas: {performance_settings.get('max_instances', '10')}
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
```
""")
            ),
            Message(
                role="assistant",
                content=TextContent(text=f"""
## Monitoring and Observability

### {monitoring_level.value.title()} Monitoring Setup
```yaml
# monitoring.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: monitoring-config
data:
  config.yaml: |
    monitoring:
      level: {monitoring_level.value}
      metrics:
        - response_time
        - error_rate
        - throughput
        - resource_utilization
      alerting:
        enabled: true
        channels:
          - slack
          - email
          - pagerduty
      dashboards:
        - application_health
        - business_metrics
        - infrastructure_metrics
```

### Security Configuration
```yaml
# security.yaml
apiVersion: v1
kind: Secret
metadata:
  name: security-config
type: Opaque
data:
  oauth_client_secret: <base64-encoded-secret>
  encryption_key: <base64-encoded-key>
  audit_webhook_url: <base64-encoded-url>
```

## Deployment Checklist

### Pre-deployment
- [ ] Infrastructure provisioned
- [ ] Security policies configured
- [ ] Monitoring stack deployed
- [ ] Backup systems tested
- [ ] Load testing completed

### Deployment
- [ ] Blue-green deployment strategy
- [ ] Database migrations applied
- [ ] Configuration validated
- [ ] Health checks passing
- [ ] Security scans completed

### Post-deployment
- [ ] Monitoring alerts configured
- [ ] Performance baselines established
- [ ] Backup schedules active
- [ ] Compliance reports generated
- [ ] Documentation updated

This deployment guide demonstrates FastMCP's ability to handle complex enterprise configurations with sophisticated parameter validation.
""")
            )
        ]
        
        return deployment_messages

    @mcp.prompt(
        name="google_chat_examples_showcase",
        description="Showcase of advanced Google Chat examples with different use cases and implementation patterns",
        tags={"google_chat", "examples", "showcase", "patterns", "use_cases"}
    )
    def google_chat_examples_showcase(
        context: Context,
        use_case_category: str = Field(default="business_workflow", description="Category of use case to showcase"),
        example_category: str = Field(default="interactive_cards", description="Type of examples to generate"),
        complexity_level: str = Field(default="advanced", description="Complexity level of examples"),
        include_code_samples: bool = Field(default=True, description="Include complete code implementations"),
        integration_services: str = Field(
            default="drive,calendar,sheets",
            description="Comma-separated list of services to integrate in examples"
        ),
        example_count: float = Field(
            default=3.0,
            ge=1.0,
            le=10.0,
            description="Number of examples to generate (1.0 to 10.0)"
        ),
        theme: str = Field(default="corporate", description="UI theme for examples"),
        branding: str = Field(default="enabled", description="Branding options"),
        target_audience: str = Field(
            default="developers,business_users",
            description="Comma-separated list of target audience for examples"
        )
    ) -> PromptMessage:
        """
        Generate comprehensive showcase of Google Chat examples with different use cases,
        implementation patterns, and complexity levels for various audiences.
        """
        
        request_id = context.request_id
        # Handle string parameters - split if comma-separated, otherwise use as-is
        services_list = [s.strip() for s in integration_services.split(',')] if isinstance(integration_services, str) else integration_services
        services_text = ", ".join(services_list)
        
        audience_list = [s.strip() for s in target_audience.split(',')] if isinstance(target_audience, str) else target_audience
        audience_text = ", ".join(audience_list)
        
        example_count_int = int(example_count)
        
        examples_content = f"""
# Google Chat Examples Showcase
*Request ID: {request_id}*

## Showcase Configuration
- **Use Case**: {use_case_category.replace('_', ' ').title()}
- **Example Type**: {example_category.replace('_', ' ').title()}
- **Complexity**: {complexity_level.title()}
- **Example Count**: {example_count_int}
- **Target Audience**: {audience_text}

## Integration Services
{services_text}

## Customization Settings
- **Theme**: {theme}
- **Branding**: {branding}

## Example Collection

### {use_case_category.replace('_', ' ').title()} Examples

#### Example 1: Advanced Approval Workflow Card
```python
def create_approval_workflow_card(request_data):
    return {{
        "header": {{
            "title": "Approval Request",
            "subtitle": f"Request ID: {{request_data['id']}}",
            "imageUrl": "https://example.com/approval-icon.png"
        }},
        "sections": [
            {{
                "header": "Request Details",
                "widgets": [
                    {{
                        "keyValue": {{
                            "topLabel": "Requester",
                            "content": request_data['requester'],
                            "icon": "PERSON"
                        }}
                    }},
                    {{
                        "keyValue": {{
                            "topLabel": "Amount",
                            "content": f"${{request_data['amount']:,.2f}}",
                            "icon": "DOLLAR"
                        }}
                    }},
                    {{
                        "keyValue": {{
                            "topLabel": "Priority",
                            "content": request_data['priority'],
                            "icon": "STAR"
                        }}
                    }}
                ]
            }},
            {{
                "header": "Actions",
                "widgets": [
                    {{
                        "buttons": [
                            {{
                                "textButton": {{
                                    "text": "Approve",
                                    "onClick": {{
                                        "action": {{
                                            "actionMethodName": "approve_request",
                                            "parameters": [
                                                {{"key": "request_id", "value": request_data['id']}},
                                                {{"key": "action", "value": "approve"}}
                                            ]
                                        }}
                                    }}
                                }}
                            }},
                            {{
                                "textButton": {{
                                    "text": "Reject",
                                    "onClick": {{
                                        "action": {{
                                            "actionMethodName": "reject_request",
                                            "parameters": [
                                                {{"key": "request_id", "value": request_data['id']}},
                                                {{"key": "action", "value": "reject"}}
                                            ]
                                        }}
                                    }}
                                }}
                            }},
                            {{
                                "textButton": {{
                                    "text": "Request More Info",
                                    "onClick": {{
                                        "action": {{
                                            "actionMethodName": "request_info",
                                            "parameters": [
                                                {{"key": "request_id", "value": request_data['id']}}
                                            ]
                                        }}
                                    }}
                                }}
                            }}
                        ]
                    }}
                ]
            }}
        ]
    }}
```

#### Example 2: Real-time Dashboard Integration
```python
async def create_dashboard_card(service_integrations):
    # Integrate with {services_text}
    drive_data = await get_drive_metrics()
    calendar_data = await get_calendar_summary()
    
    return {{
        "header": {{
            "title": "Team Dashboard",
            "subtitle": f"Updated: {{datetime.now().strftime('%Y-%m-%d %H:%M')}}",
            "imageUrl": "https://example.com/dashboard-icon.png"
        }},
        "sections": [
            {{
                "header": "Key Metrics",
                "widgets": [
                    {{
                        "keyValue": {{
                            "topLabel": "Active Projects",
                            "content": str(drive_data['active_projects']),
                            "icon": "DESCRIPTION"
                        }}
                    }},
                    {{
                        "keyValue": {{
                            "topLabel": "Meetings Today",
                            "content": str(calendar_data['meetings_today']),
                            "icon": "EVENT"
                        }}
                    }},
                    {{
                        "keyValue": {{
                            "topLabel": "Completion Rate",
                            "content": f"{{drive_data['completion_rate']}}%",
                            "icon": "STAR"
                        }}
                    }}
                ]
            }},
            {{
                "header": "Quick Actions",
                "widgets": [
                    {{
                        "buttons": [
                            {{
                                "textButton": {{
                                    "text": "Create Project",
                                    "onClick": {{
                                        "openLink": {{
                                            "url": "https://drive.google.com/drive/folders/new"
                                        }}
                                    }}
                                }}
                            }},
                            {{
                                "textButton": {{
                                    "text": "Schedule Meeting",
                                    "onClick": {{
                                        "openLink": {{
                                            "url": "https://calendar.google.com/calendar/render?action=TEMPLATE"
                                        }}
                                    }}
                                }}
                            }}
                        ]
                    }}
                ]
            }}
        ]
    }}
```

#### Example 3: Interactive Form Builder
```python
def create_form_card(form_config):
    return {{
        "header": {{
            "title": form_config['title'],
            "subtitle": f"Form ID: {{form_config['id']}}",
            "imageUrl": "https://example.com/form-icon.png"
        }},
        "sections": [
            {{
                "header": "Form Fields",
                "widgets": [
                    {{
                        "textInput": {{
                            "name": "user_name",
                            "label": "Name",
                            "type": "SINGLE_LINE",
                            "hintText": "Enter your full name"
                        }}
                    }},
                    {{
                        "textInput": {{
                            "name": "user_email",
                            "label": "Email",
                            "type": "SINGLE_LINE",
                            "hintText": "Enter your email address"
                        }}
                    }},
                    {{
                        "selectionInput": {{
                            "name": "priority",
                            "label": "Priority",
                            "type": "DROPDOWN",
                            "items": [
                                {{"text": "Low", "value": "low"}},
                                {{"text": "Medium", "value": "medium"}},
                                {{"text": "High", "value": "high"}}
                            ]
                        }}
                    }}
                ]
            }},
            {{
                "header": "Actions",
                "widgets": [
                    {{
                        "buttons": [
                            {{
                                "textButton": {{
                                    "text": "Submit",
                                    "onClick": {{
                                        "action": {{
                                            "actionMethodName": "submit_form",
                                            "parameters": [
                                                {{"key": "form_id", "value": form_config['id']}}
                                            ]
                                        }}
                                    }}
                                }}
                            }},
                            {{
                                "textButton": {{
                                    "text": "Save Draft",
                                    "onClick": {{
                                        "action": {{
                                            "actionMethodName": "save_draft",
                                            "parameters": [
                                                {{"key": "form_id", "value": form_config['id']}}
                                            ]
                                        }}
                                    }}
                                }}
                            }}
                        ]
                    }}
                ]
            }}
        ]
    }}
```

## Implementation Patterns

### Pattern 1: Event-Driven Architecture
- Webhook-based event handling
- Asynchronous processing
- Real-time updates

### Pattern 2: Service Integration
- OAuth 2.0 authentication
- API rate limiting
- Error handling and retry logic

### Pattern 3: User Experience
- Progressive disclosure
- Context-aware responses
- Accessibility compliance

## Best Practices

### Code Organization
- Modular card components
- Reusable action handlers
- Configuration-driven UI

### Performance Optimization
- Lazy loading of data
- Caching strategies
- Efficient API calls

### Security Considerations
- Input validation
- Authorization checks
- Audit logging

This showcase demonstrates FastMCP's sophisticated parameter handling with complex types, constraints, and validation rules.
"""
        
        return PromptMessage(
            content=TextContent(text=examples_content),
            role="assistant"
        )