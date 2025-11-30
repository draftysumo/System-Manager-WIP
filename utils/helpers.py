"""
Utility functions for data conversion and formatting.
"""

def human_readable_size(size_bytes):
    """
    Convert a size in bytes to a human-readable string (e.g., 1024 -> 1.00 KiB).
    
    Args:
        size_bytes (int): The size in bytes.
        
    Returns:
        str: The human-readable string representation.
    """
    if size_bytes is None or size_bytes < 0:
        return '0 B'
        
    # Ensure it's treated as an integer for comparison
    size_bytes = int(size_bytes)
    
    if size_bytes == 0:
        return '0 B'
    
    # Use powers of 1024 (KiB, MiB, GiB, etc.)
    units = ('B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB', 'EiB', 'ZiB', 'YiB')
    
    i = 0
    # Loop until we find the appropriate unit
    # Note: size_bytes must be float here for accurate division
    size_float = float(size_bytes)

    while size_float >= 1024 and i < len(units) - 1:
        size_float /= 1024.0
        i += 1
        
    return f"{size_float:.2f} {units[i]}"

# If you need to expose this function via the 'utils' package, you might 
# also add 'from .helpers import human_readable_size' to utils/__init__.py.