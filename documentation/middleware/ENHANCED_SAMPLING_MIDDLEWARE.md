# Enhanced Sampling Middleware for FastMCP2 Google Workspace Platform

## Overview

The Enhanced Sampling Middleware extends the base sampling capabilities by making the client LLM **resource-aware** and **context-intelligent**. Instead of generic sampling, this middleware dynamically enriches sampling requests with relevant data from the FastMCP2 platform's extensive resource ecosystem, Qdrant knowledge base, and template system.

## 🎯 Core Philosophy

**"Make the LLM smart about what's available"** - The middleware transforms sampling from simple text generation to **contextually-aware assistance** that understands:

- What resources are available (user data, Gmail, Drive, etc.)
- What tools can be used for follow-up actions
- Historical patterns from previous tool responses (via Qdrant)
- Current user context and preferences

## 🚀 Key Enhancements Over Base Sampling

### 1. **Resource-Aware Prompting**
Instead of basic prompts, inject available resource information to guide the LLM:

```python
# Before (Generic)
prompt = "Analyze this text: {text}"

# After (Resource-Aware)
prompt = """
Available Resources: {resource_summary}
User Context: {user_context}
Recent Activity: {recent_workspace_activity}

Now analyze this text with awareness of the user's context: {text}

Consider suggesting relevant actions using available tools like:
- Gmail operations (labels: {gmail_labels})
- Drive file management
- Workspace search and organization
"""
```

### 2. **Qdrant-Enhanced Context**
Dynamically pull relevant historical data from Qdrant to inform sampling:

```python
# Search Qdrant for related previous responses
related_responses = await qdrant_search(
    query=f"user:{user_email} similar_task", 
    limit=3
)

# Enrich sampling with historical context
enhanced_prompt = f"""
Historical Context (from previous similar tasks):
{format_qdrant_responses(related_responses)}

Current Task: {original_prompt}
"""
```

### 3. **Template-Powered Dynamic Prompts**
Use the Template Parameter Middleware to create context-aware prompts:

```python
# Template-enhanced sampling prompt
template_prompt = """
Hello {{user://current/email.name}}!

Based on your profile and recent activity:
- Email: {{user://current/email.email}}
- Recent files: {{workspace://content/recent.total_files}}
- Gmail labels: {{service://gmail/labels | length}}

{% if workspace://content/recent.total_files > 10 %}
I notice you have quite a few recent files. 
{% endif %}

Now, regarding your request: {user_request}

I can help you with actions like:
{% for tool in tools://enhanced/list.enhanced_tools[:5] %}
- {{tool.name}}: {{tool.description}}
{% endfor %}
"""
```

## 📚 Available Resource Categories for Sampling Enhancement

### User & Authentication Context
```python
SAMPLING_RESOURCES = {
    "user_context": [
        "user://current/email",           # Current user email and name
        "user://current/profile",         # Full user profile with auth status
        "auth://session/current"          # Current session information
    ],
    
    "workspace_context": [
        "workspace://content/recent",     # Recent workspace activity
        "workspace://content/search/{query}"  # Dynamic search results
    ],
    
    "gmail_context": [
        "service://gmail/labels",         # Available Gmail labels
        "service://gmail/filters",        # Current filter rules
        "gmail://messages/recent"         # Recent messages
    ],
    
    "tools_context": [
        "tools://list/all",              # All available tools
        "tools://enhanced/list",         # Enhanced tools collection
        "tools://usage/guide"            # Usage patterns and guides
    ],
    
    "qdrant_context": [
        "qdrant://search/{query}",       # Semantic search across history
        "qdrant://collections/list"      # Available knowledge collections
    ]
}
```

## 🔧 Enhanced Sampling Templates

### 1. **Context-Aware Analysis Template**
```python
CONTEXT_AWARE_ANALYSIS = {
    "system_prompt": """
You are an intelligent assistant with access to the user's Google Workspace data and tools.

Available Resources:
- User Profile: {{user://current/profile}}
- Recent Workspace Activity: {{workspace://content/recent}}  
- Gmail Organization: {{service://gmail/labels}}
- Available Tools: {{tools://enhanced/list}}

When analyzing requests, consider:
1. The user's current context and recent activity
2. What tools/resources could help achieve their goals
3. Relevant patterns from their workspace usage
4. Actionable next steps using available capabilities

Always be specific about available tools and resources that could help.
""",
    "temperature": 0.3,
    "max_tokens": 600,
    "include_context": "thisServer"
}
```

### 2. **Smart Workflow Suggestion Template**
```python
WORKFLOW_SUGGESTION = {
    "system_prompt": """
You are a workflow optimization expert with access to:

User Context:
- Email: {{user://current/email.email}}
- Recent Files: {{workspace://content/recent.content_summary}}
- Gmail Setup: {{service://gmail/labels}}

Historical Patterns: [Dynamically injected from Qdrant]
Available Tools: [Dynamically injected from tools resources]

When suggesting workflows:
1. Reference specific available tools by name
2. Use actual user data (file counts, label names, etc.)
3. Suggest realistic automation using FastMCP capabilities
4. Consider user's historical patterns and preferences
""",
    "temperature": 0.4,
    "max_tokens": 800
}
```

