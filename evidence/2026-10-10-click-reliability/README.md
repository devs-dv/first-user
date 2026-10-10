# Click reliability on saucedemo — 2026-10-10

## What was measured

`worker/measure_clicks.py` ran four browser actions on https://www.saucedemo.com with no brain model. Stagehand's lookup model was `anthropic/claude-haiku-4-5`. Each of 5 attempts used a fresh Chrome window:

1. type `standard_user` into the username field
2. type `secret_sauce` into the password field
3. click the Login button
4. click "Add to cart" for Sauce Labs Backpack

The username and password are the public demo login that saucedemo shows on its own login page.

A step **changed the page** if the page fingerprint differed after the step. The fingerprint is the URL plus a hash of the visible text and form-field values. An attempt is an **end-to-end success** if it ended logged in with a cart badge of `1`.

- **Before** (`measure-plain-20261010-145414.json`): one `stagehand.act(instruction)` per step, with Chrome at the display's default device scale factor (1.25).
- **After** (`measure-ladder-20261010-150149.json`): the new `do()` tool, with Chrome at device scale factor 1.0. It checks whether the page changed, then works through a recovery ladder until something does:
  - (a) `act(instruction)`
  - (b) `observe(instruction)` then `act(action)`
  - (c) the observed selector through the locator API: `locator.click`, then `send_click_event`

## Results

| | End-to-end success | Steps that changed the page | Reported success, nothing changed | Stagehand tokens |
|---|---|---|---|---|
| Before (plain `act`, scale 1.25) | 0/5 | 15/20 | 5 (every "Add to cart") | 40,786 |
| After (ladder, scale 1.0) | 5/5 | 20/20 | 0 | 53,139 |

In the "after" run, login steps succeeded on rung (a). "Add to cart" succeeded on rung (c) in all 5 attempts. The extra Stagehand tokens are the cost of rungs (a) and (b) failing first.

## Root cause

- **The wrong button was not the problem.** On "Add to cart", `act` returned the correct button's selector and reported success, but the click had no effect.
- **What separated working from failing clicks:** clicks sent as screen-coordinate mouse events (`act` and `locator.click`) did not register. A DOM click event (`send_click_event`) did.
- **The display scaling contributes.** The display runs at 125% scaling (device pixel ratio 1.25). At device scale factor 1.0, `locator.click` worked.
- **But it is not the whole cause.** Even at 1.0, `act` clicks still failed. Rung (a) is a plain `act` call, and it failed on "Add to cart" in all 5 "after" attempts.
- **What made clicks reliable:** checking whether the page actually changed, plus the locator rung (c). The scale-factor change alone did not.
