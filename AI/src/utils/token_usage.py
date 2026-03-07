"""Token usage estimation and cost calculation utilities."""
from typing import Dict, Optional
import re

# Model pricing per 1M tokens (as of 2024)
MODEL_PRICING = {
    "gpt-4o": {
        "input": 5.00,   # $5.00 per 1M input tokens
        "output": 15.00  # $15.00 per 1M output tokens
    },
    "gpt-4-turbo": {
        "input": 10.00,
        "output": 30.00
    },
    "gpt-4o-mini": {
        "input": 0.15,
        "output": 0.60
    },
    "text-embedding-3-small": {
        "input": 0.02,   # $0.02 per 1M tokens
        "output": 0.0
    },
    "text-embedding-ada-002": {
        "input": 0.10,
        "output": 0.0
    }
}


def estimate_tokens(text: str) -> int:
    """Estimate token count for a given text.
    
    Uses approximation: ~4 characters per token for English text.
    For more accurate estimation, tiktoken can be used if available.
    
    Args:
        text: Input text to estimate tokens for
    
    Returns:
        Estimated token count
    """
    if not text:
        return 0
    
    # Try to use tiktoken for accurate estimation if available
    try:
        import tiktoken
        # gpt-4o uses cl100k_base encoding
        encoding = tiktoken.get_encoding("cl100k_base")
        return len(encoding.encode(str(text)))
    except ImportError:
        # Fallback: approximate using character count
        # Average: ~4 characters per token for English text
        # This is a rough approximation
        text_str = str(text)
        # Count words and add some overhead for punctuation/special chars
        word_count = len(text_str.split())
        char_count = len(text_str)
        # Use average of word-based and char-based estimation
        estimated = max(word_count * 1.3, char_count / 4)
        return int(estimated)


def estimate_dict_tokens(data: dict) -> int:
    """Estimate tokens for a dictionary by converting to string.
    
    Args:
        data: Dictionary to estimate tokens for
    
    Returns:
        Estimated token count
    """
    if not data:
        return 0
    
    # Convert dict to JSON-like string for estimation
    import json
    try:
        json_str = json.dumps(data, indent=2)
        return estimate_tokens(json_str)
    except (TypeError, ValueError):
        # Fallback to string representation
        return estimate_tokens(str(data))


class TokenUsageTracker:
    """Track token usage across multiple LLM calls."""
    
    def __init__(self):
        """Initialize token usage tracker."""
        self.usage_by_chain: Dict[str, Dict[str, int]] = {}
        self.total_input_tokens = 0
        self.total_output_tokens = 0
    
    def add_usage(
        self,
        chain_name: str,
        model: str,
        input_tokens: int,
        output_tokens: int
    ):
        """Add token usage for a chain call.
        
        Args:
            chain_name: Name of the chain (e.g., "pattern_analysis")
            model: Model name (e.g., "gpt-4o")
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
        """
        if chain_name not in self.usage_by_chain:
            self.usage_by_chain[chain_name] = {
                "model": model,
                "input_tokens": 0,
                "output_tokens": 0,
                "calls": 0
            }
        
        self.usage_by_chain[chain_name]["input_tokens"] += input_tokens
        self.usage_by_chain[chain_name]["output_tokens"] += output_tokens
        self.usage_by_chain[chain_name]["calls"] += 1
        
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
    
    def estimate_chain_usage(
        self,
        chain_name: str,
        model: str,
        input_text: str,
        output_text: str
    ):
        """Estimate and track token usage for a chain.
        
        Args:
            chain_name: Name of the chain
            model: Model name
            input_text: Input text (can be str or dict)
            output_text: Output text
        """
        # Estimate input tokens
        if isinstance(input_text, dict):
            input_tokens = estimate_dict_tokens(input_text)
        else:
            input_tokens = estimate_tokens(str(input_text))
        
        # Estimate output tokens
        output_tokens = estimate_tokens(str(output_text))
        
        self.add_usage(chain_name, model, input_tokens, output_tokens)
    
    def calculate_costs(self) -> Dict[str, float]:
        """Calculate costs for all tracked usage.
        
        Returns:
            Dictionary with cost breakdown
        """
        total_cost = 0.0
        costs_by_chain = {}
        
        for chain_name, usage in self.usage_by_chain.items():
            model = usage["model"]
            input_tokens = usage["input_tokens"]
            output_tokens = usage["output_tokens"]
            
            # Get pricing for model
            pricing = MODEL_PRICING.get(model, MODEL_PRICING["gpt-4o"])
            
            # Calculate cost
            input_cost = (input_tokens / 1_000_000) * pricing["input"]
            output_cost = (output_tokens / 1_000_000) * pricing["output"]
            chain_cost = input_cost + output_cost
            
            costs_by_chain[chain_name] = {
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "input_cost_usd": round(input_cost, 6),
                "output_cost_usd": round(output_cost, 6),
                "total_cost_usd": round(chain_cost, 6),
                "calls": usage["calls"]
            }
            
            total_cost += chain_cost
        
        # Calculate total cost
        total_pricing = MODEL_PRICING.get("gpt-4o", MODEL_PRICING["gpt-4o"])
        total_input_cost = (self.total_input_tokens / 1_000_000) * total_pricing["input"]
        total_output_cost = (self.total_output_tokens / 1_000_000) * total_pricing["output"]
        
        return {
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_tokens": self.total_input_tokens + self.total_output_tokens,
            "total_cost_usd": round(total_input_cost + total_output_cost, 6),
            "breakdown_by_chain": costs_by_chain
        }
    
    def get_summary(self) -> Dict:
        """Get summary of token usage and costs.
        
        Returns:
            Dictionary with usage summary
        """
        costs = self.calculate_costs()
        return {
            "token_usage": {
                "total_input_tokens": costs["total_input_tokens"],
                "total_output_tokens": costs["total_output_tokens"],
                "total_tokens": costs["total_tokens"]
            },
            "cost_estimate": {
                "total_cost_usd": costs["total_cost_usd"],
                "breakdown_by_chain": costs["breakdown_by_chain"]
            }
        }

