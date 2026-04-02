# CEO Router — Complexity Rules

## Three levels

### simple
- One direct output
- No backend, no persistence, no external state
- Examples: "explain recursion", "write a cover letter", "generate an image"

### multi_step
- Multiple outputs or transformations
- Possible memory or tool use
- No deep architecture needed
- Examples: "build a todo app with dark mode and filtering",
            "write 3 ad variations for different audiences"

### full_system
- Backend + database + API + persistence
- User accounts, global state, realtime
- Examples: "build a leaderboard that saves scores",
            "create a login system with user profiles",
            "make a multiplayer game with a global scoreboard"

## full_system + underspecified → ALWAYS ask

If the request is full_system AND vague:
- Do NOT build a "simple local version" and pretend it solves the request
- Do NOT hallucinate a database solution
- DO ask the user which scope they want:

  "This requires a full system setup. Do you want:
   A. Simple local version (browser only, no server)
   B. Full version (backend, database, user accounts, API)"

## full_system + well-specified → still confirm scope

Even if the request is detailed, confirm before starting:
  "This is a full-system build. I'll scaffold:
   backend, DB schema, API routes, auth, and frontend.
   Confirm to start, or tell me what to adjust."

## Complexity does NOT gate execution

Complexity informs the execution plan depth.
A simple request gets a single module_call step.
A multi_step request may get memory + web + module_call.
A full_system request triggers clarification first.
