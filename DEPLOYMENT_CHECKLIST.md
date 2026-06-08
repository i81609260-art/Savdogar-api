# Savdogar Deployment Checklist

Print this and check off each step as you complete it!

---

## PHASE 1: FRONTEND DEPLOYMENT (Day 1)

### Vercel Setup
- [ ] Create Vercel account (vercel.com)
- [ ] Connect GitHub account to Vercel
- [ ] Select `Savdogar-frontend` repository
- [ ] Set environment variables:
  - [ ] `NEXT_PUBLIC_API_URL` = your Railway backend URL
  - [ ] `NEXT_PUBLIC_SOCKET_URL` = your Railway backend URL
- [ ] Deploy to production
- [ ] Verify deployment successful
- [ ] Test frontend loads at vercel domain

### DNS Configuration (if using custom domain)
- [ ] Update DNS CNAME to Vercel
- [ ] Wait for DNS propagation (5-30 minutes)
- [ ] Test: `https://your-domain.com` loads

---

## PHASE 2: BACKEND VERIFICATION (Day 1)

### Railway Health Check
- [ ] Log in to Railway dashboard
- [ ] Check `Savdogar-backend` project status
- [ ] Verify all environment variables are set:
  - [ ] `DATABASE_URL`
  - [ ] `JWT_SECRET_KEY`
  - [ ] `GOOGLE_GEMINI_API_KEY`
  - [ ] `CLICK_API_KEY`
  - [ ] `PAYME_API_KEY`
  - [ ] `TELEGRAM_BOT_TOKEN`
  - [ ] `CORS_ORIGINS`
- [ ] Test API health endpoint: `curl https://api.your-domain.com/health`
- [ ] Check recent logs for errors

---

## PHASE 3: CORE WORKFLOW TESTING (Day 2)

### CRM Request Flow
- [ ] Open frontend in browser
- [ ] Navigate to `/constructor` (tour wizard)
- [ ] Complete all 6 steps
  - [ ] Step 1: Select destination
  - [ ] Step 2: Select group type & size
  - [ ] Step 3: Select dates
  - [ ] Step 4: Select hotel rating
  - [ ] Step 5: Select meal plan
  - [ ] Step 6: Select tour type
- [ ] Enter lead information:
  - [ ] Full name
  - [ ] Phone number
  - [ ] Email address
- [ ] Click "Submit"
- [ ] Verify success message appears
- [ ] Navigate to `/admin/requests`
- [ ] Verify new request appears in list
- [ ] Click request to view details
- [ ] Verify all information is correct

### Pricing Calculator
- [ ] Open request details page
- [ ] Scroll to pricing section
- [ ] Verify price is calculated
- [ ] Change parameters (hotel rating, meal plan)
- [ ] Verify price updates automatically

### Tour Creation
- [ ] Open request details
- [ ] Click "Create Tour"
- [ ] Fill in tour details:
  - [ ] Title
  - [ ] Description
  - [ ] Duration
  - [ ] Available dates
- [ ] Submit
- [ ] Verify tour created and appears in tours list

---

## PHASE 4: PAYMENT TESTING (Day 3)

### Click Payment Setup
- [ ] Go to `/admin/payment-setup`
- [ ] Add Click merchant credentials (use test credentials)
- [ ] Create a test booking
- [ ] Select Click payment method
- [ ] Verify Click payment page loads
- [ ] Complete test payment
- [ ] Check backend logs for webhook notification
- [ ] Verify booking status changes to "paid"

### Payme Payment Setup
- [ ] Go to `/admin/payment-setup`
- [ ] Add Payme merchant credentials (use test credentials)
- [ ] Create a test booking
- [ ] Select Payme payment method
- [ ] Verify Payme payment page loads
- [ ] Complete test payment
- [ ] Check backend logs for webhook notification
- [ ] Verify booking status changes to "paid"

---

## PHASE 5: AI FEATURES TESTING (Day 3)

