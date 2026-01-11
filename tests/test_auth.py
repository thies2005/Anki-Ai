
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
