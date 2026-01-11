
import pytest
import hashlib
import json
import os
import bcrypt
from utils.auth import UserManager

# Mock data file for testing
TEST_DATA_FILE = "data/test_users.json"

@pytest.fixture
def auth_manager():
    # Setup
    if os.path.exists(TEST_DATA_FILE):
        os.remove(TEST_DATA_FILE)
    
    manager = UserManager(data_file=TEST_DATA_FILE)
    yield manager
    
    # Teardown
    if os.path.exists(TEST_DATA_FILE):
        os.remove(TEST_DATA_FILE)

def test_register_creates_bcrypt_hash(auth_manager):
    email = "test@example.com"
    password = "password123"
    
    success, msg = auth_manager.register(email, password)
    assert success is True
    
    # Verify directly in file
    with open(TEST_DATA_FILE, 'r') as f:
        data = json.load(f)
    
    stored_hash = data[email]["password_hash"]
    assert stored_hash.startswith("$2b$")
    assert bcrypt.checkpw(password.encode(), stored_hash.encode())

def test_login_success(auth_manager):
    email = "test@example.com"
    password = "password123"
    auth_manager.register(email, password)
    
    success, user = auth_manager.login(email, password)
    assert success is True
    assert user["email"] == email

def test_login_failure(auth_manager):
    email = "test@example.com"
    password = "password123"
    auth_manager.register(email, password)
    
    success, msg = auth_manager.login(email, "wrongpassword")
    assert success is False

def test_migration_from_sha256(auth_manager):
    email = "legacy@example.com"
    password = "legacypassword"
    
    # Manually create a legacy user
    legacy_hash = hashlib.sha256(password.encode()).hexdigest()
    data = {
        email: {
            "password_hash": legacy_hash,
            "api_keys": {}
        }
    }
    with open(TEST_DATA_FILE, 'w') as f:
        json.dump(data, f)
        
    # Verify it is legacy first
    with open(TEST_DATA_FILE, 'r') as f:
        d = json.load(f)
        assert d[email]["password_hash"] == legacy_hash
        
    # Login should succeed AND migrate
    success, user = auth_manager.login(email, password)
    assert success is True
    
    # Verify migration to bcrypt
    with open(TEST_DATA_FILE, 'r') as f:
        d = json.load(f)
        new_hash = d[email]["password_hash"]
        
    assert new_hash != legacy_hash
    assert new_hash.startswith("$2b$")
    assert bcrypt.checkpw(password.encode(), new_hash.encode())


# --- Encryption Tests ---

def test_encryption_roundtrip(auth_manager):
    """Test that encryption and decryption work correctly."""
    from utils.auth import _key_encryption
    
    original = "sk-test-api-key-12345"
    encrypted = _key_encryption.encrypt(original)
    
    assert encrypted != original
    assert encrypted.startswith("enc:")
    
    decrypted = _key_encryption.decrypt(encrypted)
    assert decrypted == original


def test_encryption_plaintext_passthrough(auth_manager):
    """Test that plaintext values (without enc: prefix) are returned as-is."""
    from utils.auth import _key_encryption
    
    plaintext = "sk-plaintext-key"
    result = _key_encryption.decrypt(plaintext)
    
    assert result == plaintext


def test_is_encrypted_check(auth_manager):
    """Test the is_encrypted helper."""
    from utils.auth import _key_encryption
    
    assert _key_encryption.is_encrypted("enc:abc123") == True
    assert _key_encryption.is_encrypted("plaintext-key") == False
    assert _key_encryption.is_encrypted("") == False
    assert _key_encryption.is_encrypted(None) == False


def test_save_and_get_keys_with_encryption(auth_manager):
    """Test that keys are encrypted when saved and decrypted when retrieved."""
    email = "crypto@example.com"
    password = "TestPass123"
    
    # Register user
    auth_manager.register(email, password)
    
    # Save keys
    test_keys = {"google": "sk-test-google-key", "openrouter": "sk-test-or-key"}
    auth_manager.save_keys(email, test_keys)
    
    # Verify storage is encrypted by loading raw data
    with open(TEST_DATA_FILE, 'r') as f:
        raw_data = json.load(f)
    
    stored_keys = raw_data[email]["api_keys"]
    for key_value in stored_keys.values():
        assert key_value.startswith("enc:"), "Keys should be encrypted in storage"
    
    # Verify retrieval decrypts correctly
    retrieved = auth_manager.get_keys(email)
    assert retrieved["google"] == "sk-test-google-key"
    assert retrieved["openrouter"] == "sk-test-or-key"