### Natural Language Parser
- [ ] Navigate to `/constructor/ai`
- [ ] Enter test request in Uzbek:
  - Example: "4 kishiga 10-15 aprel kuniga Dubayga 5 kun turni qidiryapman"
- [ ] Click submit
- [ ] Verify request is parsed correctly
- [ ] Check that destination, dates, group size extracted
- [ ] Verify request appears in CRM

### AI Bot Chat
- [ ] Navigate to `/admin/ai-bot`
- [ ] Ask bot a question about tours
  - Example: "Misr turlar qanday?"
- [ ] Verify bot responds with tour information
- [ ] Test multiple questions
- [ ] Verify no errors in console

### Website Analysis
- [ ] In AI bot page, test website analysis feature
- [ ] Enter website URL
- [ ] Wait for analysis to complete
- [ ] Verify tour packages are generated
- [ ] Check quality of generated packages

---

## PHASE 6: REAL-TIME FEATURES (Day 4)

### WebSocket Updates
- [ ] Open `/admin/requests` in 2 browser windows (side by side)
- [ ] In window 1, open a request
- [ ] In window 1, change request status
- [ ] In window 2, verify request list updates WITHOUT refresh
- [ ] Check browser console - no WebSocket errors

### Live Notifications
- [ ] While logged in as admin, have someone submit new request
- [ ] Verify new request notification appears in real-time
- [ ] Verify no page refresh needed to see new request

---

## PHASE 7: ANALYTICS TESTING (Day 4)

### Dashboard
- [ ] Navigate to `/admin/analytics`
- [ ] Verify dashboard loads without errors
- [ ] Check metric cards display:
  - [ ] Total requests
  - [ ] Conversion rate
  - [ ] ROI
  - [ ] Average booking value
- [ ] Verify numbers are accurate

### Conversion Funnel
- [ ] Scroll to conversion funnel section
- [ ] Verify funnel chart displays
- [ ] Verify numbers match requests created

### ROI Analysis
- [ ] Scroll to ROI section
- [ ] Verify breakdown by tour type
- [ ] Verify breakdown by destination

---

## PHASE 8: LOCALIZATION TESTING (Day 5)

### Language Settings
- [ ] Navigate to `/admin/settings/language`
- [ ] Change language to English
- [ ] Verify UI text changes to English
- [ ] Change language to Russian
- [ ] Verify UI text changes to Russian
- [ ] Change language back to Uzbek
- [ ] Verify UI text changes back to Uzbek

### Timezone
- [ ] Change timezone setting
- [ ] Create a request
- [ ] Verify dates are displayed in correct timezone

### Currency
- [ ] Change currency to USD
- [ ] Verify prices display in USD
- [ ] Change currency to EUR
- [ ] Verify prices display in EUR

---

## PHASE 9: WHITE-LABEL TESTING (Day 5)

### Branding
- [ ] Navigate to `/admin/settings/white-label`
- [ ] Upload custom logo
- [ ] Change primary color
- [ ] Change secondary color
- [ ] Verify changes apply to admin panel
- [ ] Verify changes apply to customer-facing pages

### Custom Domain
- [ ] Enter custom domain (if available)
- [ ] Update DNS CNAME
- [ ] Verify domain resolves correctly
- [ ] Verify SSL certificate is valid

### API Key
- [ ] Generate new API key
- [ ] Copy key
- [ ] Verify key can be used for API calls
- [ ] Generate new key to rotate old one

---

## PHASE 10: TELEGRAM MINI APP (Day 6)

### Setup
- [ ] Navigate to `/admin/telegram-setup`
- [ ] Copy Mini App URL
- [ ] Log in to BotFather
- [ ] Create test bot (or use existing)
- [ ] Set Web App URL to mini app URL
- [ ] Save and test in Telegram

### Testing in Telegram
- [ ] Open Telegram bot
- [ ] Click Web App button
- [ ] Verify mini app loads
- [ ] Verify tour list displays
- [ ] Click on tour
- [ ] Verify tour details load
- [ ] Try to make booking
- [ ] Verify booking created successfully

---

## PERFORMANCE TESTING (Day 6)

