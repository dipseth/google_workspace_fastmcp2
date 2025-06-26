"""Enhanced tools that use resource templating instead of manual user_google_email parameters.

This module demonstrates the new pattern for tools that automatically get the
authenticated user's email from resources instead of requiring it as a parameter.
"""

import logging
from typing import List, Optional

from fastmcp import FastMCP
from resources.user_resources import get_current_user_email_simple
from auth.context import request_google_service, get_injected_service
from auth.google_auth import get_all_stored_users

logger = logging.getLogger(__name__)


async def _detect_authenticated_user() -> Optional[str]:
    """Detect authenticated user when session context is unavailable.
    
    This fallback method tries to find a valid authenticated user
    by checking stored credentials.
    
    Returns:
        Email of authenticated user or None if none found
    """
    try:
        # Get all users with stored credentials
        stored_users = get_all_stored_users()
        
        if not stored_users:
            logger.warning("No stored users found")
            return None
            
        # For now, use the first valid user (could be enhanced to be smarter)
        from auth.google_auth import get_valid_credentials
        
        for user_email in stored_users:
            credentials = get_valid_credentials(user_email)
            if credentials and not credentials.expired:
                logger.info(f"Found valid credentials for user: {user_email}")
                return user_email
                
        # If no non-expired credentials, try the first user anyway
        # (credentials might be refreshable)
        first_user = stored_users[0]
        logger.info(f"Using first stored user as fallback: {first_user}")
        return first_user
        
    except Exception as e:
        logger.error(f"Error detecting authenticated user: {e}")
        return None


