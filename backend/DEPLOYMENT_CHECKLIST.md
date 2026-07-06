# Pre-Launch Deployment Checklist

## Railway Environment Variables
- [ ] ANGEL_API_KEY set
- [ ] ANGEL_CLIENT_ID set  
- [ ] ANGEL_PASSWORD set
- [ ] ANGEL_TOTP_SECRET set
- [ ] GROQ_API_KEY set
- [ ] FRONTEND_URL set
- [ ] RAILPACK_PYTHON_VERSION=3.12

## Before Monday Market Open (9:00am IST)
- [ ] Check Railway backend is Online
- [ ] Check Railway frontend is Online
- [ ] Open dashboard — System Health shows ONLINE
- [ ] Verify FEED shows LIVE
- [ ] Check VIX on NSE website (trade smaller if > 18)
- [ ] POST /api/scheduler/start at 8:45am
- [ ] Verify scanner runs and watchlist populated
- [ ] Verify intelligence scan completes
- [ ] Angel One account has sufficient balance
- [ ] Watch first 15 minutes without trading (9:15-9:30)
- [ ] Confirm first paper trade executes after 9:30am

## Emergency Procedures
- If system behaves wrongly: 
  POST /api/scheduler/emergency-stop immediately
- If Railway goes down:
  Angel One auto-closes positions at 3:20pm anyway
- If VIX spikes above 25 mid-session:
  System auto-reduces to zero trades
- Daily loss limit ₹3,000 hit:
  System auto-stops for the day

## Daily Review (after 3:30pm)
- [ ] Check today's trades in AutoTradeLog
- [ ] Note win rate and P&L
- [ ] Write ONE new lesson learned
- [ ] Check shadow agent predictions vs outcomes
- [ ] Tune ONE parameter if needed (not more)
