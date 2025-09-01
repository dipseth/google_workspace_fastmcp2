# Context Migration Strategy: ContextVar to FastMCP Context

## Executive Summary
This document outlines the migration strategy from Python's `contextvars.ContextVar` to FastMCP's built-in `Context` system. The migration will unify context management, improve type safety, and leverage FastMCP's native capabilities.

## Current State Analysis

### Current Implementation
- **Location**: `auth/context.py`
- **Technology**: Python's `contextvars.ContextVar`
- **Key Variables**:
  - `_session_context`: Stores session ID
  - `_user_email_context`: Stores user email
  - `_service_requests_context`: Stores pending Google service requests

### Current Usage Pattern
```python
from contextvars import ContextVar

_session_context: ContextVar[Optional[str]] = ContextVar("session_context", default=None)
_user_email_context: ContextVar[Optional[str]] = ContextVar("user_email_context", default=None)
```

### Dependencies
1. **Middleware** (`auth/middleware.py`):
   - Sets/clears session context
   - Manages user email context
   - Handles service injection

2. **Service Manager** (`auth/service_manager.py`):
   - Reads session context for service creation

3. **Resources** (various files):
   - Access context variables for user/session info

## Target State with FastMCP Context

### FastMCP Context Advantages
1. **Native Integration**: Built into FastMCP framework
2. **Type Safety**: Better type hints and validation
3. **State Management**: Built-in state dictionary for data sharing
4. **Async Support**: Native async/await support
5. **Middleware Integration**: Seamless middleware support

### New Implementation Pattern
```python
from fastmcp import Context

# In tools/resources
async def my_tool(user_google_email: str, ctx: Context) -> str:
    # Access state
    session_id = ctx.get_state("session_id")
    
    # Set state
    ctx.set_state("user_email", user_google_email)
    
    # Use logging
    await ctx.info(f"Processing for {user_google_email}")
```

## Migration Strategy

### Phase 1: Create Compatibility Layer
**Goal**: Create an adapter that bridges ContextVar and FastMCP Context

1. Create `auth/context_adapter.py`:
   - Wrapper functions that work with both systems
   - Maintain backward compatibility
   - Gradual migration support

2. Key Functions:
   ```python
   # Get context (works with both systems)
   def get_context_value(key: str, ctx: Context = None) -> Any
   
   # Set context (works with both systems)  
   def set_context_value(key: str, value: Any, ctx: Context = None) -> None
   ```

### Phase 2: Update Middleware
**Goal**: Modify middleware to use FastMCP Context's state management

1. Update `AuthMiddleware` to:
   - Store session/user data in FastMCP Context state
   - Maintain ContextVar for backward compatibility (temporary)
   - Use `context.fastmcp_context.set_state()` for new code

2. Migration approach:
   ```python
   # In middleware
   async def on_call_tool(self, context: MiddlewareContext, call_next):
       # New way - FastMCP Context
       if hasattr(context, 'fastmcp_context'):
           context.fastmcp_context.set_state("session_id", session_id)
           context.fastmcp_context.set_state("user_email", user_email)
       
       # Old way - keep for compatibility
       set_session_context(session_id)
       set_user_email_context(user_email)
   ```

### Phase 3: Migrate Tools and Resources
**Goal**: Update all tools/resources to use FastMCP Context

1. Update function signatures:
   ```python
   # Before
   async def search_gmail_messages(user_google_email: str, query: str) -> str:
       # No context access
   
   # After
   async def search_gmail_messages(user_google_email: str, query: str, ctx: Context) -> str:
       session_id = ctx.get_state("session_id")
       await ctx.info(f"Searching Gmail for {user_google_email}")
   ```

2. Priority order:
   - Start with new tools/resources
   - Update frequently used tools
   - Migrate read-only tools first
   - Handle write operations last

### Phase 4: Service Injection Update
**Goal**: Modernize service injection to use FastMCP Context

1. Update service request mechanism:
   ```python
   # Instead of ContextVar storage
   # Use FastMCP Context state
   ctx.set_state("service_requests", {
       "drive": {"status": "pending", "scopes": [...]}
   })
   ```

2. Benefits:
   - Scoped to request lifecycle
   - Automatic cleanup
   - Better debugging

### Phase 5: Remove Legacy Code
**Goal**: Clean up ContextVar implementation