def setup_enhanced_tools(mcp: FastMCP) -> None:
    """Setup enhanced tools that use resource templating."""
    
    @mcp.tool()
    async def list_my_drive_files(
        query: str = "name contains ''",
        page_size: int = 25
    ) -> str:
        """List files in the current user's Google Drive.
        
        This enhanced tool automatically uses the authenticated user's email
        from the resource system instead of requiring it as a parameter.
        
        Args:
            query: Google Drive query string to filter files
            page_size: Number of files to return (max 100)
        
        Returns:
            JSON string containing the list of files
        """
        try:
            # Try to get user email from resource context first
            try:
                user_email = get_current_user_email_simple()
                logger.info(f"✅ Got user email from context: {user_email}")
            except ValueError:
                # Fallback: Extract email from available credentials
                logger.warning("⚠️ No user context available, attempting to detect authenticated user...")
                user_email = await _detect_authenticated_user()
                if not user_email:
                    return "❌ Authentication error: No authenticated user found in current session. Please ensure the user is authenticated with start_google_auth tool first."
            
            # Try service injection first, fallback to direct service creation
            try:
                drive_key = request_google_service("drive", ["drive_read"])
                drive_service = get_injected_service(drive_key)
                logger.info(f"✅ Using injected Drive service for {user_email}")
            except RuntimeError as e:
                if "not yet fulfilled" in str(e).lower():
                    logger.warning(f"⚠️ Middleware injection unavailable, creating direct service for {user_email}")
                    from auth.service_helpers import get_service
                    drive_service = await get_service("drive", user_email)
                else:
                    raise
            
            # Perform the Drive operation
            results = drive_service.files().list(
                q=query,
                pageSize=min(page_size, 100),
                fields="nextPageToken, files(id, name, mimeType, size, modifiedTime, webViewLink)"
            ).execute()
            
            files = results.get('files', [])
            
            response_data = {
                "user_email": user_email,
                "query": query,
                "total_files": len(files),
                "files": files,
                "next_page_token": results.get('nextPageToken')
            }
            
            return f"✅ Found {len(files)} files in Drive for {user_email}:\n\n{response_data}"
            
        except ValueError as e:
            return f"❌ Authentication error: {str(e)}"
        except Exception as e:
            logger.error(f"Error listing Drive files: {e}")
            return f"❌ Error listing Drive files: {str(e)}"
    
    @mcp.tool()
    async def search_my_gmail(
        query: str,
        max_results: int = 10
    ) -> str:
        """Search the current user's Gmail messages.
        
        Enhanced tool that automatically uses the authenticated user's email.
        
        Args:
            query: Gmail search query (e.g., "from:sender@example.com")
            max_results: Maximum number of messages to return
        
        Returns:
            JSON string containing search results
        """
        try:
            # Try to get user email from resource context first
            try:
                user_email = get_current_user_email_simple()
                logger.info(f"✅ Got user email from context: {user_email}")
            except ValueError:
                # Fallback: Extract email from available credentials
                logger.warning("⚠️ No user context available, attempting to detect authenticated user...")
                user_email = await _detect_authenticated_user()
                if not user_email:
                    return "❌ Authentication error: No authenticated user found in current session. Please ensure the user is authenticated with start_google_auth tool first."
            
            # Try service injection first, fallback to direct service creation
            try:
                gmail_key = request_google_service("gmail", ["gmail_read"])
                gmail_service = get_injected_service(gmail_key)
                logger.info(f"✅ Using injected Gmail service for {user_email}")
            except RuntimeError as e:
                if "not yet fulfilled" in str(e).lower():
                    logger.warning(f"⚠️ Middleware injection unavailable, creating direct service for {user_email}")
                    from auth.service_helpers import get_service
                    gmail_service = await get_service("gmail", user_email)
                else:
                    raise
            
            # Search Gmail
            results = gmail_service.users().messages().list(
                userId='me',
                q=query,
                maxResults=max_results
            ).execute()
            
            messages = results.get('messages', [])
            
            # Get message details
            detailed_messages = []
            for msg in messages[:max_results]:
                try:
                    message = gmail_service.users().messages().get(
                        userId='me',
                        id=msg['id'],
                        format='metadata',
                        metadataHeaders=['From', 'Subject', 'Date']
                    ).execute()
                    
                    # Extract headers
                    headers = message.get('payload', {}).get('headers', [])
                    msg_data = {
                        'id': message['id'],
                        'thread_id': message['threadId'],
                        'snippet': message.get('snippet', ''),
                    }
                    
                    # Parse headers
                    for header in headers:
                        name = header['name'].lower()
                        if name in ['from', 'subject', 'date']:
                            msg_data[name] = header['value']
                    
                    detailed_messages.append(msg_data)
                    
                except Exception as e:
                    logger.warning(f"Error getting message details for {msg['id']}: {e}")
            
            response_data = {
                "user_email": user_email,
                "query": query,
                "total_found": len(messages),
                "messages": detailed_messages
            }
            
            return f"✅ Found {len(messages)} Gmail messages for {user_email}:\n\n{response_data}"
            
        except ValueError as e:
            return f"❌ Authentication error: {str(e)}"
        except Exception as e:
            logger.error(f"Error searching Gmail: {e}")
            return f"❌ Error searching Gmail: {str(e)}"
    
    @mcp.tool()
    async def create_my_calendar_event(
        summary: str,
        start_time: str,
        end_time: str,
        description: Optional[str] = None,
        attendees: Optional[List[str]] = None,
        calendar_id: str = "primary"
    ) -> str:
        """Create a calendar event for the current user.
        
        Enhanced tool that uses resource templating for user authentication.
        
        Args:
            summary: Event title
            start_time: Start time in RFC3339 format (e.g., "2025-01-01T10:00:00Z")
            end_time: End time in RFC3339 format
            description: Optional event description
            attendees: Optional list of attendee email addresses
            calendar_id: Calendar ID (default: "primary")
        
        Returns:
            JSON string with event details
        """
        try:
            # Try to get user email from resource context first
            try:
                user_email = get_current_user_email_simple()
                logger.info(f"✅ Got user email from context: {user_email}")
            except ValueError:
                # Fallback: Extract email from available credentials
                logger.warning("⚠️ No user context available, attempting to detect authenticated user...")
                user_email = await _detect_authenticated_user()
                if not user_email:
                    return "❌ Authentication error: No authenticated user found in current session. Please ensure the user is authenticated with start_google_auth tool first."
            
            # Try service injection first, fallback to direct service creation
            try:
                calendar_key = request_google_service("calendar", ["calendar_events"])
                calendar_service = get_injected_service(calendar_key)
                logger.info(f"✅ Using injected Calendar service for {user_email}")
            except RuntimeError as e:
                if "not yet fulfilled" in str(e).lower():
                    logger.warning(f"⚠️ Middleware injection unavailable, creating direct service for {user_email}")
                    from auth.service_helpers import get_service
                    calendar_service = await get_service("calendar", user_email)
                else:
                    raise
            
            # Build event data
            event_data = {
                'summary': summary,
                'start': {'dateTime': start_time},
                'end': {'dateTime': end_time}
            }
            
            if description:
                event_data['description'] = description
            
            if attendees:
                event_data['attendees'] = [{'email': email} for email in attendees]
            
            # Create the event
            event = calendar_service.events().insert(
                calendarId=calendar_id,
                body=event_data
            ).execute()
            
            response_data = {
                "user_email": user_email,
                "event_id": event['id'],
                "summary": event['summary'],
                "start": event['start'],
                "end": event['end'],
                "html_link": event.get('htmlLink'),
                "created": event.get('created')
            }
            
            return f"✅ Created calendar event for {user_email}:\n\n{response_data}"
            
        except ValueError as e:
            return f"❌ Authentication error: {str(e)}"
        except Exception as e:
            logger.error(f"Error creating calendar event: {e}")
            return f"❌ Error creating calendar event: {str(e)}"
    
    @mcp.tool()
    async def get_my_auth_status() -> str:
        """Get the current user's authentication status and available services.
        
        This tool demonstrates how to use multiple resource templates.
        
        Returns:
            Detailed authentication status
        """
        try:
            # Try to get user email from resource context first
            try:
                user_email = get_current_user_email_simple()
                logger.info(f"✅ Got user email from context: {user_email}")
            except ValueError:
                # Fallback: Extract email from available credentials
                logger.warning("⚠️ No user context available, attempting to detect authenticated user...")
                user_email = await _detect_authenticated_user()
                if not user_email:
                    return "❌ Authentication error: No authenticated user found in current session. Please ensure the user is authenticated with start_google_auth tool first."
            
            # Import here to avoid circular imports
            from auth.google_auth import get_valid_credentials
            from auth.service_helpers import SERVICE_DEFAULTS
            
            # Check credentials
            credentials = get_valid_credentials(user_email)
            
            if not credentials:
                return f"❌ No valid credentials found for {user_email}. Please authenticate first."
            
            # Build comprehensive status
            auth_info = {
                "user_email": user_email,
                "authenticated": True,
                "credentials_valid": not credentials.expired,
                "expires_at": credentials.expiry.isoformat() if credentials.expiry else None,
                "scopes": credentials.scopes or [],
                "available_services": list(SERVICE_DEFAULTS.keys()),
                "has_refresh_token": credentials.refresh_token is not None
            }
            
            if credentials.expired:
                auth_info["status"] = "Credentials expired but can be refreshed"
            else:
                auth_info["status"] = "Fully authenticated and ready"
            
            return f"✅ Authentication status for {user_email}:\n\n{auth_info}"
            
        except ValueError as e:
            return f"❌ Authentication error: {str(e)}"
        except Exception as e:
            logger.error(f"Error checking auth status: {e}")
            return f"❌ Error checking authentication: {str(e)}"
    
    logger.info("✅ Enhanced tools with resource templating registered")


# Helper function for backwards compatibility
def get_user_email_from_context_or_param(user_google_email: Optional[str] = None) -> str:
    """Helper function for gradual migration of existing tools.
    
    This function allows tools to work with both the old pattern (passing user_google_email)
    and the new pattern (using resource context). Useful during migration period.
    
    Args:
        user_google_email: Optional user email parameter (legacy pattern)
    
    Returns:
        User email from parameter or context
        
    Raises:
        ValueError: If no user email available from either source
    """
    if user_google_email:
        # Legacy pattern: use provided parameter
        return user_google_email
    
    try:
        # New pattern: get from resource context
        return get_current_user_email_simple()
    except ValueError:
        raise ValueError(
            "No user email available. Either pass user_google_email parameter "
            "or ensure user is authenticated in current session."
        )