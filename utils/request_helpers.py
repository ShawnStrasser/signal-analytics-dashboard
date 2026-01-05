"""
Request parameter helpers for handling both GET and POST methods.
"""

from flask import request


def get_request_param(name, default=None):
    """
    Get a single parameter value from either GET query params or POST JSON body.
    Automatically handles both request methods.
    """
    if request.method == 'POST':
        payload = request.get_json(silent=True)
        if not payload:
            return default
        return payload.get(name, default)
    return request.args.get(name, default)


def get_request_param_list(name):
    """
    Get a list of parameter values from either GET query params or POST JSON body.
    Automatically handles both request methods.
    
    For GET requests, expects comma-separated values (e.g., signal_ids=A,B,C).
    """
    if request.method == 'POST':
        payload = request.get_json(silent=True)
        if not payload:
            return []
        value = payload.get(name)
        if value is None:
            return []
        if isinstance(value, (list, tuple, set)):
            return list(value)
        # Handle comma-separated string in POST body
        if isinstance(value, str):
            return [v.strip() for v in value.split(',') if v.strip()]
        return [value]
    
    # For GET requests, expect comma-separated values
    raw_value = request.args.get(name)
    if not raw_value:
        return []
    
    return [v.strip() for v in raw_value.split(',') if v.strip()]