1. Remove from `auth/context.py`:
   - ContextVar declarations
   - Legacy get/set functions
   - Thread-safe storage (if replaced)

2. Update imports across codebase

## Implementation Plan

### Week 1: Preparation
- [x] Analyze current usage
- [x] Document migration strategy
- [ ] Create context_adapter.py
- [ ] Add unit tests for adapter

### Week 2: Middleware Update
- [ ] Update AuthMiddleware for dual support
- [ ] Test middleware with both systems
- [ ] Add logging for migration tracking

### Week 3: Tool Migration
- [ ] Migrate Gmail tools
- [ ] Migrate Drive tools
- [ ] Migrate resource handlers
- [ ] Update other services

### Week 4: Cleanup
- [ ] Remove ContextVar usage
- [ ] Update documentation
- [ ] Performance testing
- [ ] Final validation

## Risk Mitigation

### Risks and Mitigations

1. **Breaking Changes**
   - Risk: Existing tools stop working
   - Mitigation: Dual support during migration

2. **Session Loss**
   - Risk: Active sessions lost during migration
   - Mitigation: Graceful fallback to ContextVar

3. **Performance Impact**
   - Risk: FastMCP Context slower than ContextVar
   - Mitigation: Benchmark before full migration

4. **Middleware Compatibility**
   - Risk: Custom middleware breaks
   - Mitigation: Compatibility layer

## Testing Strategy

### Unit Tests
```python
# Test dual context support
async def test_context_compatibility():
    # Test ContextVar path
    set_session_context("test-session")
    assert get_session_context() == "test-session"
    
    # Test FastMCP Context path
    ctx = Context()
    ctx.set_state("session_id", "test-session")
    assert ctx.get_state("session_id") == "test-session"
```

### Integration Tests
1. Test middleware with both context systems
2. Verify service injection works
3. Test session persistence
4. Validate cleanup behavior

### Migration Validation
- Monitor logs for deprecation warnings
- Track context usage patterns
- Measure performance metrics
- Validate no data loss

## Success Metrics

1. **Functional**:
   - All tools work with FastMCP Context
   - No ContextVar imports remain
   - Tests pass 100%

2. **Performance**:
   - No degradation in response time
   - Memory usage stable or improved
   - Context access < 1ms

3. **Code Quality**:
   - Reduced complexity
   - Better type safety
   - Improved testability

## Rollback Plan

If issues arise:
1. Keep ContextVar implementation in git history
2. Compatibility layer allows quick revert
3. Feature flag for context system selection
4. Gradual rollback per service if needed

## Appendix: Code Examples

### Example 1: Context Adapter
```python
# auth/context_adapter.py
from typing_extensions import Any, Optional
from fastmcp import Context
from .context import get_session_context, set_session_context

def get_adaptive_context(key: str, ctx: Optional[Context] = None) -> Any:
    """Get context value from FastMCP or ContextVar."""
    if ctx:
        return ctx.get_state(key)
    elif key == "session_id":
        return get_session_context()
    # ... handle other keys
```

### Example 2: Migrated Tool
```python
@mcp.tool
async def process_data(data: str, ctx: Context) -> str:
    """Tool using FastMCP Context."""
    # Get session from context
    session_id = ctx.get_state("session_id")
    user_email = ctx.get_state("user_email")
    
    # Log progress
    await ctx.info(f"Processing for {user_email}")
    
    # Use injected services
    drive_service = ctx.get_state("services", {}).get("drive")
    
    return f"Processed in session {session_id}"
```

### Example 3: Middleware Update
```python
class AuthMiddleware(Middleware):
    async def on_call_tool(self, context: MiddlewareContext, call_next):
        # Store in FastMCP Context
        if hasattr(context, 'fastmcp_context'):
            fc = context.fastmcp_context
            fc.set_state("session_id", session_id)
            fc.set_state("user_email", user_email)
            fc.set_state("services", {})
        
        return await call_next()
```

## Conclusion

This migration will modernize our context management system, leveraging FastMCP's native capabilities while maintaining backward compatibility during the transition. The phased approach minimizes risk and allows for gradual validation of each component.

Total estimated effort: 4 weeks
Risk level: Medium (mitigated by compatibility layer)
Expected benefits: Improved maintainability, better performance, native framework integration