# Portal Message Routing Protocol (internal, front desk / triage staff)

Community Women's Health & Family Clinic. Applies to non-urgent patient-portal messages only
(urgent messages are filtered out before they reach this inbox). Every message goes to exactly
ONE queue. Apply the rules **in order; the first rule that matches wins**. Language does not change
routing: a Spanish message goes where the same English message would.

"Patient" = the person the chart belongs to. For a baby/child, the parent or legal guardian writing
about the child counts as the patient's own voice (not a third party).

## Rules

1. **Outside agencies and professionals -> family_services.** If the writer identifies themselves as
   writing *for an organization* about a patient — caseworker, CPS/DCFS/DHS, foster or adoption
   agency, guardian ad litem, court/probation/juvenile liaison, attorney or public defender, police
   victim advocate, shelter or refugee-resettlement case manager, school social worker, home-visiting
   program staff (Nurse-Family Partnership, Healthy Families, Early Head Start), community doula
   program, tribal or kinship-care navigator — route to family_services **whatever they ask for**
   (records, bills, refills, appointments, formula, forms). Family services verifies the
   authorization/court order and coordinates. Outside *medical* offices and pharmacies are not
   agencies for this rule.

2. **Someone else asking for an adult patient's clinical information -> records.** A partner, spouse,
   ex, parent of an adult patient, sibling, friend, roommate, or other relative asking to be told
   results, diagnoses, due dates, blood type, or what happened/was decided at a visit goes to
   records (they must have an authorization or proxy on file before anyone discusses it). The same
   applies to grandparents/uncles/others asking about a baby's results or visits — only the baby's
   parent/guardian is exempt. Family members asking for *logistics* (reschedule, pay a bill, order a
   pump) are not covered by this rule; route by topic.

3. **Breast pumps -> lactation.** Anything about a breast pump — getting one, the prescription or
   letter of medical necessity, insurance coverage, prior authorization, DME supplier bills and
   orders, rentals of hospital-grade pumps, parts, returns, pickup, flange fit, how/how often to
   pump — goes to lactation, before or after delivery, even when it reads like a billing question.

4. **Infant formula -> family_services.** Anything about formula — which formula, switching or
   mixing, amounts, preparation, spit-up/gas on formula, shortages, samples, cost help, nutrition
   program formula benefits, specialty/hypoallergenic formula prescriptions, the program's medical
   documentation form, formula prior authorizations, daycare notes about special formula. The
   nutrition program dietitians own all formula decisions, including the paperwork.

5. **Coverage, eligibility and program services -> family_services.** Getting or keeping coverage
   (Medicaid/pregnancy Medicaid application, renewal, denial, postpartum coverage ending, CHIP,
   marketplace), **adding a newborn to insurance**, the sliding-fee / financial-assistance program
   (any request for a discount based on income, even mixed with a payment-plan request), birth
   certificate and Social Security number help, nutrition-program enrollment/benefits, and
   **scheduling or rescheduling nutrition-program appointments and home visits**, plus community
   resources (housing, food, diapers, transport, safety, support groups for parents). Note: once a
   patient simply *has* a new card to put on file, that is rule 6, not this rule.

6. **Registration updates and bills from other organizations -> front_desk.**
   (a) New or changed insurance card / member ID / secondary insurance, address, phone, legal name,
   emergency contact. (b) Any bill, EOB or collections notice that comes from **another
   organization** — the hospital where they delivered, NICU, anesthesia, outside labs
   (Quest, LabCorp, pathology, genetic-testing companies), outside imaging centers, specialists we
   referred to, ambulance, birth centers. We do not bill those services; the front desk gives the
   patient the right contact using the redirect script. Billing_insurance only handles our own
   charges.

7. **Paperwork a clinician must complete or sign -> nurse_line.** FMLA, disability/SDI, paid family
   leave, work notes and work restrictions, return-to-work/exercise clearance, jury duty letters,
   airline/travel letters, pregnancy verification letters (employer, housing authority,
   unemployment), school absence notes, parking placard applications, daycare health
   forms/statements needing a provider signature — including status of such a form. (A fee charged
   for a form is rule 13; a formula form is rule 4.)

8. **Immunization record printouts -> front_desk.** Requests for a copy/printout of vaccines given
   here (baby shot record, state immunization form, Tdap/flu/COVID record) are printed from the
   state registry by the front desk — not records. (If a daycare form must be *signed*, rule 7.)

9. **Medication requests -> nurse_line.** Refills, new prescription requests, prescriptions not
   received at the pharmacy, pharmacy changes, and **medication prior authorizations** (PAs are done
   by nurses, not billing) — even when the medication is lactation-related (domperidone, APNO cream,
   nystatin for thrush, reglan for supply) or the patient mentions breastfeeding in the same message.

10. **Breastfeeding topics BEFORE delivery -> front_desk.** While still pregnant, breastfeeding
    questions (other than pumps, rule 3) are handled in the free prenatal breastfeeding class; the
    front desk books/changes the class and the prenatal lactation intake. This includes clinical-
    sounding questions (flat nipples, breast reduction, colostrum, nursing a toddler while
    pregnant, whether the class is covered).

11. **Breastfeeding topics AFTER delivery -> lactation.** Latch, pain, supply, engorgement, mastitis-
    type symptoms, milk storage, weaning, nursing strikes, breastfed-baby weight gain/stool
    questions, whether a medication, vaccine, food/drink or procedure is safe while nursing (with no
    refill/prescription request — see rule 9), and **scheduling or rescheduling lactation
    consults** and the breastfeeding support group. (A charge for a lactation visit is rule 13.)

12. **Records -> records.** Copies of the chart, ultrasound reports and images, sending records or
    results to another provider/insurer/third party with a signed release, checking whether records
    arrived, corrections/amendments to the chart, **portal proxy access** (baby's portal, giving a
    partner access) and authorization forms / authorized-contact changes, visit notes, growth
    charts.

13. **Our own charges -> billing_insurance.** Statements, copays, payment plans (without an income
    discount request), refunds, receipts, itemized bills, claim denials/rebilling for services done
    here, whether we accept a plan, estimates of what a visit here will cost, coding questions, and
    any charge already on our statement whatever it was for (no-show fees, lactation visits, form
    fees, records-copy fees, nurse calls).

14. **Other non-urgent clinical questions -> nurse_line.** Test-result questions and result timing,
    pregnancy/postpartum symptoms, mood, newborn concerns that are not about feeding, vaccine
    reactions, "is it safe to…" during pregnancy.

15. **Everything else -> front_desk.** Scheduling regular prenatal, postpartum and well-baby visits,
    cancellations, late arrivals, hours, directions/parking, portal login and app problems,
    interpreter or provider preferences, complaints and compliments.

## Public queue descriptions

- front_desk — appointments, registration, and general questions about the clinic
- nurse_line — non-urgent clinical requests: prescription refills, test results, clinical forms
- billing_insurance — bills, payments, and insurance questions
- records — medical records requests and copies
- lactation — breastfeeding and lactation support
- family_services — social work, community resources, and the nutrition program
