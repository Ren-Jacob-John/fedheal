# Every-Sprint Checklist — Do's and Don'ts

This checklist applies to **every sprint**, not just the current one. Review it before starting a sprint and again before closing it out. Nothing here is optional or "nice to have" — treat every unchecked box as unfinished work.

---

## ❌ Don't (design/content — avoid looking "vibe coded")

- [ ] No purple gradients
- [ ] No pill-shaped buttons
- [ ] No fake reviews or testimonials
- [ ] No fake metrics/stats
- [ ] No vague hero text (be specific about what the product does)
- [ ] No emoji used as icons
- [ ] No em dashes in copy
- [ ] No excessive scroll animations
- [ ] No AI-slop stock photos or generic AI-generated imagery
- [ ] No AI-slop copywriting (generic, filler marketing text)
- [ ] No custom cursor animations
- [ ] No fake counters (e.g. "X users joined today")
- [ ] Remove any "Made with AI" badge/tag

## ✅ Do — Legal & Compliance

- [ ] Privacy Policy page exists and is linked (e.g. footer)
- [ ] Terms & Conditions page exists and is linked
- [ ] Cookie consent banner implemented

## ✅ Do — Security

- [ ] No secrets, API keys, or credentials in frontend code/bundle
- [ ] HTTPS enforced (HTTP redirects to HTTPS)
- [ ] Spam protection on public forms (captcha/honeypot/rate limiting)

## ✅ Do — SEO & Discoverability

- [ ] Meta titles set on every page
- [ ] Meta descriptions set on every page
- [ ] Social preview image (OG image) configured
- [ ] Favicon added
- [ ] `sitemap.xml` generated
- [ ] `robots.txt` added

## ✅ Do — Accessibility & Media

- [ ] Alt text added on all images
- [ ] Images compressed/optimized
- [ ] Color contrast checked and fixed (WCAG AA minimum)

## ✅ Do — Performance & Responsiveness

- [ ] Page load speed checked (Lighthouse/PageSpeed) and acceptable
- [ ] Site is mobile-friendly / responsive

## ✅ Do — Reliability & UX

- [ ] Custom 404 page added
- [ ] All links checked, no broken links
- [ ] Form validation implemented (client + server side)
- [ ] Error handling implemented across the app
- [ ] Loading states implemented for async actions
- [ ] Empty states implemented where data can be absent
- [ ] Failed network/API requests handled gracefully (retries/user feedback)

## ✅ Do — Analytics & Conversion

- [ ] Analytics set up and tracking correctly
- [ ] Each page has one clear, unambiguous call-to-action

## ✅ Do — Backend / Database

- [ ] DB queries optimized (no N+1, unnecessary joins, etc.)
- [ ] DB indexes added where needed

## ✅ Do — Quality Bar

- [ ] **No mistakes** — this is the top priority. Double-check everything before marking the sprint done: no typos, no broken functionality, no regressions, no half-finished features shipped.

---

*Keep this file updated. If a new rule is added for future sprints, add it here so it applies retroactively to review checklists.*
