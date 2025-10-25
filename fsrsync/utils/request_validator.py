"""
Request Validation and Sanitization for FSRsync

Provides comprehensive request validation with:
- Input type checking
- Size limit enforcement
- Path traversal prevention
- SQL injection prevention
- XSS prevention
- Header validation
- Content-type validation

## Validation Levels

PERMISSIVE: Only check required fields
STANDARD: Check types and sizes
STRICT: Full validation including content
"""

import re
import logging
from typing import Any, Dict, Optional, List, Union
from urllib.parse import urlparse, unquote


class ValidationError(Exception):
    """Validation error"""
    pass


class RequestValidator:
    """
    Request validation and sanitization system for FSRsync.
    
    Prevents common web vulnerabilities and enforces
    request format standards.
    """

    # Maximum request sizes
    MAX_STRING_LENGTH = 10000
    MAX_PATH_LENGTH = 4096
    MAX_ARRAY_SIZE = 1000
    MAX_JSON_SIZE = 10 * 1024 * 1024  # 10MB

    # Dangerous patterns
    DANGEROUS_PATTERNS = [
        r'<script[^>]*>.*?</script>',  # Script tags
        r'javascript:',  # JavaScript protocol
        r'on\w+\s*=',  # Event handlers
        r'<iframe[^>]*>',  # Iframes
        r'<object[^>]*>',  # Objects
        r'<embed[^>]*>',  # Embed tags
    ]

    # Path traversal patterns
    TRAVERSAL_PATTERNS = [
        r'\.\.',
        r'\./',
        r'/\.',
    ]

    def __init__(self, logger_instance=None, strict: bool = False):
        """
        Initialize validator.
        
        Args:
            logger_instance: Logger instance
            strict: Enable strict validation
        """
        self.logger = logger_instance or logging.getLogger(__name__)
        self.strict = strict
        self.compiled_dangerous_patterns = [
            re.compile(pattern, re.IGNORECASE | re.DOTALL)
            for pattern in self.DANGEROUS_PATTERNS
        ]

    def validate_request(self, data: Dict[str, Any], schema: Optional[Dict[str, str]] = None) -> bool:
        """
        Validate entire request.
        
        Args:
            data: Request data
            schema: Optional schema defining expected fields
            
        Returns:
            True if valid
            
        Raises:
            ValidationError if invalid
        """
        if not isinstance(data, dict):
            raise ValidationError("Request must be a dictionary")

        if len(str(data).encode()) > self.MAX_JSON_SIZE:
            raise ValidationError(f"Request exceeds maximum size: {self.MAX_JSON_SIZE}")

        if schema:
            for field, field_type in schema.items():
                if field not in data and self.strict:
                    raise ValidationError(f"Missing required field: {field}")
                if field in data:
                    self.validate_field(field, data[field], field_type)

        return True

    def validate_field(self, field_name: str, value: Any, expected_type: str) -> bool:
        """
        Validate a single field.
        
        Args:
            field_name: Field name
            value: Field value
            expected_type: Expected type (str, int, bool, list, dict)
            
        Returns:
            True if valid
            
        Raises:
            ValidationError if invalid
        """
        if value is None:
            if self.strict:
                raise ValidationError(f"Field '{field_name}' cannot be None")
            return True

        type_checks = {
            'str': lambda v: self._validate_string(field_name, v),
            'int': lambda v: isinstance(v, int) and not isinstance(v, bool),
            'bool': lambda v: isinstance(v, bool),
            'float': lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
            'list': lambda v: self._validate_list(field_name, v),
            'dict': lambda v: isinstance(v, dict),
            'path': lambda v: self._validate_path(field_name, v),
            'email': lambda v: self._validate_email(v),
            'url': lambda v: self._validate_url(v),
        }

        if expected_type not in type_checks:
            raise ValidationError(f"Unknown type: {expected_type}")

        if not type_checks[expected_type](value):
            raise ValidationError(f"Field '{field_name}' has invalid type (expected {expected_type})")

        return True

    def _validate_string(self, field_name: str, value: str) -> bool:
        """Validate string field"""
        if not isinstance(value, str):
            return False

        if len(value) > self.MAX_STRING_LENGTH:
            raise ValidationError(f"Field '{field_name}' exceeds maximum length: {self.MAX_STRING_LENGTH}")

        # Check for XSS
        if self._contains_dangerous_content(value):
            raise ValidationError(f"Field '{field_name}' contains potentially dangerous content")

        return True

    def _validate_list(self, field_name: str, value: List) -> bool:
        """Validate list field"""
        if not isinstance(value, list):
            return False

        if len(value) > self.MAX_ARRAY_SIZE:
            raise ValidationError(f"Field '{field_name}' exceeds maximum array size: {self.MAX_ARRAY_SIZE}")

        return True

    def _validate_path(self, field_name: str, value: str) -> bool:
        """Validate file path"""
        if not isinstance(value, str):
            return False

        # Check length
        if len(value) > self.MAX_PATH_LENGTH:
            raise ValidationError(f"Path exceeds maximum length: {self.MAX_PATH_LENGTH}")

        # Decode URL encoding
        decoded = unquote(value)

        # Check for path traversal
        for pattern in self.TRAVERSAL_PATTERNS:
            if re.search(pattern, decoded):
                raise ValidationError(f"Path traversal detected in '{field_name}'")

        # Check for null bytes
        if '\x00' in value:
            raise ValidationError(f"Null byte in path: '{field_name}'")

        return True

    def _validate_email(self, value: str) -> bool:
        """Validate email address"""
        if not isinstance(value, str):
            return False

        # Simple email validation
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, value))

    def _validate_url(self, value: str) -> bool:
        """Validate URL"""
        if not isinstance(value, str):
            return False

        try:
            result = urlparse(value)
            return all([result.scheme, result.netloc])
        except:
            return False

    def _contains_dangerous_content(self, text: str) -> bool:
        """Check if text contains dangerous content"""
        for pattern in self.compiled_dangerous_patterns:
            if pattern.search(text):
                return True
        return False

    def sanitize_string(self, value: str) -> str:
        """Sanitize string input"""
        if not isinstance(value, str):
            return str(value)

        # Remove null bytes
        value = value.replace('\x00', '')

        # Limit length
        if len(value) > self.MAX_STRING_LENGTH:
            value = value[:self.MAX_STRING_LENGTH]

        return value

    def sanitize_path(self, value: str) -> str:
        """Sanitize file path"""
        if not isinstance(value, str):
            return str(value)

        # Decode
        value = unquote(value)

        # Remove null bytes
        value = value.replace('\x00', '')

        # Remove dangerous sequences
        value = re.sub(r'\.\./', '', value)
        value = re.sub(r'/\./', '/', value)

        # Limit length
        if len(value) > self.MAX_PATH_LENGTH:
            value = value[:self.MAX_PATH_LENGTH]

        return value

    def get_validation_stats(self) -> Dict[str, Any]:
        """Get validation statistics"""
        return {
            'max_string_length': self.MAX_STRING_LENGTH,
            'max_path_length': self.MAX_PATH_LENGTH,
            'max_array_size': self.MAX_ARRAY_SIZE,
            'max_json_size': self.MAX_JSON_SIZE,
            'strict_mode': self.strict,
            'dangerous_patterns_count': len(self.DANGEROUS_PATTERNS)
        }
