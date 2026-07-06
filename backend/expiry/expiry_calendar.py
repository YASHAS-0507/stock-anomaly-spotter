"""
expiry_calendar.py
------------------
Tracks NSE F&O expiry dates and provides expiry context for risk management.

NSE weekly expiry:  every Thursday
NSE monthly expiry: last Thursday of month

On expiry days:
- Higher intraday volatility and volume
- Gamma-driven moves near large OI strikes
- Pinning behavior toward max pain (soft attractor)
- More false breakouts and reversals

Risk approach: conservative, not exploitative.
Reduce position size, tighten daily limits.
Do NOT try to trade expiry-specific patterns.
"""

import datetime


class ExpiryCalendar:
    """
    Tracks NSE F&O expiry dates and provides
    expiry context for risk management.
    """

    # NSE holidays 2026 (add all known)
    NSE_HOLIDAYS_2026 = [
        "2026-01-26",  # Republic Day
        "2026-02-26",  # Mahashivratri
        "2026-03-25",  # Holi
        "2026-04-02",  # Ram Navami
        "2026-04-03",  # Good Friday
        "2026-04-14",  # Dr. Ambedkar Jayanti
        "2026-05-01",  # Maharashtra Day
        "2026-08-15",  # Independence Day
        "2026-10-02",  # Gandhi Jayanti
        "2026-10-20",  # Dussehra
        "2026-11-04",  # Diwali Laxmi Puja
        "2026-11-05",  # Diwali Balipratipada
        "2026-11-25",  # Guru Nanak Jayanti
        "2026-12-25",  # Christmas
    ]

    def __init__(self):
        self._holiday_set = set(self.NSE_HOLIDAYS_2026)
        self._expiry_cache = {}

    def is_trading_day(self, date=None) -> bool:
        """
        Returns True if NSE is open on given date.
        date: datetime.date object or None (uses today)
        """
        if date is None:
            date = datetime.date.today()
        if date.weekday() >= 5:  # Saturday=5, Sunday=6
            return False
        if date.strftime("%Y-%m-%d") in self._holiday_set:
            return False
        return True

    def is_weekly_expiry(self, date=None) -> bool:
        """
        Returns True if date is a weekly expiry day.
        NSE weekly expiry = every Thursday.
        If Thursday is holiday, expiry moves to Wednesday.
        """
        if date is None:
            date = datetime.date.today()

        # Check if it's Thursday
        if date.weekday() == 3:  # Thursday
            if self.is_trading_day(date):
                return True

        # Check if Thursday was holiday and today is Wednesday
        if date.weekday() == 2:  # Wednesday
            thursday = date + datetime.timedelta(days=1)
            if not self.is_trading_day(thursday):
                return True

        return False

    def is_monthly_expiry(self, date=None) -> bool:
        """
        Returns True if date is monthly expiry.
        NSE monthly expiry = last Thursday of the month.
        If last Thursday is holiday → last Wednesday.
        """
        if date is None:
            date = datetime.date.today()

        # Find last Thursday of this month
        year = date.year
        month = date.month

        # Last day of month
        if month == 12:
            last_day = datetime.date(year + 1, 1, 1) - \
                       datetime.timedelta(days=1)
        else:
            last_day = datetime.date(year, month + 1, 1) - \
                       datetime.timedelta(days=1)

        # Walk back to find last Thursday
        days_back = (last_day.weekday() - 3) % 7
        last_thursday = last_day - \
                        datetime.timedelta(days=days_back)

        # If last Thursday is holiday, use Wednesday
        if not self.is_trading_day(last_thursday):
            last_thursday -= datetime.timedelta(days=1)

        return date == last_thursday

    def get_expiry_context(self, date=None) -> dict:
        """
        Returns full expiry context for a given date.

        Returns:
        {
          "is_expiry_day": bool,
            True if weekly OR monthly expiry

          "is_weekly_expiry": bool,
          "is_monthly_expiry": bool,

          "expiry_type": str,
            "NONE" | "WEEKLY" | "MONTHLY"

          "days_to_next_expiry": int,
            How many trading days until next expiry

          "risk_multiplier": float,
            Position size multiplier for today
            NONE: 1.0 (normal)
            WEEKLY: 0.75 (reduce by 25%)
            MONTHLY: 0.60 (reduce by 40%)

          "daily_loss_multiplier": float,
            Daily loss limit multiplier
            NONE: 1.0
            WEEKLY: 0.75
            MONTHLY: 0.65

          "max_trades_today": int,
            Maximum trades allowed today
            NONE: unlimited (system default)
            WEEKLY: 6
            MONTHLY: 4

          "avoid_after": str,
            Time after which no new entries on expiry
            NONE: "14:45" (normal)
            WEEKLY: "14:00" (earlier cutoff)
            MONTHLY: "13:30" (even earlier)

          "setup_restrictions": list,
            Setups to disable or tighten on expiry
            NONE: []
            WEEKLY: ["NEWS_CATALYST after 14:00"]
            MONTHLY: ["NEWS_CATALYST", reduced ORB]

          "reason": str,
            Human readable explanation
        }
        """
        if date is None:
            date = datetime.date.today()

        weekly = self.is_weekly_expiry(date)
        monthly = self.is_monthly_expiry(date)
        is_expiry = weekly or monthly

        if monthly:
            expiry_type = "MONTHLY"
            risk_mult = 0.60
            loss_mult = 0.65
            max_trades = 4
            avoid_after = "13:30"
            restrictions = [
                "NEWS_CATALYST disabled after 13:00",
                "ORB_BREAKOUT requires 2x volume confirmation",
                "No new positions after 13:30"
            ]
            reason = "Monthly F&O expiry: high gamma, " \
                     "reduced position sizes and earlier cutoff"
        elif weekly:
            expiry_type = "WEEKLY"
            risk_mult = 0.75
            loss_mult = 0.75
            max_trades = 6
            avoid_after = "14:00"
            restrictions = [
                "NEWS_CATALYST disabled after 14:00"
            ]
            reason = "Weekly F&O expiry (Thursday): " \
                     "elevated volatility, conservative sizing"
        else:
            expiry_type = "NONE"
            risk_mult = 1.0
            loss_mult = 1.0
            max_trades = 999
            avoid_after = "14:45"
            restrictions = []
            reason = "Normal trading day"

        # Calculate days to next expiry
        days_to_next = self._days_to_next_expiry(date)

        return {
            "is_expiry_day":         is_expiry,
            "is_weekly_expiry":      weekly,
            "is_monthly_expiry":     monthly,
            "expiry_type":           expiry_type,
            "days_to_next_expiry":   days_to_next,
            "risk_multiplier":       risk_mult,
            "daily_loss_multiplier": loss_mult,
            "max_trades_today":      max_trades,
            "avoid_after":           avoid_after,
            "setup_restrictions":    restrictions,
            "reason":                reason,
        }

    def _days_to_next_expiry(self, from_date) -> int:
        """
        Returns number of trading days until next expiry.
        Searches forward up to 15 days.
        """
        for i in range(1, 15):
            check = from_date + datetime.timedelta(days=i)
            if self.is_weekly_expiry(check) or \
               self.is_monthly_expiry(check):
                # Count only trading days
                trading_days = 0
                d = from_date + datetime.timedelta(days=1)
                while d <= check:
                    if self.is_trading_day(d):
                        trading_days += 1
                    d += datetime.timedelta(days=1)
                return trading_days
        return 99  # no expiry found in window


# Module-level singleton
expiry_calendar = ExpiryCalendar()
