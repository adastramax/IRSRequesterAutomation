# IRSRequesterAutomation

Live IRS PIN QA workspace for requester add and deactivate flows.

## Quick Links

- `QA/README_local.md`
- `QA/SUMMARY.md`
- `QA/Maste_Prompt_LLM_QA.md`

## Current QA App

The active QA app lives in `QA/` and is the source of truth for the live Streamlit and API flows.

Main UI pages:

- Add Requester
- Deactivate Requester
- Dev Use

Current frontend behavior:

- Add Requester supports both bulk upload and manual entry
- Bulk upload uses the legacy file flow
- Manual entry uses review first, then commit
- Deactivate Requester uses the same clean operations-style workflow
- Dev Use keeps raw debug output for internal troubleshooting

For implementation details and current contracts, read `QA/SUMMARY.md` first.
