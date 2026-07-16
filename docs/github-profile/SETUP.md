# Publish the BLERBZ GitHub profile

The profile README in this folder is ready to ship. GitHub only renders it
from a special repository — not from `absoloop` itself.

## Organization profile (BLERBZ)

1. Create a **public** repository named exactly `.github` under the `BLERBZ`
   organization (if it does not already exist).
2. Add these paths on the default branch:

   ```text
   profile/README.md                 ← copy from docs/github-profile/README.md
   profile/absoloop-logo.png         ← copy from this folder
   profile/absoloop-logo-pixel.png   ← copy from this folder
   ```

3. Push. Visit `https://github.com/BLERBZ` — the profile block appears above
   the repository list within a few minutes.

### One-shot copy (from an Absoloop checkout)

```bash
# Assumes you have write access and gh is authenticated
ORG=BLERBZ
WORKDIR=$(mktemp -d)
gh repo clone "$ORG/.github" "$WORKDIR" -- --depth 1 \
  || gh repo create "$ORG/.github" --public --clone --confirm
# if create used a different cwd, adjust WORKDIR

mkdir -p "$WORKDIR/profile"
cp docs/github-profile/README.md "$WORKDIR/profile/README.md"
cp docs/github-profile/absoloop-logo.png "$WORKDIR/profile/"
cp docs/github-profile/absoloop-logo-pixel.png "$WORKDIR/profile/"
git -C "$WORKDIR" add profile
git -C "$WORKDIR" commit -m "Add BLERBZ profile README featuring Absoloop"
git -C "$WORKDIR" push
```

Strip the HTML comment block at the top of `profile/README.md` before or
after publish if you want a cleaner source file (optional — HTML comments
do not render).

## Personal profile

1. Create a public repo named exactly your GitHub username.
2. Use this folder’s `README.md` as that repo’s root `README.md`.
3. Copy both PNGs next to it (same relative paths) **or** point `<img src>`
   at the Absoloop raw URLs:

   ```text
   https://raw.githubusercontent.com/BLERBZ/absoloop/main/docs/assets/absoloop-logo.png
   https://raw.githubusercontent.com/BLERBZ/absoloop/main/docs/assets/absoloop-logo-pixel.png
   ```

## Keeping brand in sync

Edit logos and palette notes in [`../assets/`](../assets/) first, then
re-copy into `docs/github-profile/` (and the live `.github` profile repo)
when you cut a brand refresh.
