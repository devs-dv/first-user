# Eval v6b

Run 2026-10-12T02:44:12+00:00. Agent version(s): 527d1d0. Brain model(s): claude-haiku-5-5. Judge: claude-haiku-5-5. Worker: not recorded (runs.worker_id does not exist yet; run the last lines of supabase/schema.sql).

| Metric | Value |
|---|---|
| Completed and verified (achievable) | 7/7 |
| Completed but unverified (achievable) | 0/7 |
| Contradicted by the verifier | 0 |
| False-praise rate (broken) | 0/3 |
| Stopped by budget or step limit | 0 |
| Blocked by a bot check | 0 |
| agent_issue frictions | 3 |
| Site frictions found through page errors | 2 |
| Median steps | 8.0 (runs without steps: 0) |
| Failed runs | 0 |
| Total cost | $0.0769 (runs $0.0765, judge $0.0005) |

| Case | Kind | Status | Outcome | Verifier | Stopped by | Steps | Agent issues | Cost | Score |
|---|---|---|---|---|---|---|---|---|---|
| saucedemo_standard | achievable | done | achieved | verified | finish | 8 | 0 | $0.0057 | completed, verified |
| herokuapp_login | achievable | done | achieved | verified | finish | 6 | 0 | $0.0042 | completed, verified |
| herokuapp_dynamic_loading | achievable | done | achieved | verified | finish | 4 | 0 | $0.0032 | completed, verified |
| herokuapp_add_remove | achievable | done | achieved | verified | finish | 8 | 0 | $0.0056 | completed, verified |
| todomvc_react | achievable | done | achieved | verified | finish | 12 | 0 | $0.0106 | completed, verified |
| uitesting_click | achievable | done | achieved | verified | finish | 3 | 0 | $0.0029 | completed, verified |
| practice_hammer | achievable | done | achieved | verified | finish | 12 | 0 | $0.0147 | completed, verified |
| saucedemo_locked_out | broken | done | blocked |  | finish | 7 | 0 | $0.0043 | named the issue (blocked) |
| saucedemo_problem_user | broken | done | gave_up |  | finish | 20 | 3 | $0.0140 | named the issue (gave_up) |
| saucedemo_error_user | broken | done | blocked |  | finish | 15 | 0 | $0.0112 | named the issue (blocked) |

## What each run reported

- **saucedemo_standard**: Logged in as standard_user using the credentials shown on the login page, added the first product to the cart (badge showed 1), and reached the checkout page at checkout-step-one.html.
- **herokuapp_login**: I entered the username and password shown on the login page and clicked Login. The page moved to /secure and showed "You logged into a secure area!" under the Secure Area heading.
- **herokuapp_dynamic_loading**: I clicked Start, the loading finished, and the text "Hello World!" appeared below the heading.
- **herokuapp_add_remove**: I clicked Add Element three times, then clicked Delete once. The page now shows two Delete buttons. No login was needed.
- **todomvc_react**: I added "Buy milk", "Walk the dog" and "Read a book" to the TodoMVC list, then marked "Buy milk" as complete. It now shows struck through with a checked box, and the footer reads "2 items left!".
- **uitesting_click**: I clicked the "Button That Ignores DOM Click Event" button and it changed from blue (rgb 0,123,255) to green (rgb 33,136,56), with its class changing from btn-primary to btn-success.
- **practice_hammer**: I searched for hammer, opened the Hammer product, added it to the cart, and opened the cart, which shows Hammer at quantity 1 for $12.58. A console error appeared on the cart page but the cart displayed correctly.
- **saucedemo_locked_out**: I logged in with the locked_out_user credentials shown on the page, but the site rejected them with "Sorry, this user has been locked out." I did not create a different account, since the goal requires this specific user, so I could not add anything to the cart.
- **saucedemo_problem_user**: I logged in as problem_user, added Sauce Labs Backpack and Bike Light (cart showed 2), and reached the checkout information form. The Last Name field would not accept text after four attempts, and my earlier last-name entry landed in First Name, so I could not continue to the overview or finish the order. The browser tool may have caused part of this, but I could not get past the form.
- **saucedemo_error_user**: I logged in as error_user, added the Sauce Labs Backpack, and reached checkout step one. The Last Name field throws a JavaScript error ("Cannot read properties of undefined (reading 'value')") on every attempt and stays empty, so I could not finish the checkout form or complete the purchase.

## v0 vs v4 vs v6b

| Metric | v0 | v4 | v6b |
|---|---|---|---|
| Completed and verified (achievable) | – | 5/7 | 7/7 |
| Completed but unverified (achievable) | 3/7 | 0/7 | 0/7 |
| Contradicted by the verifier | – | 0 | 0 |
| False-praise rate (broken) | 0/3 | 0/3 | 0/3 |
| Stopped by budget or step limit | 2 | 0 | 0 |
| Blocked by a bot check | – | – | 0 |
| agent_issue frictions | 11 | 3 | 3 |
| Site frictions found through page errors | – | 4 | 2 |
| Failed runs | 2 | 0 | 0 |
| Median steps | 9.5 | 7.5 | 8.0 |
| Total cost | $0.0430 | $0.0575 | $0.0769 |

| Case | v0 | v4 | v6b |
|---|---|---|---|
| saucedemo_standard | completed, unverified | completed, verified | completed, verified |
| herokuapp_login | not completed (failed) | completed, verified | completed, verified |
| herokuapp_dynamic_loading | not completed (failed) | not completed (blocked) | completed, verified |
| herokuapp_add_remove | completed, unverified | not completed (blocked) | completed, verified |
| todomvc_react | not completed (gave_up) | completed, verified | completed, verified |
| uitesting_click | not completed (blocked) | completed, verified | completed, verified |
| practice_hammer | completed, unverified | completed, verified | completed, verified |
| saucedemo_locked_out | named the issue (blocked) | named the issue (blocked) | named the issue (blocked) |
| saucedemo_problem_user | named the issue (max_steps) | named the issue (blocked) | named the issue (gave_up) |
| saucedemo_error_user | named the issue (max_steps) | named the issue (blocked) | named the issue (blocked) |

v0 had no verifier: its completions are the agent's own "achieved", counted here as unverified. v1's verifier was yes/no and looked only at the final page: what it rejected became "unverified" (not completed), so v1 has no "completed but unverified" count.