### 3. **Historical Pattern-Aware Template**
```python
PATTERN_AWARE = {
    "system_prompt": """
You have access to the user's historical interaction patterns via Qdrant search.

Before responding, I will search for related previous responses using:
{{qdrant://search/similar_request}}

This gives you context about:
- How similar requests were handled before
- What tools were successful
- User preferences and patterns
- Common follow-up actions

Use this historical context to provide more relevant and personalized assistance.
""",
    "temperature": 0.2,
    "max_tokens": 700
}
```

## 🎨 Implementation Architecture

### Core Components

#### 1. **ContextEnrichedSamplingContext**
```python
class ContextEnrichedSamplingContext(SamplingContext):
    """Enhanced sampling context with resource awareness."""
    
    def __init__(self, fastmcp_context, tool_name, resource_manager, qdrant_middleware, template_middleware):
        super().__init__(fastmcp_context, tool_name)
        self.resource_manager = resource_manager
        self.qdrant_middleware = qdrant_middleware  
        self.template_middleware = template_middleware
        
    async def enhanced_sample(
        self,
        messages: str,
        enhancement_level: str = "basic",  # basic, contextual, historical
        relevant_resources: List[str] = None,
        include_historical: bool = True,
        **kwargs
    ):
        """Enhanced sampling with resource awareness and historical context."""
        
        # 1. Gather relevant resource data
        resource_context = await self._gather_resource_context(relevant_resources)
        
        # 2. Search for historical patterns if requested
        historical_context = ""
        if include_historical:
            historical_context = await self._get_historical_context(messages)
        
        # 3. Build enhanced prompt using templates
        enhanced_prompt = await self._build_enhanced_prompt(
            original_message=messages,
            resource_context=resource_context,
            historical_context=historical_context,
            enhancement_level=enhancement_level
        )
        
        # 4. Perform sampling with enriched context
        return await super().sample(enhanced_prompt, **kwargs)
```

#### 2. **ResourceContextManager**
```python
class ResourceContextManager:
    """Manages dynamic resource context for sampling enhancement."""
    
    async def get_user_context_summary(self, user_email: str) -> Dict[str, Any]:
        """Get comprehensive user context for sampling."""
        return {
            "profile": await self.get_resource("user://current/profile"),
            "recent_activity": await self.get_resource("workspace://content/recent"),
            "gmail_setup": await self.get_resource("service://gmail/labels"),
            "available_tools": await self.get_resource("tools://enhanced/list")
        }
    
    async def get_relevant_resources_for_task(self, task_description: str) -> List[str]:
        """Intelligently determine which resources are relevant for a task."""
        # Use keyword matching and ML to suggest relevant resources
        # e.g., if task mentions "email" -> include Gmail resources
        # if task mentions "files" -> include Drive resources
        pass
```

#### 3. **QdrantHistoryEnhancer**
```python
class QdrantHistoryEnhancer:
    """Enhances sampling with historical context from Qdrant."""
    
    async def get_relevant_history(
        self, 
        user_email: str, 
        query: str, 
        limit: int = 3
    ) -> List[Dict[str, Any]]:
        """Search Qdrant for relevant historical responses."""
        
        # Search for similar previous tool responses
        search_query = f"user_email:{user_email} {query}"
        results = await self.qdrant_middleware.search(
            query=search_query,
            limit=limit,
            score_threshold=0.7
        )
        
        return [
            {
                "tool_name": result.payload.get("tool_name"),
                "response_summary": result.payload.get("response_summary", "")[:200],
                "timestamp": result.payload.get("timestamp"),
                "success_pattern": result.payload.get("success_indicators", [])
            }
            for result in results
        ]
```

## 🔄 Sampling Enhancement Levels

### Level 1: Basic Enhancement
- Inject user profile and current session info
- Add available tools summary
- Use resource-aware templates

### Level 2: Contextual Enhancement  
- Include recent workspace activity
- Add Gmail/Drive context relevant to the task
- Suggest specific tools based on user's setup

### Level 3: Historical Enhancement
- Search Qdrant for similar previous tasks
- Include successful patterns and workflows
- Provide personalized recommendations based on history

## 📊 Example Enhanced Sampling Flow

