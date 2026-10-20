# Project charter

<!--
  Fill this in during TC1 Step 4, from your Getting to Concreteness form.
  Later weeks' notebooks read this file and stop if it is still the template.
  That is on purpose.
-->

**Department:** Finance

**Working title:** Bifrost

---

## The problem

**Who has it?** One real role, not a department.

Financial advisors

**What are they trying to do?**

Quickly convert K-1 tax documents (PDFs) to accurate data in their core tax software

**How do they handle it today?**

Manually reviewing outputs from paid software that doesn't perform well on state and local (SALT) K-1 documents

**What does that cost — time, money, risk, or relationships?**

Hours of financial advisor time spent on manual data entry and multi-person reviews instead of tax strategy or scaling their customer base

**The problem in one sentence. No solution in it.**

Thousands of hours of financial advisor time and money is spent on manual data entry then multi-person review of tax documents

---

## Success

**What does the new world look like for that person?**

Provide the K-1, have all the data entered into their core tax software (or a format that their software can bulk import), ready to be finalized.

**How would the firm measure it? Which numbers should move?**

Hours spent on data entry/review

---

## The first product

**Your solution in one sentence.**

A tax copilot for financial advisors that processes K-1 documents, extracts accurate, verified information and integrates with CCH Axcess, helping the firm reduce 1,000's of manual data entry hours annually and reduce audit risk.

**Input → Output.** Be specific enough that someone could build it wrong and you
would notice.

| | |
| --- | --- |
| **In** | Raw Tax PDF files |
| **Out** | There will be quite a few pieces of output. See below. |
### Outputs
1. Tax form data for companies and partnerships including federal Schedule K-1s, state and local K-1 equivalent files i.e. for [UTAH 2024](https://files.tax.utah.gov/tax/forms/2024/tc-65-k1.pdf) or [UTAH 2025](https://files.tax.utah.gov/tax/forms/current/tc-65.pdf), and any attached statements or other schedules that those files point to i.e. 199A, foreign incomes, or other custom "statements". All of which should be easily exportable to an excel file. Includes but these will be defined in a more declarative way so that I can support all the possible tax documents and form fields without making L X M X N models for all the documents (L=tax form, M=tax year, N=state/jurisdiction)
  - tax year
  - state/jurisdiction
  - partnership info -- info about the corporation
    - employer identification number (EIN)
    - name
    - address
  - partner info -- info about an individual human in the partnership
    - name
    - address
    - social security number (SSN) or EIN
    - phone number
    - percent of ownership
    - limited partner? (yes/no)
    - entity code - enum of options
    - date of affliation
    - date of withdrawal
  - apportionment factors -- divvy up company assets for tax accuracy
    - property
    - payroll
    - sales
  - income, deductions, credits, losses -- lots of fields involved here, refer to PDF above or json schema I will create
2. document metadata
  - file info -- general file related info
    - doc id/filename
    - file hashes (sha256 or md5)
    - mime type
    - file size
  - document structure -- any info about the documents or sub documents in a single PDF
    - number of pages
    - forms detected i.e TC65 vs TC20 and the various schedules in the document
    - states/jurisdiction i.e. federal vs UT vs CA
    - applicable tax years
  - processing info -- info about the processing pipeline
    - timestamp
    - duration
    - processing pipeline version
    - model id/name
    - ocr engine used
---

### **Output Excel Filename Patterns**
| | |
| --- | --- |
| Template | Purpose |
| K1yyyyP.xls | Partnership K-1 data |
| K1yyyyS.xls | S Corporation K-1 data |
| K1yyyyF.xls	| Fiduciary K-1 data |
---

## Decisions made later

<!--
  Amended as the cohort goes. Keep the reasoning, not just the choice — Week 5
  asks you to defend your architecture against the options you rejected, and
  Week 10's handoff doc is largely this section.
-->

| Week | Decision | Why, and what you rejected |
| --- | --- | --- |
| 1 | Charter Inputs and Outputs | After so more talks with the stakeholders it became apparent that this would be an extract and review task instead of just review. I have no access to the extracted outputs from their existing K-1x software and it would be difficult to get access. Pluswe think this blends better with the agentic approach this course asks for. |
| 3 | Retrieval approach | <!-- TC3 --> |
| 5 | Agent architecture | <!-- TC5 --> |
| 8 | Model | <!-- TC8 --> |
