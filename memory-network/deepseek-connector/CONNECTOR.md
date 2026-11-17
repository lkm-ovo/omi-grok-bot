# Deepseek

- `custom.deepseek` connects Muse to Deepseek through the Deepseek REST API and calls only `api.deepseek.com`.

- It authenticates with the registered `api_key` credential and sends the key as a bearer header.

- Helpers live in `~/workspace/custom-connectors/custom.deepseek/bin/deepseek.py` and cover listing models and chat completions.

## Connect

- Register the connection with `credentials.request_api_access` and reuse these details to reconnect.

```json
{
  "provider": "deepseek",
  "auth_scheme": "api_key",
  "placement": "bearer_header",
  "api_hosts": ["api.deepseek.com"]
}
```

- Prove access before the first change in a conversation with a harmless read.

```text
python3 ~/workspace/custom-connectors/custom.deepseek/bin/deepseek.py models
```

- The read was verified on 2026-11-17 and returned two models.

## Credentials

- The registered connection holds the credential. Helpers import `/opt/muse/skills/custom-connector-setup/bin/dynamic_credentials.py`, which returns an `hsurr:` surrogate and places it where the provider reads the key. Muse swaps in the real credential only on an approved request to a registered host.

- Never put a key, token, password or cookie in this doc, a helper, a command argument, an environment variable or a log. Never ask the user to paste one in chat.

- Keep redirects disabled on authenticated requests.

- On a 401 or 403, check the request first. Confirm that the helper attached the credential, that the host is registered and that the placement and scopes match.

- Only when a request that carried the credential is still rejected, call `credentials.request_api_access` with the details above and `"reconnect": true`.

## List models

- List the models on the account when you need a valid model name before a chat call.

```text
python3 ~/workspace/custom-connectors/custom.deepseek/bin/deepseek.py models
```

- Read the `id` field of each entry in `data` and use one of those ids as the chat model.

- Verified on 2026-11-17. The account returned `deepseek-flash` and `deepseek-v4-pro`, each with a context window of 1048576 and a max output of 393216 tokens.

## Send a chat completion

- Send a chat completion when you need Deepseek to write, summarize or extract text.

```text
python3 ~/workspace/custom-connectors/custom.deepseek/bin/deepseek.py chat --model deepseek-flash --message "hello" --max-tokens 800
```

- Pass the model with `--model` and the user text with `--message`.

- Pass an optional system prompt with `--system` and an optional temperature with `--temperature`.

- Read the assistant text from `choices[0].message.content` and the token counts from `usage`.

- Verified on 2026-11-17 with `deepseek-flash`. The call returned a chat completion with `finish_reason` set to `stop`.

## Recover from errors

- A 401 or 403 means the credential was missing, wrong or not attached. Check the helper attached the credential and the host is registered before you retry.

- A 429 means the account hit a rate limit. Wait and retry the same read once, then stop and tell the user if it still fails.

- After a failed or timed-out change, check the current state with a read before trying again, because the first request may have completed.

## Limits

- The connector only calls `api.deepseek.com` and only covers the two operations above.

- Any other Deepseek endpoint is untested. Do not claim it works until you run it and record the result here.

## Related skills

- Use `muse.skill_search` to find other skills and `muse.connector_search` to find other connectors.