```python
@mcp.tool
async def smart_email_assistant(
    user_request: str, 
    ctx: ContextEnrichedSamplingContext
) -> str:
    """Smart email assistant with full context awareness."""
    
    # Enhanced sampling with all context
    response = await ctx.enhanced_sample(
        messages=f"""
        User Request: {user_request}
        
        Please provide a helpful response considering:
        1. The user's Gmail setup and labels
        2. Their recent workspace activity  
        3. Available tools for follow-up actions
        4. Any relevant historical patterns
        
        Be specific about tools and resources that could help.
        """,
        template=SamplingTemplate.CONTEXT_AWARE_ANALYSIS,
        enhancement_level="historical",
        relevant_resources=[
            "service://gmail/labels",
            "workspace://content/recent", 
            "tools://enhanced/list"
        ],
        include_historical=True
    )
    
    return response.text
```

**Sample Enhanced Response:**
```
Based on your Gmail setup (I see you have 15 labels including "Work Projects" and "Client Communications") and your recent activity (42 files modified this week, mostly presentations), here's how I can help:

For your request about organizing project emails, I can:

1. **Use the 'gmail_create_filter' tool** to automatically label emails from specific projects
2. **Use the 'workspace_search_content' tool** to find related documents in your Drive
3. **Use the 'gmail_bulk_organize' tool** to batch-process existing emails

I noticed from your previous interactions that you successfully used a similar workflow 2 weeks ago for the "Marketing Campaign" project. Would you like me to apply a similar pattern here?

Available next steps:
- Create Gmail filters: `gmail_create_filter(criteria=..., label="Work Projects")`  
- Search related files: `workspace_search_content(query="project name")`
- Organize existing emails: `gmail_bulk_organize(label_strategy="by_project")`
```

## 🚀 Benefits of Enhanced Sampling

### For Users
- **Contextually relevant suggestions** based on their actual data
- **Actionable recommendations** using available tools
- **Personalized workflows** based on historical patterns
- **Smarter assistance** that understands their workspace setup

### For Developers  
- **Resource-aware LLM interactions** that leverage platform capabilities
- **Historical pattern recognition** via Qdrant integration
- **Template-powered dynamic prompts** for consistency
- **Extensible enhancement levels** for different use cases

### For the Platform
- **Better tool adoption** through intelligent suggestions
- **Improved user experience** with contextual assistance
- **Data-driven insights** from usage patterns
- **Scalable intelligence** that grows with user data

## 🔧 Implementation Roadmap

### Phase 1: Core Infrastructure
- [ ] Implement `ContextEnrichedSamplingContext`
- [ ] Create `ResourceContextManager`
- [ ] Build enhanced template system
- [ ] Add basic resource injection

### Phase 2: Historical Intelligence
- [ ] Implement `QdrantHistoryEnhancer`
- [ ] Add historical pattern search
- [ ] Create success pattern recognition
- [ ] Build personalization engine

### Phase 3: Advanced Features
- [ ] Dynamic resource relevance detection
- [ ] Multi-level enhancement system
- [ ] Workflow pattern recognition
- [ ] Smart tool recommendation engine

### Phase 4: Optimization
- [ ] Performance tuning and caching
- [ ] Enhanced template compilation
- [ ] Resource usage optimization  
- [ ] Historical data management

## 📚 Integration Points

### With Existing Middleware
- **Template Parameter Middleware**: Use for dynamic prompt construction
- **Qdrant Unified Middleware**: Access historical responses and patterns
- **Auth Middleware**: Provide user context and permissions

### With Resource System
- **User Resources**: Profile, email, session data
- **Gmail Resources**: Labels, filters, messages
- **Workspace Resources**: Files, activity, search results
- **Tools Resources**: Available capabilities and usage guides

### With Qdrant Collections
- **mcp_tool_responses**: Historical tool usage and success patterns
- **email_templates**: Pre-built email patterns and templates  
- **card_framework_components_fastembed**: UI component usage patterns

## 🎉 Example Use Cases

### 1. **Smart Email Organization**
```python
# User: "Help me organize my project emails"
# Enhanced sampling considers:
# - User's current Gmail labels (from service://gmail/labels)
# - Recent project files (from workspace://content/recent) 
# - Previous email organization patterns (from Qdrant)
# - Available email tools (from tools://enhanced/list)

# Response includes specific tool recommendations with actual user data
```

### 2. **Intelligent Workflow Suggestions**
```python
# User: "I have too many documents, help me organize them"
# Enhanced sampling considers:
# - Current file count and types (from workspace resources)
# - Previous organization strategies (from Qdrant history)
# - User's Drive folder structure preferences
# - Available file management tools

# Response provides personalized organization strategy
```

### 3. **Context-Aware Content Generation**
```python
# User: "Draft a status update email"
# Enhanced sampling considers:
# - Recent work activity and files
# - User's typical email style (from Gmail templates)
# - Available Gmail tools for sending
# - User's communication patterns

# Response creates personalized email draft with specific project details
```

This Enhanced Sampling Middleware transforms the FastMCP2 platform from a simple tool provider into an **intelligent workspace assistant** that understands user context, learns from patterns, and provides contextually-aware AI assistance powered by the full ecosystem of resources and capabilities.