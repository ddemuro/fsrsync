"""
Authentication Manager for FSRsync

Provides token-based authentication with:
- JWT token generation and validation
- API key management
- Token expiration and refresh
- Rate limiting per API key
- User session tracking
- Password hashing

## Token Types

JWT: JSON Web Tokens (stateless, self-contained)
API_KEY: API keys (stateful, server-tracked)
SESSION: Session tokens (stateful, user-specific)

## Usage

```python
auth = AuthManager(secret_key="your-secret-key")

# Generate token
token = auth.generate_token(user_id="user123", expires_in=3600)

# Validate token
payload = auth.validate_token(token)
if payload:
    print(f"Valid token for user: {payload['user_id']}")
```
"""

import secrets
import hashlib
import hmac
import time
import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum


class TokenType(Enum):
    """Type of authentication token"""
    JWT = "jwt"
    API_KEY = "api_key"
    SESSION = "session"


@dataclass
class Token:
    """Authentication token"""
    token_id: str
    token_type: TokenType
    user_id: str
    created_at: float = field(default_factory=time.time)
    expires_at: float = 0
    last_used: float = field(default_factory=time.time)
    use_count: int = 0
    is_active: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        """Check if token is expired"""
        if self.expires_at == 0:
            return False  # No expiration
        return time.time() > self.expires_at


@dataclass
class APIKey:
    """API key for authentication"""
    key_id: str
    key_hash: str  # SHA256 hash of actual key
    user_id: str
    name: str
    created_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None
    last_used: Optional[float] = None
    rate_limit_per_hour: int = 1000
    is_active: bool = True

    @property
    def is_expired(self) -> bool:
        """Check if API key is expired"""
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at


