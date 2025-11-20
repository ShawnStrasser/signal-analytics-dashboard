"""
Custom exception types shared across the Flask app.
"""

class InvalidQueryParameter(ValueError):
    """Raised when a user-supplied query parameter is invalid or unsafe."""

