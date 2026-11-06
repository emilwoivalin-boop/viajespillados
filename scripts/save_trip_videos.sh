#!/usr/bin/env bash
# save_trip_videos.sh <trip id> <lang...>: copy the finished videos/covers of trips/<id>/ to the branch "trip-videos".
# A language whose video is missing (failed render) is skipped; the others are still saved.
set -u
ID="$1"; shift
SRC="$(pwd)/trips/$ID"
TV="${RUNNER_TEMP:-/tmp}/tv-$$"
git worktree remove --force "$TV" 2>/dev/null || true
if git ls-remote --exit-code --heads origin trip-videos >/dev/null; then
  git fetch -q origin trip-videos
  git worktree add -q "$TV" origin/trip-videos && cd "$TV" && git checkout -q -B trip-videos
else
  git worktree add -q --orphan -b trip-videos "$TV" && cd "$TV"
fi
mkdir -p "$ID"
saved=""
for L in "$@"; do
  [ -f "$SRC/video_$L.mp4" ] || continue
  cp "$SRC/video_$L.mp4" "$ID"/
  cp "$SRC/video_${L}_cover.jpg" "$SRC/cover_$L.jpg" "$ID"/ 2>/dev/null || true
  saved="$saved $L"
done
[ -n "$saved" ] || { echo "nothing to save"; exit 0; }
git add "$ID" && git commit -q -m "Travel plan video: $ID ($saved )"
for i in 1 2 3 4 5; do git push -q origin trip-videos && break; git pull -q --rebase origin trip-videos; done
cd - >/dev/null; git worktree remove --force "$TV" 2>/dev/null || true
echo "saved:$saved"
