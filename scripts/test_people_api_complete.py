"""Complete test of People API with full output visibility."""

import json
import base64
from pathlib import Path
from cryptography.fernet import Fernet
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from datetime import datetime
from config.settings import settings

def load_creds(user_email):
    """Load encrypted credentials."""
    key_path = Path('credentials/.auth_encryption_key')
    with open(key_path, 'rb') as f:
        key_bytes = f.read()
    fernet = Fernet(key_bytes)
    
    safe_email = user_email.replace("@", "_at_").replace(".", "_")
    creds_path = Path(f'credentials/{safe_email}_credentials.enc')
    with open(creds_path, 'r') as f:
        encrypted = f.read()
    
    encrypted_bytes = base64.urlsafe_b64decode(encrypted.encode())
    decrypted = fernet.decrypt(encrypted_bytes)
    data = json.loads(decrypted.decode())
    
    creds = Credentials(
        token=data['token'],
        refresh_token=data['refresh_token'],
        token_uri=data.get('token_uri'),
        client_id=data['client_id'],
        client_secret=data['client_secret'],
        scopes=data.get('scopes', [])
    )
    if data.get('expiry'):
        creds.expiry = datetime.fromisoformat(data['expiry'])
    return creds

def main():
    print("=" * 80)
    print("🧪 COMPLETE PEOPLE API TEST")
    print("=" * 80)
    
    user_email = "srivers@groupon.com"
    print(f"\n📧 User: {user_email}")
    
    # Load creds
    creds = load_creds(user_email)
    print(f"✅ Credentials loaded")
    print(f"📋 Total scopes: {len(creds.scopes)}")
    
    # Check People API scope
    people_scope = "https://www.googleapis.com/auth/contacts.readonly"
    has_people = people_scope in creds.scopes
    print(f"👤 People API scope: {'✅ YES' if has_people else '❌ NO'}")
    
    # Build services
    print("\n🔧 Building Google API services...")
    chat = build('chat', 'v1', credentials=creds)
    people = build('people', 'v1', credentials=creds) if has_people else None
    print("✅ Services built")
    
    # List spaces
    print("\n💬 Listing Chat spaces...")
    spaces_resp = chat.spaces().list(pageSize=10).execute()
    spaces = spaces_resp.get('spaces', [])
    print(f"✅ Found {len(spaces)} spaces:\n")
    for i, space in enumerate(spaces, 1):
        print(f"{i}. {space.get('displayName')} ({space.get('name')})")
    
    if not spaces:
        print("\n❌ No spaces found - cannot test messages")
        return
    
    # Pick first space with messages
    print("\n" + "=" * 80)
    print("📨 TESTING MESSAGES FROM EACH SPACE")
    print("=" * 80)
    
    for space in spaces[:3]:  # Test first 3 spaces
        space_id = space.get('name')
        space_name = space.get('displayName')
        
        print(f"\n📍 Space: {space_name}")
        print(f"   ID: {space_id}")
        
        try:
            # List messages
            msg_resp = chat.spaces().messages().list(
                parent=space_id,
                pageSize=5,
                orderBy='createTime desc'
            ).execute()
            
            messages = msg_resp.get('messages', [])
            print(f"   Messages: {len(messages)}")
            
            if not messages:
                print("   ⏭️  No messages, skipping...")
                continue
            
            # Show messages
            print("\n   📨 Message senders:")
            user_ids = set()
            for msg in messages:
                sender = msg.get('sender', {})
                sender_name = sender.get('displayName') or sender.get('name', 'Unknown')
                text = (msg.get('text', '')[:60] + '...') if len(msg.get('text', '')) > 60 else msg.get('text', '')
                
                print(f"\n   👤 Sender: {sender_name}")
                print(f"      Text: {text}")
                
                # Collect user IDs
                if sender_name.startswith('users/'):
                    user_id = sender_name.split('/')[-1]
                    user_ids.add(user_id)
            
            # Test People API enrichment
            if user_ids and people:
                print(f"\n   👤 PEOPLE API ENRICHMENT TEST ({len(user_ids)} users):")
                print("   " + "-" * 76)
                
                for user_id in user_ids:
                    try:
                        person = people.people().get(
                            resourceName=f"people/{user_id}",
                            personFields='names,emailAddresses'
                        ).execute()
                        
                        names = person.get('names', [])
                        emails = person.get('emailAddresses', [])
                        
                        name = names[0].get('displayName') if names else None
                        email = emails[0].get('value') if emails else None
                        
                        print(f"\n   ✅ {user_id}:")
                        print(f"      Name: {name or 'N/A'}")
                        print(f"      Email: {email or 'N/A'}")
                        
                    except Exception as e:
                        error_msg = str(e)[:80]
                        print(f"\n   ❌ {user_id}: {error_msg}")
                
                # We found messages with user IDs - stop here
                break
                
        except Exception as e:
            print(f"   ❌ Error: {str(e)[:100]}")
    
    print("\n" + "=" * 80)
    print("🎉 TEST COMPLETE")
    print("=" * 80)

if __name__ == "__main__":
    main()