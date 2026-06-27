"""
risk_engine.py
--------------
Stage 5 Risk Engine. Implements mathematical position sizing,
automatic stop-loss/take-profit boundaries, and downside protection filters.
"""

from typing import Dict, Union

def calculate_position_size(
    account_balance: float,
    current_price: float,
    win_probability: float,
    risk_per_trade: float = 0.02
) -> Dict[str, Union[str, int, float]]:
    """
    Calculates institutional position sizing using a fixed-fractional risk model.

    Args:
        account_balance: Total account value in cash
        current_price: Entry price per share/unit
        win_probability: Model confidence score (0.0 to 1.0)
        risk_per_trade: Fraction of account to risk (default 2%)

    Returns:
        Dictionary with action, quantity, and risk parameters
    """
    # Safety Check: Reject if confidence below threshold
    if win_probability < 0.60:
        return {
            "action": "HOLD",
            "reason": f"Confidence score ({round(win_probability * 100, 1)}%) below threshold (0.60).",
            "quantity": 0,
            "actual_risk": 0.0,
            "stop_loss": 0.0,
            "take_profit": 0.0,
            "total_transaction_value": 0.0,
            "risk_reward_ratio": 0.0
        }

    # 1. Quantify total capital exposure risk allowed
    max_risk_cash = account_balance * risk_per_trade

    # 2. Determine structural market exits (Technical buffers)
    stop_loss_pct = 0.02
    take_profit_pct = 0.06

    stop_loss_price = current_price * (1.0 - stop_loss_pct)
    take_profit_price = current_price * (1.0 + take_profit_pct)

    # Risk per single share in absolute cash terms
    risk_per_share = current_price - stop_loss_price
    reward_per_share = take_profit_price - current_price

    if risk_per_share <= 0:
        return {
            "action": "HOLD",
            "reason": "Invalid risk per share calculation.",
            "quantity": 0,
            "actual_risk": 0.0,
            "stop_loss": 0.0,
            "take_profit": 0.0,
            "total_transaction_value": 0.0,
            "risk_reward_ratio": 0.0
        }

    # 3. Calculate quantity using Fixed Fractional formula
    target_quantity = int(max_risk_cash // risk_per_share)
    total_transaction_value = target_quantity * current_price
    actual_risk = target_quantity * risk_per_share
    potential_reward = target_quantity * reward_per_share

    if target_quantity <= 0:
        return {
            "action": "HOLD",
            "reason": "Sizing engine generated zero shares within current risk boundaries.",
            "quantity": 0,
            "actual_risk": 0.0,
            "stop_loss": round(stop_loss_price, 2),
            "take_profit": round(take_profit_price, 2),
            "total_transaction_value": 0.0,
            "risk_reward_ratio": round(potential_reward / actual_risk, 2) if actual_risk > 0 else 0.0
        }

    return {
        "action": "ENTER",
        "quantity": target_quantity,
        "entry_price": round(current_price, 2),
        "stop_loss": round(stop_loss_price, 2),
        "take_profit": round(take_profit_price, 2),
        "actual_risk": round(actual_risk, 2),
        "total_transaction_value": round(total_transaction_value, 2),
        "risk_reward_ratio": round(potential_reward / actual_risk, 2),
        "reason": "Position validated by fixed-fractional allocation model."
    }

if __name__ == "__main__":
    res = calculate_position_size(account_balance=10000.0, current_price=100.0, win_probability=0.65)
    print(f"Risk Matrix Sizing Audit: {res}")