# User card photos

User-uploaded front photos for cards when TCDB has no scan, or when you want a better-condition photo (`wants_upgrade`).

## Enable / disable (rollback)

In `config.yaml`:

```yaml
features:
  user_card_photos: false   # hides UI and returns 404 on API routes
```

Restart the web service after changing config:

```bash
sudo systemctl restart phillies-checklist-web
```

**No data is deleted** when the flag is off. Photos on disk and `user_image_front_local` columns remain; re-enable to show them again.

## Display priority

1. User photo (`user_image_front_local` / `user_image_back_local`)
2. TCDB local cache (`image_front_local`)
3. TCDB remote URL (`image_front_url`)
4. Placeholder

TCDB columns are never overwritten by uploads.

## Storage layout

Under the image root (`storage.image_path`, default `/mnt/phillies-images`):

```
user-uploads/{tcdb_sid}/card-{card_id}-front.jpg
user-uploads/{tcdb_sid}/card-{card_id}-front-original.jpg
user-uploads/{tcdb_sid}/card-{card_id}-back.jpg
user-uploads/{tcdb_sid}/card-{card_id}-back-original.jpg
user-uploads/{tcdb_sid}/.staging/                         # temporary during upload (auto-cleaned)
```

Writes use `sg devagent` when the SMB mount is not writable by the web user.

## Full rollback (remove feature + data)

1. Set `features.user_card_photos: false` and restart (stops new uploads).
2. Optional — clear DB references only (keeps files as backup):

   ```bash
   sqlite3 data/phillies.db "UPDATE cards SET user_image_front_local = NULL, user_image_back_local = NULL;"
   ```

3. Optional — remove files:

   ```bash
   rm -rf /mnt/phillies-images/user-uploads
   ```

4. Optional — remove code dependency:

   ```bash
   # revert git commit(s) for user photos, or leave disabled via config
   pip uninstall opencv-python-headless  # only if nothing else needs it
   ```

## Schema

Columns on `cards` (added via `init_db()` migration):

- `user_image_front_local`
- `user_image_back_local`

## API (when enabled)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/card/{id}/user-photo/upload` | multipart `file` + `side` (`front`\|`back`) → staging + auto-crop preview |
| POST | `/api/card/{id}/user-photo/confirm` | form crop box + `side` → final JPEG + HTML row swap |
| DELETE | `/api/card/{id}/user-photo?side=front` | remove user photo for that side + HTML row swap |
