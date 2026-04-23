from yonca.models import User
from yonca.google_drive_service import SCOPES, authenticate

print("=== OAuth Configuration Debug ===\n")
print(f"Current SCOPES in code: {SCOPES}\n")

# Get user with Google tokens
user = User.query.filter_by(id=1).first()

if not user:
    print("❌ User with ID 1 not found")
else:
    print(f"User: {user.email}")
    print(f"Has access token: {bool(user.google_access_token)}")
    print(f"Has refresh token: {bool(user.google_refresh_token)}")
    
    if user.google_access_token:
        print("\n=== Attempting to authenticate... ===")
        service = authenticate(user)
        
        if service:
            print("✅ Authentication successful")
            
            # Try to list files in user's Drive
            print("\n=== Testing Drive access... ===")
            try:
                results = service.files().list(pageSize=5).execute()
                files = results.get('files', [])
                print(f"✅ Can list files. Found {len(files)} files:")
                for file in files:
                    print(f"  - {file['name']} (ID: {file['id']})")
            except Exception as e:
                print(f"❌ Failed to list files: {e}")
                print("\n⚠️  This means the OAuth scope is still restricted.")
                print("Try fully disconnecting from Google:")
                print("  1. Go to https://myaccount.google.com/permissions")
                print("  2. Find and REMOVE 'Yonca'")
                print("  3. Clear browser cookies for Yonca")
                print("  4. Log out and back in to Yonca")
                print("  5. Authenticate with Google again")
        else:
            print("❌ Authentication failed")
