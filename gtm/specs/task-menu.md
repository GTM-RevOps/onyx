# Task menu

The menu is the task list in `gtm/config/gtm.yaml`. The bootstrap copies the first four tasks of each agent into that agent's starter messages. It also saves each task as an input prompt for the admin user who owns the API key.

Onyx stores those input prompts as private. The team sees the starter messages on the agent. Replace each `{{placeholder}}` before you send the prompt.

## SDR Helper

### SDR first-touch email

Draft a first-touch email to a `{{persona}}` at a `{{segment}}` gym. Use the messaging page. Cite each line you use. Do not send it.

### SDR objection reply

Draft a reply to this objection: `{{objection}}`. Use the objections page. Cite it. Do not send it.

### SDR account fit

Is this account in our ICP? `{{account_description}}`. Cite the ICP page. If the page does not decide it, say this is not in the brain.

### SDR call opener

Write a 30-second opener for a `{{persona}}`. Use the SDR playbook. Cite it.

## AE Deal Prep

### AE deal brief

Prepare a deal brief for `{{account}}`. Cover fit, persona, risks, and questions. Cite the ICP and battlecards. Leave stage and amount blank unless the rep supplied them.

### AE pricing explain

Explain pricing for `{{segment}}` in plain language. Cite the pricing page. Do not invent a discount.

### AE follow-up draft

Draft a follow-up after this call note: `{{note}}`. Cite any claim you take from the brain. A human sends it.

### AE competitive risk

How do we answer `{{competitor}}` on this deal? Use battlecards only. If no card names them, say this is not in the brain.

## CS Helper

### CS renewal note

Draft a renewal note for `{{account}}`. Use the CS playbook and case studies. Cite them. Do not send it.

### CS release answer

Did we ship `{{feature}}`? Answer from the release notes only. If the notes are silent, say this is not in the brain.

### CS customer reply

Draft a reply to this customer message: `{{message}}`. Do not promise a feature the release notes do not list.

### CS objection reply

The customer said: `{{objection}}`. Draft a reply from the objections page. Cite it.

## Manager

### Manager call review

Review this call summary against the `{{role}}` playbook: `{{summary}}`. List gaps. Cite the playbook.

### Manager coaching point

What should a manager coach when an SDR skips discovery? Cite the manager or SDR playbook.

### Manager commit rule

What must be true before a deal is commit? Answer from the playbooks. If they are silent, say this is not in the brain.

### Manager release brief

Summarize the latest release notes for a team meeting. Cite the notes. If there are no notes, say this is not in the brain.

## RevOps

### RevOps definition check

What is our definition of ICP and of a qualified meeting? Quote the pages. Flag conflicts.

### RevOps pricing rules

List the pricing rules a rep must follow. Cite the pricing page. Do not add a rule that is not there.

### RevOps source gap

Which of these topics have no page in the brain: ICP, personas, messaging, battlecards, pricing, objections, playbooks, case studies, release notes? Say "not in the brain" for a missing topic. Do not invent the page.

### RevOps draft update

Draft a Notion update for this decision: `{{decision}}`. Do not publish it. A human publishes it.

## Competitive Analyst

### Competitive battlecard

Give the battlecard for `{{competitor}}`: their claim, our answer, and the proof. Cite the card. If no card exists, say this is not in the brain.

### Competitive landmine

What question should we ask when `{{competitor}}` is in the deal? Cite the battlecard.

### Competitive unknown rival

How do we beat `{{competitor}}`? If no battlecard exists, say this is not in the brain.

### Competitive claim check

Is this claim safe to say: `{{claim}}`? Answer only from battlecards and messaging. Cite the page.
