# Notion space

Two connectors read one Notion workspace. Access is the connector credential, not a document-set group.

Use a **new** read-only Notion internal integration. Read content only. Do not reuse the existing `RevOps | Dev` integration. Put that new token in `NOTION_INTEGRATION_TOKEN` for the Hub connector. Each Informatics viewer creates their own credential with the same integration after they are briefly an admin. See the runbook in `gtm/qm/INTEGRATION.md`.

## Hub

Page `Revenue Operations`, id `1cd17a7f-1e33-4794-a832-05ef95ab2a60`.

The Hub connector is PUBLIC. Every `pushpress.com` Google user who can sign in to Onyx can read it. The crawl starts at this page and follows children. It excludes Informatics, so that subtree is not in the public index.

```
Revenue Operations
  ICP
  Personas
  Messaging
  Battlecards
  Pricing
  Objections
  Playbooks
    SDR
    AE
    CS
    Manager
  Case studies
  Release notes
  Informatics          excluded from the Hub crawl
```

Share this page with the new integration.

## Informatics

Page id `408233ce-1c17-81e4-a92f-e23cc8bb95fd`. It sits under the Hub. It holds sales compensation and Kevin's personal pages.

The Informatics connector is PRIVATE. It is paired once per viewer, each pair using that person's Notion credential. Visible only to:

- kevin.williams@pushpress.com
- garrick.iwamoto@pushpress.com
- ian.chand@pushpress.com
- jessica.xu@pushpress.com  # TODO confirm

Gavin, Nathan Hemphill, and the rest of the sales team get the Hub only.

Keep this page out of every public document set. The GTM Informatics set is not public. The Informatics agent is shared only with those four emails.

## Hub page headings

### ICP

- Firmographics
- Must-have
- Disqualifiers
- Segments

### Personas

One child page per buyer.

- Role
- Jobs to be done
- Pains
- What they need to hear
- Who else is in the deal

### Messaging

- Category line
- Problem
- Promise
- Proof points
- Words we use
- Words we avoid

### Battlecards

One child page per competitor.

- Their claim
- Our answer
- Proof
- Question to ask
- Landmines

### Pricing

- Packages
- What is included
- Rules a rep must follow
- What a rep must not offer

### Objections

- They say
- We answer
- Proof
- Role that hears it

### Playbooks

Child pages: SDR, AE, CS, and Manager.

- Goal of the motion
- Steps
- Required questions
- Definition of done
- Handoff

### Case studies

- Customer type
- Problem
- What they used
- Outcome
- What a rep may quote

### Release notes

- Date
- What shipped
- Who it is for
- What we do not claim yet

## After you turn exclusion on

Start the Hub index fresh, or confirm that Informatics documents no longer have PUBLIC access. A page indexed by the old public crawl can stay readable until that check. Pruning of those already-public pages was not verified in this tree.
