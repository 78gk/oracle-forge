"""Normalize dates across different formats and database systems."""

from datetime import datetime, date
from typing import Union, Optional, Tuple
import re
from dateutil import parser

class DateNormalizer:
    """
    Normalize date strings to ISO format (YYYY-MM-DD) for cross-database joins.
    
    Handles:
    - Multiple input formats (YYYY-MM-DD, MM/DD/YYYY, DD/MM/YYYY, etc.)
    - Date ranges and comparisons
    - Fiscal year calculations
    - Week-based joins
    """
    
    # Common date format patterns
    FORMAT_PATTERNS = [
        (r'(\d{4})-(\d{2})-(\d{2})', 'iso'),           # 2026-04-12
        (r'(\d{2})/(\d{2})/(\d{4})', 'us_slash'),      # 04/12/2026  (MM/DD — US default)
        (r'(\d{2})\.(\d{2})\.(\d{4})', 'eu_dot'),      # 04.12.2026  (DD.MM — European)
        (r'(\d{4})/(\d{2})/(\d{2})', 'iso_slash'),     # 2026/04/12
        (r'(\w+)\s+(\d{1,2}),?\s+(\d{4})', 'month'),   # April 12, 2026
        (r'(\d{1,2})\s+(\w+)\s+(\d{4})', 'day_month'), # 12 April 2026
    ]
    
    def __init__(self, default_fiscal_year_start: Tuple[int, int] = (7, 1)):  # July 1
        self.fiscal_year_start = default_fiscal_year_start
        self._parser = parser
    
    def to_iso(self, date_input: Union[str, datetime, date]) -> str:
        """
        Convert any date input to ISO format string (YYYY-MM-DD).
        
        Examples:
            "04/12/2026" -> "2026-04-12"
            "April 12, 2026" -> "2026-04-12"
            "2026-04-12" -> "2026-04-12"
        """
        if isinstance(date_input, datetime):
            return date_input.date().isoformat()
        if isinstance(date_input, date):
            return date_input.isoformat()
        if isinstance(date_input, str):
            return self._parse_string_to_iso(date_input)
        return str(date_input)
    
    def _parse_string_to_iso(self, date_str: str) -> str:
        """Parse string date using patterns, fallback to dateutil."""
        date_str = date_str.strip()
        
        for pattern, format_type in self.FORMAT_PATTERNS:
            match = re.match(pattern, date_str, re.IGNORECASE)
            if match:
                if format_type == 'iso':
                    return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
                elif format_type == 'us_slash':
                    # MM/DD/YYYY → YYYY-MM-DD
                    return f"{match.group(3)}-{match.group(1)}-{match.group(2)}"
                elif format_type == 'eu_dot':
                    # DD.MM.YYYY → YYYY-MM-DD
                    return f"{match.group(3)}-{match.group(2)}-{match.group(1)}"
                elif format_type == 'iso_slash':
                    return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
                elif format_type == 'month':
                    month_num = self._month_name_to_number(match.group(1))
                    return f"{match.group(3)}-{month_num:02d}-{int(match.group(2)):02d}"
                elif format_type == 'day_month':
                    month_num = self._month_name_to_number(match.group(2))
                    return f"{match.group(3)}-{month_num:02d}-{int(match.group(1)):02d}"
        
        # Fallback to dateutil parser
        try:
            dt = parser.parse(date_str)
            return dt.date().isoformat()
        except (ValueError, OverflowError):
            return date_str
    
    def _month_name_to_number(self, month_name: str) -> int:
        """Convert month name to number."""
        months = {
            'january': 1, 'february': 2, 'march': 3, 'april': 4,
            'may': 5, 'june': 6, 'july': 7, 'august': 8,
            'september': 9, 'october': 10, 'november': 11, 'december': 12
        }
        return months.get(month_name.lower(), 1)
    
    def normalize_for_join(self, left_date: str, right_date: str) -> Tuple[str, str]:
        """Normalize both dates to ISO for equality comparison."""
        return self.to_iso(left_date), self.to_iso(right_date)
    
    def same_week(self, date1: str, date2: str) -> bool:
        """Check if two dates fall in the same calendar week."""
        iso1 = self.to_iso(date1)
        iso2 = self.to_iso(date2)
        dt1 = datetime.fromisoformat(iso1)
        dt2 = datetime.fromisoformat(iso2)
        # ISO week definition
        return dt1.isocalendar().year == dt2.isocalendar().year and \
               dt1.isocalendar().week == dt2.isocalendar().week
    
    def get_fiscal_year(self, date_str: str) -> int:
        """
        Get fiscal year for a given date.
        Fiscal year starts on July 1 (configurable).
        """
        iso_date = self.to_iso(date_str)
        dt = datetime.fromisoformat(iso_date)
        year = dt.year
        month = dt.month
        
        if month >= self.fiscal_year_start[0]:
            return year + 1
        return year
    
    def to_fiscal_period(self, date_str: str) -> str:
        """Convert date to fiscal period string (e.g., 'FY2025-Q1')."""
        iso_date = self.to_iso(date_str)
        dt = datetime.fromisoformat(iso_date)
        fy = self.get_fiscal_year(date_str)
        
        # Adjust month for fiscal quarters
        adj_month = (dt.month - self.fiscal_year_start[0]) % 12
        quarter = (adj_month // 3) + 1
        
        return f"FY{fy}-Q{quarter}"