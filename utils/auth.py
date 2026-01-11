import json
import os
import hashlib
import hmac
import logging
import secrets
import time
import base64
import bcrypt
import re
from cryptography.fernet import Fernet, InvalidToken
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


class KeyEncryption:
    """
    Handles encryption/decryption of API keys using Fernet symmetric encryption.
    
    The encryption key is loaded from API_ENCRYPTION_KEY environment variable.
    If not set, a key is auto-generated and saved to .encryption_key file.
    """
    
    KEY_FILE = "data/.encryption_key"
    
    def __init__(self):
        self._fernet = None
        self._init_encryption()
    
    def _init_encryption(self):
        """Initialize the Fernet cipher with encryption key."""
        key = self._get_or_create_key()
        if key:
            try:
                self._fernet = Fernet(key)
            except Exception as e:
                logger.error(f"Failed to initialize encryption: {e}")
                self._fernet = None
    
    def _get_or_create_key(self) -> bytes:
        """
        Get encryption key from environment or file, or generate a new one.
        Returns the key as bytes suitable for Fernet.
        """
        # 1. Try environment variable first
        env_key = os.getenv("API_ENCRYPTION_KEY")
        if env_key:
            try:
                # Ensure it's valid base64 and correct length
                key_bytes = base64.urlsafe_b64decode(env_key)
                if len(key_bytes) == 32:
                    return env_key.encode() if isinstance(env_key, str) else env_key
            except Exception:
                logger.warning("Invalid API_ENCRYPTION_KEY format, generating new key")
        
        # 2. Try loading from file
        if os.path.exists(self.KEY_FILE):
            try:
                with open(self.KEY_FILE, 'rb') as f:
                    key = f.read().strip()
                    # Validate key
                    Fernet(key)
                    return key
            except Exception as e:
                logger.warning(f"Failed to load encryption key from file: {e}")
        
        # 3. Generate new key
        key = Fernet.generate_key()
        try:
            os.makedirs(os.path.dirname(self.KEY_FILE), exist_ok=True)
            with open(self.KEY_FILE, 'wb') as f:
                f.write(key)
            logger.info("Generated new API encryption key")
        except Exception as e:
            logger.error(f"Failed to save encryption key: {e}")
        
        return key
    
    def encrypt(self, plaintext: str) -> str:
        """
        Encrypt a string value.
        Returns encrypted value prefixed with 'enc:' marker.
        """
        if not plaintext or not self._fernet:
            return plaintext
        
        try:
            encrypted = self._fernet.encrypt(plaintext.encode('utf-8'))
            return f"enc:{encrypted.decode('utf-8')}"
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            return plaintext
    
    def decrypt(self, ciphertext: str) -> str:
        """
        Decrypt a string value.
        Handles both encrypted (prefixed with 'enc:') and plaintext values.
        """
        if not ciphertext or not self._fernet:
            return ciphertext
        
        # Check if value is encrypted (has our marker)
        if not ciphertext.startswith("enc:"):
            # Plaintext value - return as-is (migration case)
            return ciphertext
        
        try:
            encrypted_data = ciphertext[4:]  # Remove 'enc:' prefix
            decrypted = self._fernet.decrypt(encrypted_data.encode('utf-8'))
            return decrypted.decode('utf-8')
        except InvalidToken:
            logger.error("Decryption failed: invalid token (wrong key?)")
            return ""
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            return ""
    
    def is_encrypted(self, value: str) -> bool:
        """Check if a value is already encrypted."""
        return value.startswith("enc:") if value else False