### Frontend Performance
- [ ] Open DevTools → Network tab
- [ ] Check page load time
  - [ ] Target: < 3 seconds
  - [ ] Actual: _______
- [ ] Check bundle size
  - [ ] Target: < 200KB
  - [ ] Actual: _______
- [ ] Test on slow 3G (DevTools → Network throttling)
- [ ] Verify still usable on slow connection

### Backend Performance
- [ ] Test API response time:
  ```
  curl -o /dev/null -w "%{time_total}\n" https://api.your-domain.com/api/requests
  ```
  - [ ] Target: < 200ms
  - [ ] Actual: _______
- [ ] Load test with concurrent requests
  ```
  ab -n 100 -c 10 https://api.your-domain.com/api/requests
  ```
  - [ ] All requests succeed: YES / NO
  - [ ] Response time under load: _______

---

## SECURITY TESTING (Day 7)

### Authentication
- [ ] Try to access admin pages without login
- [ ] Verify redirected to login page
- [ ] Login with correct credentials
- [ ] Verify can access admin pages
- [ ] Login with incorrect credentials
- [ ] Verify error message shown
- [ ] Test token refresh: keep app open 1+ hour
- [ ] Verify still logged in

### Authorization
- [ ] Login as regular user
- [ ] Try to access superadmin pages
- [ ] Verify access denied
- [ ] Try to modify other company's requests
- [ ] Verify access denied

### Data Protection
- [ ] Check sensitive data not in logs
- [ ] Verify HTTPS enforced everywhere
- [ ] Test SQL injection in search
- [ ] Verify no injection errors
- [ ] Test XSS in request notes
- [ ] Verify no XSS issues

---

## DATABASE TESTING (Day 7)

### Backup
- [ ] Verify daily backups enabled in Railway
- [ ] Test restore procedure (in staging if possible)
- [ ] Verify data integrity after restore

### Migrations
- [ ] Check all migrations applied successfully
- [ ] Review database schema
- [ ] Verify all tables created

### Performance
- [ ] Check slow query logs
- [ ] Verify indexes on commonly filtered columns
- [ ] Test with sample data (100+ records)
- [ ] Verify query performance acceptable

---

## GO-LIVE READINESS (Day 8)

### Final Checks
- [ ] All tests passing: YES / NO
- [ ] No critical bugs found: YES / NO
- [ ] Performance acceptable: YES / NO
- [ ] Security review complete: YES / NO
- [ ] Database backups working: YES / NO
- [ ] Monitoring configured: YES / NO
- [ ] Support team trained: YES / NO
- [ ] Documentation complete: YES / NO

### Production Deployment
- [ ] Announce scheduled maintenance (if needed)
- [ ] Final backend verification
- [ ] Final frontend verification
- [ ] Create backup of production database
- [ ] Monitor for errors for first 24 hours
- [ ] Announce go-live to users

---

## DAY 1 PRODUCTION MONITORING

### Every 30 minutes:
- [ ] Check backend health: `curl https://api.your-domain.com/health`
- [ ] Check frontend loads: visit https://your-domain.com
- [ ] Check for error alerts in monitoring
- [ ] Check Payment gateway webhooks received

### Every 2 hours:
- [ ] Review error logs
- [ ] Check performance metrics
- [ ] Verify database responding
- [ ] Test key workflows (CRM, payments)

### Daily (7 days):
- [ ] Monitor uptime (target: 99.9%)
- [ ] Monitor error rate (target: < 0.1%)
- [ ] Monitor API response time (target: < 200ms)
- [ ] Check user feedback
- [ ] Review analytics

---

## SIGN-OFF

- **Tested By:** _________________
- **Date Deployed:** _________________
- **Go-Live Confirmed:** YES / NO
- **Issues Discovered:** (list below)

```
1. ___________________________________
2. ___________________________________
3. ___________________________________
```

---

**CONGRATULATIONS! 🎉 You've successfully deployed Savdogar to production!**

For ongoing support, refer to NEXT_STEPS.md and IMPLEMENTATION_SUMMARY.md
