"""
Decision engine for PDF enrichment.

Determines whether to replace product names and descriptions
based on quality heuristics.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from .models import NameQualityAssessment, PdfProductMatch

logger = logging.getLogger(__name__)


# Chinese color characters that indicate weak names
CHINESE_COLOR_CHARS = [
    "哑黑", "枪灰", "亮银", "古铜", "拉丝", "哑白", "亮白",
    "哑", "黑", "灰", "银", "白", "铜", "金", "红", "蓝", "绿",
]

# Color names in various languages
COLOR_NAMES = [
    "black", "white", "gray", "grey", "silver", "gold", "bronze",
    "red", "blue", "green", "yellow", "chrome", "matte", "glossy",
    "черный", "белый", "серый", "серебристый", "золотой", "бронзовый",
    "красный", "синий", "зеленый", "желтый", "хром", "матовый", "глянцевый",
]

# Product type indicators (good sign in name)
PRODUCT_TYPE_INDICATORS = [
    "смеситель", "кран", "вал", "труба", "угол", "фитинг",
    "гибка", "колено", "переход", "заглушка", "муфта", "тройник",
    "вентиль", "конус", "бочонок", "сгон", " American", "евроконус",
    "компрессионный", "цанговый", "обжимной", "фланец",
]


class NameQualityAnalyzer:
    """Analyzes quality of product names."""
    
    def assess_name_quality(self, name: Optional[str]) -> NameQualityAssessment:
        """
        Assess the quality of a product name.
        
        Returns:
            NameQualityAssessment with flags indicating quality issues
        """
        if not name:
            return NameQualityAssessment(
                is_weak=True,
                is_very_short=True,
                reasons=["empty_name"]
            )
        
        name = name.strip()
        assessment = NameQualityAssessment()
        
        # Check if name is just the SKU
        if self._is_sku_only(name):
            assessment.is_sku_only = True
            assessment.is_weak = True
            assessment.reasons.append("name_equals_sku")
        
        # Check if very short
        if len(name) < 10:
            assessment.is_very_short = True
            assessment.is_weak = True
            assessment.reasons.append(f"very_short ({len(name)} chars)")
        
        # Check if it's just a color/variant
        if self._is_color_only_name(name):
            assessment.is_color_only = True
            assessment.is_weak = True
            assessment.reasons.append("color_variant_only")
        
        # Check for garbled characters
        if self._has_garbled_chars(name):
            assessment.is_garbled = True
            assessment.is_weak = True
            assessment.reasons.append("garbled_characters")
        
        # Check for suspicious patterns
        if self._has_suspicious_patterns(name):
            assessment.is_weak = True
            assessment.reasons.append("suspicious_patterns")
        
        return assessment
    
    def _is_sku_only(self, name: str) -> bool:
        """Check if name is just a SKU code."""
        name_clean = re.sub(r"[\s\-_.]", "", name).upper()
        
        # SKU patterns: letters + digits, optionally with dash and suffix
        sku_patterns = [
            r"^[A-Z]\d{3,}$",  # G101, A1234
            r"^[A-Z]{2,}\d{2,}$",  # AB123, XY4567
            r"^[A-Z]\d{3,}-\d{1,3}[A-Z]?$",  # G101-13, G10101-2
        ]
        
        for pattern in sku_patterns:
            if re.match(pattern, name_clean):
                return True
        
        return False
    
    def _is_color_only_name(self, name: str) -> bool:
        """Check if name is just a color or variant description."""
        name_lower = name.lower()
        
        # Check for Chinese color characters
        for char in CHINESE_COLOR_CHARS:
            if char in name:
                # If name is short and contains Chinese color, it's likely just color
                if len(name) < 20:
                    return True
        
        # Check if it's just a color name
        color_words_found = []
        other_words = []
        
        words = re.findall(r'\b\w+\b', name_lower)
        for word in words:
            if word in COLOR_NAMES:
                color_words_found.append(word)
            else:
                other_words.append(word)
        
        # If only color words and very short
        if color_words_found and len(name) < 15:
            return True
        
        # If mostly color words with few other meaningful words
        if color_words_found and len(other_words) <= 1:
            return True
        
        return False
    
    def _has_garbled_chars(self, name: str) -> bool:
        """Check for garbled/encoding issue characters."""
        garbled_chars = ['╤', 'Ё', 'Є', '√', '№', 'ё', '├', '┤', '─', '│']
        garbled_count = sum(name.count(ch) for ch in garbled_chars)
        
        return garbled_count >= 2 or (garbled_count > 0 and len(name) < 20)
    
    def _has_suspicious_patterns(self, name: str) -> bool:
        """Check for suspicious patterns indicating bad data."""
        name_lower = name.lower()
        
        suspicious = [
            "каталог", "catalog",
            "стр.", "page", "лист",
            "новинки", "new products",
            "www.", "http://", "https://",
        ]
        
        for pattern in suspicious:
            if pattern in name_lower:
                return True
        
        # Check for excessive digits (likely garbled SKU data)
        digit_count = sum(c.isdigit() for c in name)
        if digit_count > len(name) * 0.6 and len(name) > 10:
            return True
        
        return False
    
    def count_product_indicators(self, name: str) -> int:
        """Count how many product type indicators are in the name."""
        name_lower = name.lower()
        count = 0
        
        for indicator in PRODUCT_TYPE_INDICATORS:
            if indicator.lower() in name_lower:
                count += 1
        
        return count


class ReplacementDecisionEngine:
    """Decides whether to replace existing name with PDF name."""
    
    def __init__(self):
        self.analyzer = NameQualityAnalyzer()
    
    def decide_name_replacement(
        self,
        old_name: str,
        pdf_match: PdfProductMatch,
        mode: str = "conservative"  # "aggressive" or "conservative"
    ) -> tuple[bool, str]:
        """
        Decide whether to replace the old name with PDF name.
        
        Args:
            old_name: Current product name
            pdf_match: Matched data from PDF
            mode: "aggressive" or "conservative"
            
        Returns:
            Tuple of (should_replace, reason)
        """
        pdf_name = pdf_match.pdf_title or ""
        
        # Safety checks
        if not pdf_name or not pdf_name.strip():
            return False, "pdf_name_empty"
        
        pdf_name = pdf_name.strip()
        
        # Always reject if PDF name is suspicious
        pdf_assessment = self.analyzer.assess_name_quality(pdf_name)
        if pdf_assessment.is_weak:
            return False, f"pdf_name_weak: {','.join(pdf_assessment.reasons)}"
        
        # Assess old name
        old_assessment = self.analyzer.assess_name_quality(old_name)
        
        # AGGRESSIVE MODE: Replace if old name is weak
        if mode == "aggressive":
            if old_assessment.needs_replacement:
                return True, f"old_name_weak: {','.join(old_assessment.reasons)}"
        
        # Always replace if old name is just SKU
        if old_assessment.is_sku_only:
            return True, "old_name_is_sku_only"
        
        # Always replace if old name is just color
        if old_assessment.is_color_only:
            return True, "old_name_is_color_only"
        
        # Always replace if old name has garbled chars
        if old_assessment.is_garbled:
            return True, "old_name_has_garbled_chars"
        
        # Compare name quality
        old_indicators = self.analyzer.count_product_indicators(old_name)
        pdf_indicators = self.analyzer.count_product_indicators(pdf_name)
        
        # If PDF name has product type info and old doesn't, use PDF
        if pdf_indicators > old_indicators:
            return True, f"pdf_has_more_product_info ({pdf_indicators} vs {old_indicators})"
        
        # If PDF name is significantly longer and has product info
        if len(pdf_name) > len(old_name) * 1.5 and pdf_indicators > 0:
            if len(pdf_name) > len(old_name) + 10:
                return True, "pdf_name_significantly_longer_and_informative"
        
        # CONSERVATIVE MODE: Don't replace if old name is decent
        if mode == "conservative":
            if not old_assessment.is_weak and old_indicators > 0:
                return False, "conservative_mode: old_name_good_enough"
        
        # If PDF name clearly better by indicators
        if pdf_indicators > old_indicators + 1:
            return True, "pdf_name_clearly_better"
        
        # Default: keep old name
        return False, "no_clear_improvement"
    
    def decide_description_update(
        self,
        old_description: Optional[str],
        pdf_match: PdfProductMatch
    ) -> tuple[bool, str]:
        """
        Decide whether to update description.
        
        Args:
            old_description: Current description (if any)
            pdf_match: Matched data from PDF
            
        Returns:
            Tuple of (should_update, reason)
        """
        pdf_description = pdf_match.pdf_description
        
        # No PDF description available
        if not pdf_description:
            return False, "no_pdf_description"
        
        pdf_description = pdf_description.strip()
        if not pdf_description:
            return False, "pdf_description_empty"
        
        # No existing description - always add
        if not old_description:
            return True, "no_existing_description"
        
        old_description = old_description.strip()
        
        # If PDF description is longer
        if len(pdf_description) > len(old_description):
            return True, "pdf_description_longer"
        
        # If PDF has additional attributes
        if pdf_match.additional_attributes:
            return True, "pdf_has_additional_attributes"
        
        return False, "existing_description_sufficient"
    
    def should_clear_enrichment_flag(
        self,
        old_name: str,
        new_name: str,
        pdf_match: PdfProductMatch
    ) -> bool:
        """
        Decide if needs_pdf_enrichment flag should be cleared.
        
        Clear the flag if:
        - Name was successfully replaced with a good name
        - Or if PDF match found but name was already good
        """
        new_assessment = self.analyzer.assess_name_quality(new_name)
        
        # Don't clear if name is still weak
        if new_assessment.needs_replacement:
            return False
        
        # Clear if we have a product indicator in the name
        indicators = self.analyzer.count_product_indicators(new_name)
        if indicators > 0:
            return True
        
        # Clear if name is reasonable length and not SKU/color only
        if len(new_name) >= 15 and not new_assessment.is_sku_only:
            return True
        
        return False