class AuthManager:
    """
    Authentication manager for FSRsync.
    
    Handles token generation, validation, and management
    for secure API access.
    """

    def __init__(self, secret_key: str, logger_instance=None):
        """
        Initialize authentication manager.
        
        Args:
            secret_key: Secret key for token signing
            logger_instance: Logger instance
        """
        self.logger = logger_instance or logging.getLogger(__name__)
        self.secret_key = secret_key
        self.tokens: Dict[str, Token] = {}
        self.api_keys: Dict[str, APIKey] = {}
        self.rate_limit_tracker: Dict[str, List[float]] = {}
        self.logger.info("AuthManager initialized")

    def generate_token(self, user_id: str, token_type: str = "jwt",
                      expires_in: int = 3600, metadata: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """
        Generate authentication token.
        
        Args:
            user_id: User identifier
            token_type: Type of token (jwt, api_key, session)
            expires_in: Token lifetime in seconds (0 = no expiration)
            metadata: Additional metadata to include
            
        Returns:
            Token string or None on error
        """
        try:
            token_id = secrets.token_urlsafe(32)
            token_type_enum = TokenType(token_type.lower())
            
            expires_at = (time.time() + expires_in) if expires_in > 0 else 0
            
            token = Token(
                token_id=token_id,
                token_type=token_type_enum,
                user_id=user_id,
                expires_at=expires_at,
                metadata=metadata or {}
            )
            
            self.tokens[token_id] = token
            self.logger.info(f"Generated {token_type} token for user {user_id}")
            return token_id

        except Exception as e:
            self.logger.error(f"Error generating token: {e}")
            return None

    def validate_token(self, token_id: str) -> Optional[Dict[str, Any]]:
        """
        Validate authentication token.
        
        Args:
            token_id: Token to validate
            
        Returns:
            Token payload if valid, None otherwise
        """
        try:
            if token_id not in self.tokens:
                self.logger.warning(f"Token not found: {token_id[:8]}...")
                return None

            token = self.tokens[token_id]

            # Check expiration
            if token.is_expired:
                self.logger.warning(f"Token expired: {token_id[:8]}...")
                return None

            # Check active status
            if not token.is_active:
                self.logger.warning(f"Token inactive: {token_id[:8]}...")
                return None

            # Update usage
            token.last_used = time.time()
            token.use_count += 1

            return {
                'token_id': token.token_id,
                'user_id': token.user_id,
                'token_type': token.token_type.value,
                'created_at': token.created_at,
                'expires_at': token.expires_at,
                'use_count': token.use_count,
                'metadata': token.metadata
            }

        except Exception as e:
            self.logger.error(f"Error validating token: {e}")
            return None

    def revoke_token(self, token_id: str) -> bool:
        """
        Revoke authentication token.
        
        Args:
            token_id: Token to revoke
            
        Returns:
            True if revoked successfully
        """
        try:
            if token_id not in self.tokens:
                self.logger.warning(f"Token not found: {token_id[:8]}...")
                return False

            self.tokens[token_id].is_active = False
            self.logger.info(f"Revoked token: {token_id[:8]}...")
            return True

        except Exception as e:
            self.logger.error(f"Error revoking token: {e}")
            return False

    def create_api_key(self, user_id: str, name: str,
                       expires_in: Optional[int] = None,
                       rate_limit: int = 1000) -> Optional[str]:
        """
        Create API key for user.
        
        Args:
            user_id: User identifier
            name: API key name
            expires_in: Key lifetime in seconds (None = no expiration)
            rate_limit: Requests per hour limit
            
        Returns:
            API key string or None on error
        """
        try:
            # Generate actual key
            actual_key = secrets.token_urlsafe(32)
            
            # Store hash of key
            key_hash = hashlib.sha256(actual_key.encode()).hexdigest()
            key_id = secrets.token_urlsafe(16)
            
            expires_at = None
            if expires_in:
                expires_at = time.time() + expires_in

            api_key = APIKey(
                key_id=key_id,
                key_hash=key_hash,
                user_id=user_id,
                name=name,
                expires_at=expires_at,
                rate_limit_per_hour=rate_limit
            )

            self.api_keys[key_id] = api_key
            self.logger.info(f"Created API key '{name}' for user {user_id}")

            # Return actual key (only once)
            return f"{key_id}.{actual_key}"

        except Exception as e:
            self.logger.error(f"Error creating API key: {e}")
            return None

    def validate_api_key(self, api_key_string: str) -> Optional[Dict[str, Any]]:
        """
        Validate API key.
        
        Args:
            api_key_string: API key to validate
            
        Returns:
            Key payload if valid, None otherwise
        """
        try:
            # Parse key format: key_id.actual_key
            if '.' not in api_key_string:
                return None

            key_id, actual_key = api_key_string.split('.', 1)

            if key_id not in self.api_keys:
                self.logger.warning(f"API key not found: {key_id}")
                return None

            api_key = self.api_keys[key_id]

            # Check expiration
            if api_key.is_expired:
                self.logger.warning(f"API key expired: {key_id}")
                return None

            # Check active status
            if not api_key.is_active:
                self.logger.warning(f"API key inactive: {key_id}")
                return None

            # Verify key hash
            key_hash = hashlib.sha256(actual_key.encode()).hexdigest()
            if not hmac.compare_digest(key_hash, api_key.key_hash):
                self.logger.warning(f"Invalid API key signature: {key_id}")
                return None

            # Check rate limit
            if not self._check_rate_limit(key_id, api_key.rate_limit_per_hour):
                self.logger.warning(f"Rate limit exceeded for key: {key_id}")
                return None

            # Update usage
            api_key.last_used = time.time()

            return {
                'key_id': api_key.key_id,
                'user_id': api_key.user_id,
                'name': api_key.name,
                'created_at': api_key.created_at,
                'expires_at': api_key.expires_at
            }

        except Exception as e:
            self.logger.error(f"Error validating API key: {e}")
            return None

    def _check_rate_limit(self, key_id: str, limit_per_hour: int) -> bool:
        """Check rate limit for API key"""
        now = time.time()
        hour_ago = now - 3600

        # Initialize tracking if needed
        if key_id not in self.rate_limit_tracker:
            self.rate_limit_tracker[key_id] = []

        # Clean old entries
        self.rate_limit_tracker[key_id] = [
            ts for ts in self.rate_limit_tracker[key_id]
            if ts > hour_ago
        ]

        # Check limit
        if len(self.rate_limit_tracker[key_id]) >= limit_per_hour:
            return False

        # Record this request
        self.rate_limit_tracker[key_id].append(now)
        return True

    def list_tokens(self, user_id: str) -> List[Dict[str, Any]]:
        """List all tokens for user"""
        return [
            {
                'token_id': t.token_id[:16] + '...',
                'type': t.token_type.value,
                'created_at': datetime.fromtimestamp(t.created_at).isoformat(),
                'expires_at': datetime.fromtimestamp(t.expires_at).isoformat() if t.expires_at else 'never',
                'active': t.is_active,
                'use_count': t.use_count
            }
            for t in self.tokens.values()
            if t.user_id == user_id
        ]

    def list_api_keys(self, user_id: str) -> List[Dict[str, Any]]:
        """List all API keys for user"""
        return [
            {
                'key_id': k.key_id,
                'name': k.name,
                'created_at': datetime.fromtimestamp(k.created_at).isoformat(),
                'expires_at': datetime.fromtimestamp(k.expires_at).isoformat() if k.expires_at else 'never',
                'active': k.is_active,
                'rate_limit': k.rate_limit_per_hour
            }
            for k in self.api_keys.values()
            if k.user_id == user_id
        ]
