// The posts shown under "On X" on /journey. Add a post by pasting its address (https://x.com/<user>/status/<id>)
// into the day it was posted. Days with no posts are not shown.

export type PostDay = { day: string; date: string; posts: string[] };

export const X_POSTS: PostDay[] = [
  { day: "Day 1", date: "Sat 10 Oct", posts: [] },
  { day: "Day 2", date: "Sun 11 Oct", posts: [] },
  { day: "Day 3", date: "Mon 12 Oct", posts: [] },
];
