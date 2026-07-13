# Architecture

## Principle

The **Builder Bot** is a separate product. The Mafia game bot lives only under `template/mafia-bot` and is treated as an immutable source snapshot for cloning into tenant workspaces.

## Data flow

1. User pays with Telegram Stars (`XTR` invoice).
2. Platform marks subscription `active` for 30 days.
3. User sends BotFather token.
4. Platform calls Telegram `getMe`.
5. Platform copies template → `data/deployments/{slug}/` (never edits template).
6. Platform writes tenant `.env` (token, DB URL, username).
7. Platform creates venv / container and runs `python -m app.main`.
8. User controls lifecycle via Builder commands; expiration suspends process.

## Isolation

- One process/container per customer bot  
- Separate sqlite DB under tenant `storage/`  
- Encrypted token at rest (AES-GCM)  
- Optional Docker network isolation in production  
