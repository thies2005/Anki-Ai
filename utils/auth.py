import json
import os
import hashlib
import logging

DATA_FILE = "data/users.json"
logger = logging.getLogger(__name__)

class UserManager:
    def __init__(self, data_file=DATA_FILE):
        self.data_file = data_file
        self._ensure_data_file()

    def _ensure_data_file(self):
        """Creates the data file if it doesn't exist."""
        if not os.path.exists(self.data_file):
            os.makedirs(os.path.dirname(self.data_file), exist_ok=True)
            with open(self.data_file, 'w') as f:
                json.dump({}, f)

    def _load_data(self):
        """Loads the entire user database."""
        try:
            with open(self.data_file, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {}

    def _save_data(self, data):
        """Saves the user database."""
        with open(self.data_file, 'w') as f:
            json.dump(data, f, indent=4)

    def _hash_password(self, password):
        """Return a SHA-256 hash of the password."""
        return hashlib.sha256(password.encode()).hexdigest()

    def register(self, email, password):
        """
        Registers a new user.
        Returns (success, message).
        """
        data = self._load_data()
        if email in data:
            return False, "User already exists."
        
        data[email] = {
            "password_hash": self._hash_password(password),
            "api_keys": {}
        }
        self._save_data(data)
        return True, "User registered successfully."

    def login(self, email, password):
        """
        Authenticates a user.
        Returns (success, user_data_or_error_message).
        """
        data = self._load_data()
        user = data.get(email)
        
        if not user:
            return False, "User not found."
        
        if user["password_hash"] == self._hash_password(password):
            # Return user data excluding password
            return True, {
                "email": email,
                "api_keys": user.get("api_keys", {})
            }
        else:
            return False, "Invalid password."

    def save_keys(self, email, keys):
        """
        Updates API keys for a user.
        keys: dict of {'provider_name': 'key_value'}
        """
        data = self._load_data()
        if email not in data:
            return False, "User not found."
        
        # Update keys (merge with existing)
        current_keys = data[email].get("api_keys", {})
        current_keys.update(keys)
        data[email]["api_keys"] = current_keys
        
        self._save_data(data)
        return True, "Keys saved successfully."

    def get_keys(self, email):
        """Retrieve API keys for a user."""
        data = self._load_data()
        if email not in data:
            return {}
        return data[email].get("api_keys", {})
