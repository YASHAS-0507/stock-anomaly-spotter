from typing import Dict, Union, List

def generate_decision_reason(
    probabilities: Dict[str, float],
    latest_features: Dict[str, float]
) -> Dict[str, Union[str, List[str]]]:
    """
    Generates human-readable explanations for ML model trading decisions.
    Uses case-insensitive key scanning to prevent feature mismatch issues.

    Args:
        probabilities: Dict with keys "spike_up", "spike_down", "sideways" (values 0.0-1.0)
        latest_features: Dict of current indicator values from the Feature Store

    Returns:
        Dict with primary signal, confidence rating, and reasoning chain
    """
    reasoning_chain = []

    # Safe float mapping from incoming prediction weights
    spike_up = float(probabilities.get("spike_up", 0.0))
    spike_down = float(probabilities.get("spike_down", 0.0))
    sideways = float(probabilities.get("sideways", 0.0))

    # Evaluate absolute signal dominant direction
    max_prob = max(spike_up, spike_down, sideways)

    if spike_up == max_prob:
        primary_signal = "BUY"
    elif spike_down == max_prob:
        primary_signal = "SHORT"
    else:
        primary_signal = "HOLD"

    confidence_rating = f"{(max_prob * 100):.1f}%"

    # Normalize incoming feature store keys to lowercase to ensure robust lookup matches
    normalized_features = {str(k).lower().replace("_", " "): float(v) for k, v in latest_features.items()}

    # Extract indicators dynamically using fallback searches
    rsi = 50.0
    for k, v in normalized_features.items():
        if "rsi" in k:
            rsi = v
            break

    relative_volume = 1.0
    for k, v in normalized_features.items():
        if "volume" in k or "vol" in k:
            relative_volume = v
            break

    # Construct the explainability reasoning chains
    if primary_signal == "BUY":
        if rsi < 35:
            reasoning_chain.append("RSI Oversold Condition Detected")
        if rsi < 30:
            reasoning_chain.append("Extreme Oversold Momentum")
        if relative_volume > 1.5:
            reasoning_chain.append("Substantial Institutional Volume Spike")
        if relative_volume > 2.0:
            reasoning_chain.append("Significant Liquidity Influx")

    elif primary_signal == "SHORT":
        if rsi > 65:
            reasoning_chain.append("RSI Overbought Condition Detected")
        if rsi > 70:
            reasoning_chain.append("Extreme Overbought Momentum")
        if relative_volume > 1.5:
            reasoning_chain.append("Distribution Volume Detected")
        if relative_volume > 2.0:
            reasoning_chain.append("Aggressive Selling Pressure")

    else:  # HOLD
        if 35 <= rsi <= 65:
            reasoning_chain.append("Market in Neutral Equilibrium")
        if relative_volume < 0.8:
            reasoning_chain.append("Reduced Volume Profile")

    # Final fallback safety check to keep frontend arrays populated
    if not reasoning_chain:
        reasoning_chain.append("No Strong Technical Deviation Present")

    return {
        "primary_signal": str(primary_signal),
        "confidence_rating": str(confidence_rating),
        "reasoning_chain": reasoning_chain
    }

if __name__ == "__main__":
    # Internal text execution test validating localized key structures
    probs = {"spike_up": 0.874, "spike_down": 0.08, "sideways": 0.046}
    features = {"rsi_14": 28.5, "volume_relative": 1.8}
    result = generate_decision_reason(probs, features)
    print(f"Explainability Audit Output: {result}")