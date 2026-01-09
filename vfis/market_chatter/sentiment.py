"""
Sentiment analysis engine for market chatter.

Implements hybrid sentiment analysis:
- Phase 1: Rule-based lexicon with financial polarity weighting
- Phase 2: FinBERT (optional, auto-detected if available)
"""

import logging
import re
from typing import Dict, Tuple, Optional
from collections import Counter

logger = logging.getLogger(__name__)

# Try to import FinBERT (optional)
try:
    from transformers import AutoTokenizer, AutoModelForSequenceClassification
    import torch
    FINBERT_AVAILABLE = True
    logger.info("FinBERT available - will use for sentiment analysis")
except ImportError:
    FINBERT_AVAILABLE = False
    logger.info("FinBERT not available - using rule-based sentiment analysis only")


# Financial lexicon with polarity scores (-1.0 to +1.0)
FINANCIAL_LEXICON = {
    # Positive terms
    "bullish": 0.8, "surge": 0.7, "rally": 0.7, "gains": 0.6, "profit": 0.6,
    "growth": 0.6, "strong": 0.5, "beat": 0.7, "exceed": 0.6, "outperform": 0.7,
    "upgrade": 0.6, "buy": 0.5, "positive": 0.5, "outstanding": 0.6,
    "improvement": 0.5, "expansion": 0.5, "revenue": 0.3, "earnings": 0.3,
    "dividend": 0.4, "acquisition": 0.4, "partnership": 0.4,
    
    # Negative terms
    "bearish": -0.8, "plunge": -0.7, "crash": -0.8, "loss": -0.6, "decline": -0.6,
    "weak": -0.5, "miss": -0.7, "downgrade": -0.6, "sell": -0.5, "negative": -0.5,
    "concern": -0.4, "risk": -0.4, "volatility": -0.3, "uncertainty": -0.4,
    "debt": -0.3, "losses": -0.6, "declining": -0.5, "disappointing": -0.6,
    "lawsuit": -0.7, "scandal": -0.8, "bankruptcy": -0.9, "delisting": -0.8,
    
    # Neutral/context-dependent
    "stable": 0.2, "maintain": 0.1, "hold": 0.0, "neutral": 0.0,
}

# Financial negation patterns
NEGATION_PATTERNS = [
    r"not\s+\w+",
    r"no\s+\w+",
    r"never\s+\w+",
    r"can't\s+\w+",
    r"won't\s+\w+",
    r"doesn't\s+\w+",
    r"isn't\s+\w+",
    r"aren't\s+\w+",
]