# Global encryption instance
_key_encryption = KeyEncryption()

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
            # Legacy verification - deprecated for security
            logger.warning(f"Login attempted with legacy SHA-256 hash. Password should be reset.")
            legacy_hash = hashlib.sha256(password.encode()).hexdigest()
            is_valid = stored_hash == legacy_hash
            if is_valid:
                logger.warning(f"Legacy hash verified. User should change password immediately.")
            return is_valid, True

        # Bcrypt verification (secure)
        try:
            return bcrypt.checkpw(password.encode('utf-8'), stored_hash.encode('utf-8')), False
        except (ValueError, TypeError) as e:
            logger.warning(f"Password verification failed: {e}")
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
            return False, "Too many reset attempts. Please try again later."

        data = self._load_data()
        if email not in data:
            # Don't reveal if email exists - use same message as success
            # to prevent email enumeration (timing attack mitigation)
            return False, "If this email is registered, a verification code will be sent."

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
            # Use consistent message to prevent email enumeration
            return True, "If this email is registered, a verification code will be sent."
        else:
            # Still use consistent message to prevent information leakage
            logger.error(f"Failed to send reset email to {email}: {msg}")
            return False, "If this email is registered, a verification code will be sent."

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
            # Use consistent message to prevent email enumeration
            return False, "Invalid or expired verification code."

        user = data[email]
        stored_code_hash = user.get("reset_code")
        expiry = user.get("reset_expiry", 0)

        if not stored_code_hash:
            # Use consistent message to prevent timing attacks
            return False, "Invalid or expired verification code."

        # Hash the provided code and compare using timing-safe comparison
        provided_code_hash = hashlib.sha256(code.encode()).hexdigest()
        if not hmac.compare_digest(stored_code_hash, provided_code_hash):
            # Use consistent message to prevent timing attacks
            return False, "Invalid or expired verification code."

        if time.time() > expiry:
            # Clear expired code
            user.pop("reset_code", None)
            user.pop("reset_expiry", None)
            self._save_data(data)
            return False, "Invalid or expired verification code."

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
        Keys are encrypted before storage.
        keys: dict of {'provider_name': 'key_value'}
        """
        data = self._load_data()
        if email not in data:
            return False, "User not found."
        
        # Encrypt each key before storing
        encrypted_keys = {}
        for provider, key_value in keys.items():
            if key_value and not _key_encryption.is_encrypted(key_value):
                encrypted_keys[provider] = _key_encryption.encrypt(key_value)
            else:
                encrypted_keys[provider] = key_value
        
        # Update keys (merge with existing)
        current_keys = data[email].get("api_keys", {})
        current_keys.update(encrypted_keys)
        data[email]["api_keys"] = current_keys
        
        self._save_data(data)
        return True, "Keys saved successfully."

    def get_keys(self, email):
        """
        Retrieve API keys for a user.
        Keys are decrypted before returning.
        Also handles migration of existing plaintext keys.
        """
        data = self._load_data()
        if email not in data:
            return {}
        
        stored_keys = data[email].get("api_keys", {})
        decrypted_keys = {}
        needs_migration = False
        
        for provider, key_value in stored_keys.items():
            if key_value:
                if _key_encryption.is_encrypted(key_value):
                    # Already encrypted - decrypt it
                    decrypted_keys[provider] = _key_encryption.decrypt(key_value)
                else:
                    # Plaintext key - decrypt returns as-is, mark for migration
                    decrypted_keys[provider] = key_value
                    needs_migration = True
            else:
                decrypted_keys[provider] = key_value
        
        # Migrate plaintext keys to encrypted
        if needs_migration:
            logger.info(f"Migrating plaintext API keys for {email}")
            encrypted_keys = {}
            for provider, key_value in stored_keys.items():
                if key_value and not _key_encryption.is_encrypted(key_value):
                    encrypted_keys[provider] = _key_encryption.encrypt(key_value)
                else:
                    encrypted_keys[provider] = key_value
            data[email]["api_keys"] = encrypted_keys
            self._save_data(data)
        
        return decrypted_keys

    def create_session(self, email):
        """
        Creates a session token for the user.
        """
        data = self._load_data()
        if email not in data:
            return None
        
        # simple random token
        token = secrets.token_urlsafe(32)
        # expire in 30 days
        expiry = time.time() + (30 * 24 * 60 * 60)
        
        # Store session
        if "sessions" not in data[email]:
            data[email]["sessions"] = {}
            
        data[email]["sessions"][token] = expiry
        
        # Cleanup old sessions
        current_time = time.time()
        active_sessions = {t: e for t, e in data[email]["sessions"].items() if e > current_time}
        data[email]["sessions"] = active_sessions
        
        self._save_data(data)
        return token

    def validate_session(self, email, token):
        """
        Validates a session token.
        """
        data = self._load_data()
        if email not in data:
            return False
            
        sessions = data[email].get("sessions", {})
        expiry = sessions.get(token)
        
        if not expiry:
            return False
            
        if time.time() > expiry:
            # Expired, remove it
            del data[email]["sessions"][token]
            self._save_data(data)
            return False
            
        return True

    def invalidate_session(self, email, token):
        """
        Invalidates a specific session token.
        """
        data = self._load_data()
        if email not in data:
            return

        sessions = data[email].get("sessions", {})
        if token in sessions:
            del data[email]["sessions"][token]
            self._save_data(data)

    def get_user_by_token(self, token: str):
        """
        Retrieve user email by session token with rate limiting protection.
        Returns (email, user_data) tuple or (None, None) if not found.
        This prevents token enumeration attacks through rate limiting.
        """
        if not token:
            return None, None

        # Rate limit token lookups to prevent enumeration
        if self.rate_limiter.is_rate_limited("token_lookup", "global"):
            logger.warning("Token lookup rate limit reached")
            return None, None

        self.rate_limiter.record_attempt("token_lookup", "global")

        data = self._load_data()
        for email, user_data in data.items():
            if "sessions" in user_data and token in user_data["sessions"]:
                # Validate the session properly
                if self.validate_session(email, token):
                    return email, user_data
                else:
                    # Session exists but is expired
                    return None, None

        return None, None

    def get_preferences(self, email):
        """
        Retrieves user preferences.
        Returns a dict of preferences or empty dict if none found.
        """
        data = self._load_data()
        if email not in data:
            return {}
            
        return data[email].get("preferences", {})

    def save_preferences(self, email, preferences):
        """
        Saves user preferences (merged with existing).
        preferences: dict of settings
        """
        data = self._load_data()
        if email not in data:
            return False
            
        current_prefs = data[email].get("preferences", {})
        current_prefs.update(preferences)
        data[email]["preferences"] = current_prefs
        
        self._save_data(data)
        logger.info(f"Updated preferences for {email}: {preferences.keys()}")
        return True

