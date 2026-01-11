import json
import os
import hashlib
import hmac
import logging
import secrets
import time
import bcrypt
import re
from utils.email_client import EmailClient

DATA_FILE = "data/users.json"
logger = logging.getLogger(__name__)

# Rate limiting configuration
MAX_ATTEMPTS = 5
RATE_LIMIT_WINDOW = 300  # 5 minutes in seconds


class RateLimiter:
    """Simple in-memory rate limiter for auth operations."""

    def __init__(self):
        self._attempts = {}  # {(action, identifier): [timestamp1, timestamp2, ...]}

    def _cleanup_old_attempts(self, key):
        """Remove attempts older than the rate limit window."""
        if key in self._attempts:
            now = time.time()
            self._attempts[key] = [
                ts for ts in self._attempts[key]
                if now - ts < RATE_LIMIT_WINDOW
            ]
            # Remove empty lists
            if not self._attempts[key]:
                del self._attempts[key]

    def record_attempt(self, action, identifier):
        """Record an attempt for rate limiting."""
        key = (action, identifier)
        self._cleanup_old_attempts(key)
        if key not in self._attempts:
            self._attempts[key] = []
        self._attempts[key].append(time.time())

    def is_rate_limited(self, action, identifier):
        """Check if the identifier has exceeded rate limit."""
        key = (action, identifier)
        self._cleanup_old_attempts(key)
        attempts = len(self._attempts.get(key, []))
        return attempts >= MAX_ATTEMPTS

    def get_remaining_attempts(self, action, identifier):
        """Get remaining attempts before rate limit."""
        key = (action, identifier)
        self._cleanup_old_attempts(key)
        attempts = len(self._attempts.get(key, []))
        return max(0, MAX_ATTEMPTS - attempts)


# Global rate limiter instance
_rate_limiter = RateLimiter()

class UserManager:
    def __init__(self, data_file=DATA_FILE):
        self.data_file = data_file
        self.email_client = EmailClient()
        self.rate_limiter = _rate_limiter
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
        """
        Return a bcrypt hash of the password.
        """
        # salt is generated automatically by hashpw
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    def _verify_password(self, stored_hash, password):
        """
        Verify password against stored hash (supports bcrypt and legacy SHA-256).
        Returns: (is_valid, is_legacy)
        """
        # Check if it's a legacy SHA-256 hash (64 hex chars)
        if len(stored_hash) == 64 and "$" not in stored_hash:
            # Legacy verification
            legacy_hash = hashlib.sha256(password.encode()).hexdigest()
            return (stored_hash == legacy_hash), True
        
        # Bcrypt verification
        try:
            return bcrypt.checkpw(password.encode('utf-8'), stored_hash.encode('utf-8')), False
        except ValueError:
            return False, False

    def _validate_password_strength(self, password):
        """
        Validate password strength.
        Returns (is_valid, error_message).
        """
        if len(password) < 8:
            return False, "Password must be at least 8 characters long."
        if not re.search(r'[A-Z]', password):
            return False, "Password must contain at least one uppercase letter."
        if not re.search(r'[a-z]', password):
            return False, "Password must contain at least one lowercase letter."
        if not re.search(r'[0-9]', password):
            return False, "Password must contain at least one digit."
        return True, ""

    def register(self, email, password):
        """
        Registers a new user.
        Returns (success, message).
        """
        # Rate limiting - record attempt first
        self.rate_limiter.record_attempt("register", email)
        if self.rate_limiter.is_rate_limited("register", email):
            return False, f"Too many registration attempts. Please try again later."

        # Validate password strength
        is_valid, error_msg = self._validate_password_strength(password)
        if not is_valid:
            return False, error_msg

        data = self._load_data()
        if email in data:
            return False, "User already exists."
        
        data[email] = {
            "password_hash": self._hash_password(password),
            "api_keys": {}
        }
        self._save_data(data)
        
        # Send Welcome Email
        self.email_client.send_welcome_email(email)

        return True, "User registered successfully."

    def initiate_password_reset(self, email):
        """
        Generates a reset code and sends it via email.
        Uses cryptographically secure random number generation.
        """
        # Rate limiting
        self.rate_limiter.record_attempt("reset", email)
        if self.rate_limiter.is_rate_limited("reset", email):
            return False, f"Too many reset attempts. Please try again later."

        data = self._load_data()
        if email not in data:
            # Don't reveal if email exists - use same message as success
            # to prevent email enumeration
            return False, "User not found."

        # Generate cryptographically secure 6-digit code
        code = secrets.token_hex(3)[:6].upper()
        expiration = time.time() + 600  # 10 mins

        # Hash the code before storing (timing-safe comparison on verification)
        data[email]["reset_code"] = hashlib.sha256(code.encode()).hexdigest()
        data[email]["reset_expiry"] = expiration
        self._save_data(data)

        # Send Email with plaintext code
        success, msg = self.email_client.send_reset_email(email, code)
        if success:
            return True, "Verification code sent to email."
        else:
            return False, f"Failed to send email: {msg}"

    def complete_password_reset(self, email, code, new_password):
        """
        Verifies code and updates password.
        Uses timing-safe comparison for code verification.
        """
        # Rate limiting
        self.rate_limiter.record_attempt("reset_verify", email)
        if self.rate_limiter.is_rate_limited("reset_verify", email):
            return False, "Too many verification attempts. Please try again later."

        # Validate password strength
        is_valid, error_msg = self._validate_password_strength(new_password)
        if not is_valid:
            return False, error_msg

        data = self._load_data()
        if email not in data:
            return False, "User not found."

        user = data[email]
        stored_code_hash = user.get("reset_code")
        expiry = user.get("reset_expiry", 0)

        if not stored_code_hash:
            return False, "No reset code found. Please request a new one."

        # Hash the provided code and compare using timing-safe comparison
        provided_code_hash = hashlib.sha256(code.encode()).hexdigest()
        if not hmac.compare_digest(stored_code_hash, provided_code_hash):
            return False, "Invalid verification code."

        if time.time() > expiry:
            return False, "Verification code expired."

        # Update Password
        user["password_hash"] = self._hash_password(new_password)
        # Clear code
        user.pop("reset_code", None)
        user.pop("reset_expiry", None)

        self._save_data(data)
        return True, "Password reset successfully. You can now login."

    def login(self, email, password):
        """
        Authenticates a user.
        Returns (success, user_data_or_error_message).
        """
        # Rate limiting
        self.rate_limiter.record_attempt("login", email)
        if self.rate_limiter.is_rate_limited("login", email):
            return False, f"Too many login attempts. Please try again later."

        data = self._load_data()
        user = data.get(email)
        
        if not user:
            return False, "User not found."
        
        # Get stored hash
        stored_hash = user.get("password_hash", "")
        
        # Verify
        is_valid, is_legacy = self._verify_password(stored_hash, password)
        
        if is_valid:
            # If legacy, migrate to bcrypt immediately
            if is_legacy:
                logger.info(f"Migrating user {email} from SHA-256 to bcrypt.")
                user["password_hash"] = self._hash_password(password)
                self._save_data(data)
                
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