class SentimentAnalyzer:
    """
    Hybrid sentiment analyzer with rule-based and FinBERT options.
    """
    
    def __init__(self):
        """Initialize sentiment analyzer."""
        self.finbert_model = None
        self.finbert_tokenizer = None
        self._initialize_finbert()
    
    def _initialize_finbert(self):
        """Initialize FinBERT model if available."""
        if not FINBERT_AVAILABLE:
            return
        
        try:
            model_name = "ProsusAI/finbert"
            logger.info(f"Loading FinBERT model: {model_name}")
            self.finbert_tokenizer = AutoTokenizer.from_pretrained(model_name)
            self.finbert_model = AutoModelForSequenceClassification.from_pretrained(model_name)
            self.finbert_model.eval()  # Set to evaluation mode
            logger.info("FinBERT model loaded successfully")
        except Exception as e:
            logger.warning(f"Failed to load FinBERT model: {e}. Using rule-based only.")
            self.finbert_model = None
            self.finbert_tokenizer = None
    
    def analyze(self, text: str, use_finbert: bool = True) -> Dict[str, float]:
        """
        Analyze sentiment of text.
        
        Args:
            text: Text to analyze
            use_finbert: Whether to use FinBERT if available (default: True)
            
        Returns:
            Dictionary with:
            - sentiment_score: float between -1.0 and +1.0
            - sentiment_label: "positive", "neutral", or "negative"
            - confidence: float between 0.0 and 1.0
        """
        if not text or not text.strip():
            return {
                "sentiment_score": 0.0,
                "sentiment_label": "neutral",
                "confidence": 0.0
            }
        
        # Try FinBERT first if available and requested
        if use_finbert and self.finbert_model and self.finbert_tokenizer:
            try:
                finbert_result = self._analyze_with_finbert(text)
                if finbert_result:
                    return finbert_result
            except Exception as e:
                logger.warning(f"FinBERT analysis failed: {e}. Falling back to rule-based.")
        
        # Fall back to rule-based analysis
        return self._analyze_rule_based(text)
    
    def _analyze_with_finbert(self, text: str) -> Optional[Dict[str, float]]:
        """
        Analyze sentiment using FinBERT.
        
        Args:
            text: Text to analyze
            
        Returns:
            Sentiment result dictionary or None if analysis fails
        """
        try:
            # Tokenize and encode
            inputs = self.finbert_tokenizer(
                text[:512],  # FinBERT max length
                return_tensors="pt",
                truncation=True,
                padding=True,
                max_length=512
            )
            
            # Get predictions
            with torch.no_grad():
                outputs = self.finbert_model(**inputs)
                predictions = torch.nn.functional.softmax(outputs.logits, dim=-1)
            
            # FinBERT labels: [positive, negative, neutral]
            positive_score = predictions[0][0].item()
            negative_score = predictions[0][1].item()
            neutral_score = predictions[0][2].item()
            
            # Convert to -1.0 to +1.0 scale
            sentiment_score = positive_score - negative_score
            
            # Determine label
            if sentiment_score > 0.15:
                sentiment_label = "positive"
            elif sentiment_score < -0.15:
                sentiment_label = "negative"
            else:
                sentiment_label = "neutral"
            
            # Confidence is the distance from neutral
            confidence = abs(sentiment_score)
            
            return {
                "sentiment_score": round(sentiment_score, 3),
                "sentiment_label": sentiment_label,
                "confidence": round(confidence, 3)
            }
            
        except Exception as e:
            logger.error(f"Error in FinBERT analysis: {e}", exc_info=True)
            return None
    
    def _analyze_rule_based(self, text: str) -> Dict[str, float]:
        """
        Analyze sentiment using rule-based lexicon.
        
        Args:
            text: Text to analyze
            
        Returns:
            Sentiment result dictionary
        """
        text_lower = text.lower()
        words = re.findall(r'\b\w+\b', text_lower)
        
        # Check for negation patterns
        has_negation = any(re.search(pattern, text_lower) for pattern in NEGATION_PATTERNS)
        
        # Calculate sentiment score
        scores = []
        for word in words:
            if word in FINANCIAL_LEXICON:
                score = FINANCIAL_LEXICON[word]
                # Flip score if negation detected
                if has_negation and score != 0:
                    score = -score * 0.5  # Reduce magnitude for negated sentiment
                scores.append(score)
        
        if not scores:
            return {
                "sentiment_score": 0.0,
                "sentiment_label": "neutral",
                "confidence": 0.3
            }
        
        # Average score, normalized to -1.0 to +1.0
        avg_score = sum(scores) / len(scores)
        # Clip to valid range
        sentiment_score = max(-1.0, min(1.0, avg_score))
        
        # Determine label
        if sentiment_score > 0.2:
            sentiment_label = "positive"
        elif sentiment_score < -0.2:
            sentiment_label = "negative"
        else:
            sentiment_label = "neutral"
        
        # Confidence based on absolute score magnitude
        confidence = min(0.9, abs(sentiment_score) * 1.5)
        
        return {
            "sentiment_score": round(sentiment_score, 3),
            "sentiment_label": sentiment_label,
            "confidence": round(confidence, 3)
        }


def analyze_sentiment(text: str, use_finbert: bool = True) -> Dict[str, float]:
    """
    Convenience function to analyze sentiment.
    
    Args:
        text: Text to analyze
        use_finbert: Whether to use FinBERT if available
        
    Returns:
        Sentiment result dictionary
    """
    analyzer = SentimentAnalyzer()
    return analyzer.analyze(text, use_finbert=use_finbert)

