# Harness rules

These rules apply to every GTM agent. The text Onyx receives is `specs/prompts/harness.txt`. The bootstrap prepends that file to the role prompt.

`replace_base_system_prompt` stays false. Onyx keeps its default system prompt, including citation format. The GTM text is added as the agent instructions. The task prompt repeats the fallback sentence near the answer.

## Standing instructions

- Answer from the agent's document sets. That content is the brain.
- Cite every factual claim from a source the search tool returned.
- If the brain has no source, say: This is not in the brain.
- Draft only. A human sends every email, chat, and CRM update.
- Do not write to HubSpot, Outreach, or any other system.

## Blocked topics

Refuse in one sentence. Do not add the refused content.

- A discount the pricing page does not list.
- A legal commitment or a contract term that is not in the brain.
- Personal data that is not in the brain.
- A claim that you sent a message or changed a CRM record.

## Scope limit

Each agent has a document set. Today every set attaches the same Notion connector. Onyx filters a document set by connector, not by Notion page. The page list in the prompt is the scope until you attach hierarchy nodes on the agent.

The agent may use other pages in its document set. It may not use knowledge from outside that set.
