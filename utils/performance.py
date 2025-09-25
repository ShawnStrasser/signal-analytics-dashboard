"""
Performance monitoring and logging utilities
"""

import time
import functools
from datetime import datetime
from typing import Callable, Any, Optional


class PerformanceLogger:
    """Performance logger that prints timing information to terminal."""
    
    def __init__(self, enabled: bool = True):
        self.enabled = enabled
    
    def log(self, message: str, duration: float = None, level: str = "INFO"):
        """Log a performance message to terminal."""
        if not self.enabled:
            return
            
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]  # milliseconds
        if duration is not None:
            print(f"[{timestamp}] {level}: {message} - {duration:.3f}s")
        else:
            print(f"[{timestamp}] {level}: {message}")
    
    def time_function(self, func_name: str = None):
        """Decorator to time function execution."""
        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            def wrapper(*args, **kwargs) -> Any:
                if not self.enabled:
                    return func(*args, **kwargs)
                
                name = func_name or func.__name__
                start_time = time.perf_counter()
                
                try:
                    result = func(*args, **kwargs)
                    end_time = time.perf_counter()
                    duration = end_time - start_time
                    self.log(f"Function '{name}' completed", duration)
                    return result
                    
                except Exception as e:
                    end_time = time.perf_counter()
                    duration = end_time - start_time
                    self.log(f"Function '{name}' failed: {str(e)}", duration, "ERROR")
                    raise
                    
            return wrapper
        return decorator
    
    def time_block(self, description: str):
        """Context manager to time a block of code."""
        return TimedBlock(self, description, verbose=False)


class TimedBlock:
    """Context manager for timing code blocks."""
    
    def __init__(self, logger: PerformanceLogger, description: str, verbose: bool = True):
        self.logger = logger
        self.description = description
        self.verbose = verbose
        self.start_time = None
    
    def __enter__(self):
        if self.logger.enabled:
            self.start_time = time.perf_counter()
            if self.verbose:
                self.logger.log(f"Starting: {self.description}")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.logger.enabled and self.start_time is not None:
            end_time = time.perf_counter()
            duration = end_time - self.start_time
            
            if exc_type is None:
                if self.verbose:
                    self.logger.log(f"Completed: {self.description}", duration)
                else:
                    self.logger.log(f"{self.description}", duration)
            else:
                self.logger.log(f"Failed: {self.description} - {str(exc_val)}", duration, "ERROR")


# Global performance logger instance
perf_logger = PerformanceLogger(enabled=True)

# Convenience functions for easier usage
def time_function(func_name: str = None):
    """Decorator to time function execution."""
    return perf_logger.time_function(func_name)

def time_block(description: str):
    """Context manager to time a block of code."""
    return perf_logger.time_block(description)

def log_performance(message: str, duration: float = None, level: str = "INFO"):
    """Log a performance message."""
    perf_logger.log(message, duration, level)

def enable_performance_logging(enabled: bool = True):
    """Enable or disable performance logging."""
    perf_logger.enabled = enabled