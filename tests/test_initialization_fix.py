#!/usr/bin/env python3
"""
Test the initialization flow fix for QdrantUnifiedMiddleware.

This test validates that:
1. The middleware initialization properly calls the background reindexing setup
2. on_call_tool uses the correct initialization method
3. Backward compatibility is maintained
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from middleware.qdrant_middleware import QdrantUnifiedMiddleware


class TestQdrantInitializationFlow:
    """Test the corrected initialization flow in QdrantUnifiedMiddleware."""

    @pytest.fixture
    def mock_middleware(self):
        """Create a QdrantUnifiedMiddleware with mocked dependencies."""
        with patch('middleware.qdrant_middleware.QdrantClientManager') as mock_client_manager_class, \
             patch('middleware.qdrant_middleware.QdrantStorageManager') as mock_storage_manager_class, \
             patch('middleware.qdrant_middleware.QdrantSearchManager') as mock_search_manager_class, \
             patch('middleware.qdrant_middleware.QdrantResourceHandler') as mock_resource_handler_class:
            
            # Create mock instances
            mock_client_manager = AsyncMock()
            mock_client_manager.is_initialized = False
            mock_client_manager.is_available = True
            mock_client_manager.initialize.return_value = True
            mock_client_manager_class.return_value = mock_client_manager
            
            mock_storage_manager = AsyncMock()
            mock_storage_manager_class.return_value = mock_storage_manager
            
            mock_search_manager = AsyncMock()
            mock_search_manager_class.return_value = mock_search_manager
            
            mock_resource_handler = AsyncMock()
            mock_resource_handler_class.return_value = mock_resource_handler
            
            # Create middleware
            middleware = QdrantUnifiedMiddleware(
                qdrant_host="localhost",
                qdrant_port=6333,
                enabled=True
            )
            
            # Store references to mocks for test access
            middleware._mock_client_manager = mock_client_manager
            middleware._mock_storage_manager = mock_storage_manager
            
            return middleware

    @pytest.mark.asyncio
    async def test_initialize_middleware_and_reindexing_calls_background_reindexing(self, mock_middleware):
        """Test that the new initialization method properly starts background reindexing."""
        with patch.object(mock_middleware, '_start_background_reindexing', new_callable=AsyncMock) as mock_start_reindexing:
            # Call the new initialization method
            result = await mock_middleware.initialize_middleware_and_reindexing()
            
            # Verify results
            assert result is True
            assert mock_middleware._initialized is True
            mock_middleware._mock_client_manager.initialize.assert_called_once()
            mock_start_reindexing.assert_called_once()

    @pytest.mark.asyncio
    async def test_backward_compatibility_initialize_method(self, mock_middleware):
        """Test that the legacy initialize() method still works and delegates properly."""
        with patch.object(mock_middleware, 'initialize_middleware_and_reindexing', new_callable=AsyncMock) as mock_init_full:
            mock_init_full.return_value = True
            
            # Call the legacy method
            result = await mock_middleware.initialize()
            
            # Verify it delegates to the new method
            assert result is True
            mock_init_full.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_call_tool_uses_correct_initialization(self, mock_middleware):
        """Test that on_call_tool calls the middleware initialization instead of client manager directly."""
        # Mock context and call_next
        mock_context = MagicMock()
        mock_context.message.name = "test_tool"
        mock_context.message.arguments = {}
        
        mock_call_next = AsyncMock()
        mock_call_next.return_value = {"result": "success"}
        
        # Mock the initialization method
        with patch.object(mock_middleware, 'initialize_middleware_and_reindexing', new_callable=AsyncMock) as mock_init_full:
            mock_init_full.return_value = True
            
            # Mock other dependencies
            with patch('middleware.qdrant_middleware.get_session_context', return_value="test_session"), \
                 patch.object(mock_middleware.storage_manager, '_store_response_with_params', new_callable=AsyncMock):
                
                # Set client as not initialized to trigger initialization
                mock_middleware._mock_client_manager.is_initialized = False
                
                # Call on_call_tool
                result = await mock_middleware.on_call_tool(mock_context, mock_call_next)
                
                # Verify the middleware initialization was called
                mock_init_full.assert_called_once()
                
                # Verify the tool was called and response returned
                mock_call_next.assert_called_once()
                assert result == {"result": "success"}

    @pytest.mark.asyncio
    async def test_ensure_initialization_uses_correct_method(self, mock_middleware):
        """Test that _ensure_initialization calls the middleware initialization."""
        with patch.object(mock_middleware, 'initialize_middleware_and_reindexing', new_callable=AsyncMock) as mock_init_full, \
             patch('asyncio.create_task') as mock_create_task:
            
            # Set up for triggering initialization
            mock_middleware._early_init_started = False
            
            # Call _ensure_initialization
            await mock_middleware._ensure_initialization("test_context")
            
            # Verify it started the task with the correct method
            assert mock_middleware._early_init_started is True
            mock_create_task.assert_called_once()
            
            # Get the task argument and verify it's the right method
            task_arg = mock_create_task.call_args[0][0]
            # The task should be a coroutine for the middleware initialization
            assert hasattr(task_arg, '__await__')  # It's a coroutine

    def test_initialization_variables_properly_set(self, mock_middleware):
        """Test that initialization variables are properly set in __init__."""
        # Verify reindexing control variables are set
        assert hasattr(mock_middleware, '_early_init_started')
        assert hasattr(mock_middleware, '_reindexing_task')
        assert hasattr(mock_middleware, '_reindexing_enabled')
        
        assert mock_middleware._early_init_started is False
        assert mock_middleware._reindexing_task is None
        assert mock_middleware._reindexing_enabled is True

    @pytest.mark.asyncio
    async def test_reindexing_not_started_when_disabled(self, mock_middleware):
        """Test that reindexing is not started when disabled."""
        with patch.object(mock_middleware, '_start_background_reindexing', new_callable=AsyncMock) as mock_start_reindexing:
            # Disable reindexing
            mock_middleware._reindexing_enabled = False
            
            # Call initialization
            result = await mock_middleware.initialize_middleware_and_reindexing()
            
            # Verify reindexing was not started
            assert result is True
            mock_start_reindexing.assert_not_called()

    @pytest.mark.asyncio
    async def test_reindexing_not_started_on_client_init_failure(self, mock_middleware):
        """Test that reindexing is not started when client initialization fails."""
        with patch.object(mock_middleware, '_start_background_reindexing', new_callable=AsyncMock) as mock_start_reindexing:
            # Make client initialization fail
            mock_middleware._mock_client_manager.initialize.return_value = False
            
            # Call initialization
            result = await mock_middleware.initialize_middleware_and_reindexing()
            
            # Verify reindexing was not started
            assert result is False
            assert mock_middleware._initialized is False
            mock_start_reindexing.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])