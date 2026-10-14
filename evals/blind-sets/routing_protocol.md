# Inbound Message Routing Protocol (internal)

Non-urgent messages from patients and families. Medical messages have already been filtered out
upstream. Every message goes to exactly ONE queue.

## Public queue descriptions (what a new hire sees)

- care_coordinator — your overall care plan and team
- billing — payments and bills
- scheduling — booking and changing appointments
- doula_support — questions for and about your doula
- community_resources — help with baby supplies, food, housing and other needs

## Rules

**Precedence: apply the rules in order. The FIRST rule that matches decides the queue.**
A message that touches two topics is routed by whichever matching rule has the lower number.

1. **Third-party sender → care_coordinator, regardless of topic.** If the message is written by
   anyone other than the patient (partner, spouse, parent, in-law, sibling, friend, roommate,
   child typing for a parent) about the patient, it goes to care_coordinator, because a release of
   information must be checked before anyone acts. This applies even to "simple" asks like moving
   an appointment, paying a bill, a thank-you, or announcing a birth. A patient who mentions their
   partner in their own message is still the sender — this rule does not apply.

2. **Leaving, pausing, or changing the care relationship → care_coordinator.** Withdrawing from the
   program, cancelling the whole package or all remaining visits, putting services on hold, ending
   the contract early (including any refund requested as part of leaving), asking for a different
   doula, asking for an additional/backup doula to be assigned, or any complaint or discomfort about
   a doula's conduct. (Not doula_support: the doula is never the one to triage a complaint about
   herself or a reassignment.)

3. **Insurance, Medicaid, CHIP, OHP or any coverage question → care_coordinator, NOT billing.**
   Coverage, eligibility, enrollment, renewal letters, termination letters, prior authorization,
   denied claims, EOBs, new member IDs, copays that conflict with the plan, and any paperwork or
   statement that will be sent to an insurer. Applies even when the message is about a bill or
   balance, and even when it asks for a letter or form, as long as the purpose is coverage.

4. **Birth timeline events → doula_support.** A new or changed due date, an induction or
   cesarean date being set, moved or cancelled, heading in for a planned induction, or the baby
   having arrived. The on-call doula rotation needs this first. This wins over scheduling even when
   the message also asks to cancel or move visits — doula_support adjusts the visits itself.

5. **No-show, late-cancellation and lateness fees → scheduling, NOT billing.** Any question,
   dispute, waiver request, refund request or policy question about a missed-visit / no-show /
   late-cancel / late-arrival fee. The scheduling lead owns fee waivers because they hold the
   attendance record.

6. **Sliding scale, discounts and financial hardship → community_resources, NOT billing.** Sliding-
   scale applications and tiers, fee waivers, bill forgiveness, scholarships, hardship funds,
   income limits, and any discount program (student, military, shelter). Applies even when the
   patient says they can't pay their bill.

7. **Group classes, workshops and support circles → community_resources, NOT scheduling.**
   Registering, cancelling a spot, switching sessions, waitlists, class times/locations, class Zoom
   links, who may attend. The community team runs all group programming. (One-on-one visits are
   rule 11.)

8. **Transportation → community_resources.** Rides to any visit or class, ride-service problems,
   bus passes, gas cards, taxi vouchers, parking validation or reimbursement for travel costs
   (even though a "reimbursement" sounds like billing).

9. **Changes to the patient record → billing.** Address, phone, email, name or name spelling,
   chosen name, pronouns, date of birth, preferred language, preferred contact method, emergency
   contact. Billing owns the patient master record.

10. **Letters, notes and forms for outside parties → scheduling.** The scheduling team is also the
    front desk: employer letters, work or school excuse notes, proof of enrollment or attendance,
    FMLA/leave forms, letters for landlords, housing or childcare-subsidy applications, courts or
    probation — including forms the patient wants their doula to sign. (Exceptions are already
    handled above: insurance paperwork is rule 3. Payment receipts and superbills for HSA/FSA or
    taxes are ordinary billing, rule 12.)

11. **Default — one-on-one visits → scheduling.** Booking, moving, cancelling or confirming an
    individual prenatal or postpartum visit, availability, visit format (home/office/virtual),
    reminders, video-visit links.

12. **Default — money → billing.** Balances, invoices, statements, payments, payment methods,
    payment plans, autopay, duplicate charges, overpayment refunds, deposits, prices, gift
    certificates, receipts, superbills and itemized statements for HSA/FSA or tax records.

13. **Default — the doula's role and relationship → doula_support.** What the doula does, birth
    plans, what to pack, how and when to reach the doula, partner involvement, comfort measures,
    preparation tips, and thank-yous, gifts or photos for a doula.

14. **Default — practical needs → community_resources.** Car seats, cribs, strollers, diapers,
    formula, clothes, food, WIC/SNAP sign-up, housing, rent or utility help, childcare, phones,
    laundry, legal aid referrals.
