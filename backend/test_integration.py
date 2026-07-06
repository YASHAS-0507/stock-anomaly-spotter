"""
test_integration.py
-------------------
End-to-end integration test for the full intraday pipeline.
Runs without Angel One connection — uses synthetic data fallback.
"""

import os
import time
import datetime
from datetime import timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))


def test_full_pipeline():
    print("=" * 50)
    print("INTEGRATION TEST — Full Pipeline")
    print("=" * 50)

    # Test 1: Scanner
    print("\n[1] Scanner...")
    from scanner.market_scanner import MarketScanner
    scanner = MarketScanner()
    results = scanner.scan()
    assert len(results) > 0
    print(f"    PASS: {len(results)} stocks selected")
    print(f"    Top 3: {[r['ticker'] for r in results[:3]]}")

    # Test 2: Intelligence (offline safe)
    print("\n[2] Intelligence layer...")
    from intelligence.market_mood import MarketMood
    from intelligence.sentiment_cache import SentimentCache
    mood = MarketMood()
    result = mood.get_mood()
    assert 'vix' in result
    cache = SentimentCache()
    cache.set('RELIANCE.NS', {'action': 'NORMAL',
              'intelligence_score': 60}, ttl_minutes=7)
    assert cache.is_fresh('RELIANCE.NS')
    print(f"    PASS: VIX={result['vix']} "
          f"regime={result['vix_regime']}")

    # Test 3: Feature engineering
    print("\n[3] Feature engineering...")
    from indicators.intraday_features import IntradayFeatures
    import random
    random.seed(42)
    base = 1303.50
    bt = time.time() - 200 * 300

    def make_candles(n, tf):
        candles = []
        p = base
        for i in range(n):
            o = p
            c = o + random.uniform(-0.5, 0.5)
            h = max(o, c) + random.uniform(0, 0.3)
            l = min(o, c) - random.uniform(0, 0.3)
            v = random.randint(10000, 100000)
            candles.append({'timestamp': bt + i * tf,
                'open': o, 'high': h, 'low': l,
                'close': c, 'volume': v})
            p = c
        return candles

    c5 = make_candles(60, 300)
    c1 = make_candles(200, 60)
    features = IntradayFeatures()
    result = features.compute(c5, c1, base)
    assert len(result) > 20
    print(f"    PASS: {len(result)} features computed")
    print(f"    RSI={result['rsi_14']:.1f} "
          f"VWAP={result['vwap']:.2f}")

    # Test 4: Regime detection
    print("\n[4] Regime detection...")
    from regime.intraday_regime import IntradayRegimeDetector
    detector = IntradayRegimeDetector()
    t = datetime.datetime(2026, 7, 13, 10, 0, tzinfo=IST)
    regime = detector.detect(
        result,
        {'vix': 15.0, 'vix_regime': 'NORMAL'},
        t
    )
    assert 'regime' in regime
    assert 'trading_permitted' in regime
    print(f"    PASS: regime={regime['regime']} "
          f"trading={regime['trading_permitted']}")

    # Test 5: ML model
    print("\n[5] ML model...")
    from models.intraday_model import intraday_model
    prediction = intraday_model.predict(result)
    assert 'prob_up' in prediction
    assert 'confidence_level' in prediction
    print(f"    PASS: prob_up={prediction['prob_up']:.3f} "
          f"confidence={prediction['confidence_level']}")

    # Test 6: Decision engine
    print("\n[6] Decision engine...")
    from decisions.intraday_decision import (
        intraday_decision_engine
    )
    signal = intraday_decision_engine.generate_signal(
        ticker='RELIANCE.NS',
        features=result,
        regime=regime,
        ml_prediction=prediction,
        intelligence={'action': 'NORMAL',
                     'intelligence_score': 60},
        open_positions=0
    )
    assert 'signal' in signal
    assert signal['signal'] in ['BUY', 'HOLD', 'BLOCKED']
    print(f"    PASS: signal={signal['signal']} "
          f"score={signal['combined_score']}")

    # Test 7: Position sizer
    print("\n[7] Position sizer...")
    from risk.intraday_sizer import intraday_sizer
    sizing = intraday_sizer.calculate(
        entry_price=1303.50,
        stop_loss=1291.00,
        available_capital=100000.0,
        size_multiplier=regime['size_multiplier']
    )
    assert sizing['viable']
    print(f"    PASS: shares={sizing['shares']} "
          f"risk=₹{sizing['risk_amount']:.0f}")

    # Test 8: Paper broker
    print("\n[8] Paper broker...")
    from broker.auto_paper_broker import AutoPaperBroker
    broker = AutoPaperBroker()

    if signal['signal'] == 'BUY' and sizing['viable']:
        order = broker.execute_signal(
            {'signal': 'BUY',
             'setup_type': signal.get('setup_type', 'TEST'),
             'ticker': 'RELIANCE.NS',
             'trade_id': 'TRD-INTEGRATION-001'},
            1303.50,
            sizing
        )
        assert order['status'] == 'filled'
        print(f"    PASS: order filled at "
              f"₹{order['fill_price']:.2f}")

        closed = broker.monitor_positions(
            {'RELIANCE.NS': 1288.0}
        )
        if closed:
            print(f"    PASS: SL triggered "
                  f"pnl=₹{closed[0]['pnl']:.2f}")
    else:
        print(f"    PASS: signal={signal['signal']} "
              f"broker not called (correct)")

    # Test 9: Shadow agents
    print("\n[9] Shadow agents...")
    from shadow.shadow_manager import ShadowManager
    manager = ShadowManager()
    manager.observe(
        ticker='RELIANCE.NS',
        features=result,
        regime=regime,
        live_signal=signal['signal'],
        live_confidence=prediction['prob_up'],
        intelligence={'action': 'NORMAL',
                     'intelligence_score': 60},
        trade_id='TRD-INTEGRATION-001'
    )
    report = manager.get_weekly_report()
    assert isinstance(report, dict)
    print(f"    PASS: shadow agents observed, "
          f"report keys={list(report.keys())}")

    # Test 10: Scheduler pre-session checklist
    print("\n[10] Scheduler pre-session checklist...")
    from scheduler.market_scheduler import market_scheduler
    checklist = market_scheduler.pre_session_checklist()
    assert 'ready' in checklist
    assert 'checks' in checklist
    print(f"    PASS: ready={checklist['ready']}")
    print(f"    checks={checklist['checks']}")

    print("\n" + "=" * 50)
    print("ALL 10 INTEGRATION TESTS PASSED")
    print("System ready for live paper trading")
    print("=" * 50)


if __name__ == "__main__":
    test_full_pipeline()
