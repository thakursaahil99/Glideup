# ruff: noqa: E501  (question content reads better unwrapped)
"""The frameworks GlideUp ships with, and a starter question set for React and FastAPI.

Admins add frameworks and questions afterwards; seeding only inserts what is missing.
"""

from typing import Any

COMPOSITION = {"mcq": 6, "review": 1, "viva": 2, "project": 1}

FRAMEWORKS: list[dict[str, Any]] = [
    {"key": "react", "name": "React", "language_key": "javascript", "duration_minutes": 40,
     "description": "Components, hooks, state, effects, rendering and performance.",
     "composition": COMPOSITION},
    {"key": "fastapi", "name": "FastAPI", "language_key": "python", "duration_minutes": 40,
     "description": "Routing, Pydantic models, dependencies, async I/O, errors and testing.",
     "composition": COMPOSITION},
]  # fmt: skip


def _mcq(
    fw: str, slug: str, title: str, options: list[str], answer: int, why: str, level: str = "medium"
) -> dict[str, Any]:
    return {"framework": fw, "type": "mcq", "slug": slug, "title": title, "difficulty": level,
            "statement": title, "content": {"options": options, "answer": answer, "explanation": why}}  # fmt: skip


QUESTIONS: list[dict[str, Any]] = [
    # ------------------------------------------------------------------ React: MCQ
    _mcq("react", "react-mcq-state-update", "What does `setCount(count + 1)` called twice in the same click handler do (count starts at 0)?",
         ["Sets count to 2", "Sets count to 1", "Throws an error", "Sets count to 0"], 1,
         "Both calls read the same `count` from this render. Use the updater form `setCount(c => c + 1)` to add twice.", "easy"),
    _mcq("react", "react-mcq-effect-deps", "When does `useEffect(fn, [])` run its function?",
         ["On every render", "Only after the first render (and again on remount)", "Before the first render", "Never, the empty array disables it"], 1,
         "An empty dependency array means the effect has no dependencies, so it runs after mount (twice in Strict Mode development).", "easy"),
    _mcq("react", "react-mcq-keys", "Why should list items have stable `key` props?",
         ["To style them", "So React can match items between renders and keep their state", "Keys make lists render faster on first paint only", "They are required for accessibility"], 1,
         "Keys identify items across renders; unstable keys (like array indexes in reordered lists) mix up component state."),
    _mcq("react", "react-mcq-memo", "What does `React.memo(Component)` do?",
         ["Caches the component's DOM forever", "Skips re-rendering when its props are shallowly equal", "Memoizes every function inside the component", "Prevents state updates"], 1,
         "memo skips re-rendering a component if its props are shallowly equal to the previous ones."),
    _mcq("react", "react-mcq-usecallback", "When is `useCallback` actually useful?",
         ["Always, for every function", "When passing a function to a memoized child or using it as an effect dependency",
          "To make functions run faster", "To avoid closures"], 1,
         "It keeps a function's identity stable, which only matters when something compares it (memo props, effect deps)."),
    _mcq("react", "react-mcq-controlled", "What makes an input 'controlled'?",
         ["It has a ref", "Its value comes from React state and changes go through onChange", "It is inside a form", "It uses defaultValue"], 1,
         "A controlled input's value prop is driven by state; uncontrolled inputs keep their own DOM state.", "easy"),
    _mcq("react", "react-mcq-effect-cleanup", "Why does an effect that subscribes to something return a function?",
         ["To return data to the component", "To clean up (unsubscribe) before the effect re-runs or the component unmounts",
          "It is required by the linter only", "To cancel the render"], 1,
         "The returned cleanup runs before the next effect run and on unmount, preventing leaks and stale subscriptions."),
    _mcq("react", "react-mcq-derived-state", "A component stores `fullName` in state and syncs it from `first` and `last` props in an effect. What is better?",
         ["Keep it, effects are the right tool", "Compute `fullName` during render from the props", "Use a ref", "Use context"], 1,
         "Derived values should be calculated during render; syncing them with effects causes extra renders and bugs.", "hard"),
    # ------------------------------------------------------------------ React: review / viva / project
    {"framework": "react", "type": "review", "slug": "react-review-user-list", "title": "Review this component",
     "difficulty": "medium", "statement": "Review this component as you would in a pull request. List every problem you find and how to fix it.",
     "content": {"language": "javascript", "code": """function UserList({ teamId }) {
  const [users, setUsers] = useState([]);

  useEffect(() => {
    fetch(`/api/teams/${teamId}/users`)
      .then((r) => r.json())
      .then((data) => setUsers(data));
  });

  return (
    <ul>
      {users.map((user, index) => (
        <li key={index} onClick={() => users.splice(index, 1)}>
          {user.name}
        </li>
      ))}
    </ul>
  );
}""", "issues": [
         {"key": "missing_deps", "description": "The effect has no dependency array, so it refetches after every render (an infinite loop with setUsers).", "weight": 3},
         {"key": "race_condition", "description": "No cleanup/abort: a slow response for an old teamId can overwrite newer data.", "weight": 2},
         {"key": "index_key", "description": "Using the array index as key breaks state when items are removed or reordered.", "weight": 2},
         {"key": "mutating_state", "description": "users.splice mutates state directly and never triggers a re-render; use setUsers with a filtered copy.", "weight": 3},
         {"key": "no_error_handling", "description": "No loading or error handling for the request.", "weight": 1},
     ]}},
    {"framework": "react", "type": "viva", "slug": "react-viva-rendering", "title": "When does a React component re-render?",
     "difficulty": "medium", "statement": "Explain when a React component re-renders, and two ways to avoid unnecessary re-renders.",
     "content": {"key_points": ["Its state changes", "Its parent re-renders (props change or not)", "A context it consumes changes",
                                "React.memo to skip renders when props are equal", "Keep state close to where it is used / split components",
                                "Stable references with useMemo/useCallback where it matters"]}},
    {"framework": "react", "type": "viva", "slug": "react-viva-server-client", "title": "Server vs client components",
     "difficulty": "hard", "statement": "In a framework like Next.js, what is the difference between a Server Component and a Client Component, and when would you choose each?",
     "content": {"key_points": ["Server components render on the server and send no component JS to the browser",
                                "They can read data/secrets directly (database, files)", "Client components run in the browser and can use state, effects and event handlers",
                                "'use client' marks the boundary", "Keep most of the tree on the server; make interactive leaves client components"]}},
    {"framework": "react", "type": "viva", "slug": "react-viva-state-management", "title": "Choosing where state lives",
     "difficulty": "medium", "statement": "How do you decide whether state belongs in a component, is lifted up, goes into context, or into a server-state library like TanStack Query?",
     "content": {"key_points": ["Local state when only one component needs it", "Lift state to the closest common parent when siblings share it",
                                "Context for widely read, rarely changing values (theme, user)", "Server data belongs in a cache like TanStack Query (caching, refetching, dedup)",
                                "Avoid duplicating the same data in several places"]}},
    {"framework": "react", "type": "project", "slug": "react-project-search-list", "title": "Build a filterable list",
     "difficulty": "medium", "statement": "Write a `SearchableList` component that receives `items` (an array of `{ id, name }`) and shows a text input; only items whose name contains the typed text (case-insensitive) are listed. Show \"No results\" when nothing matches.",
     "content": {"language": "javascript", "starter": "export default function SearchableList({ items }) {\n  // your code\n}\n", "requirements": [
         {"key": "controlled_input", "description": "A controlled text input backed by state", "pattern": r"useState", "weight": 2},
         {"key": "case_insensitive", "description": "Filtering is case-insensitive", "pattern": r"toLowerCase|toLocaleLowerCase|/i\b|RegExp", "weight": 2},
         {"key": "stable_keys", "description": "List items use a stable key (the item id)", "pattern": r"key=\{[^}]*\.id\}", "weight": 1},
         {"key": "empty_state", "description": "Shows \"No results\" when nothing matches", "pattern": r"No results", "weight": 1},
         {"key": "derived_not_stored", "description": "The filtered list is derived during render, not kept in separate state or synced with an effect", "weight": 2},
     ]}},
    # ------------------------------------------------------------------ FastAPI: MCQ
    _mcq("fastapi", "fastapi-mcq-path-param", "How does FastAPI know `item_id` in `@app.get(\"/items/{item_id}\")` def read(item_id: int) is an integer?",
         ["It guesses from the URL", "From the type hint; it validates and converts the value, returning 422 if invalid", "You must call int() yourself", "From the docstring"], 1,
         "FastAPI uses type hints (via Pydantic) to parse and validate parameters and returns 422 on invalid input.", "easy"),
    _mcq("fastapi", "fastapi-mcq-depends", "What is `Depends()` used for?",
         ["Installing packages", "Declaring dependencies FastAPI resolves per request (e.g. a DB session or the current user)", "Making a route async", "Defining background tasks"], 1,
         "Dependencies are reusable callables FastAPI runs before the endpoint and injects; they can have their own dependencies and cleanup.", "easy"),
    _mcq("fastapi", "fastapi-mcq-async-blocking", "An `async def` endpoint calls `time.sleep(5)` (or a blocking DB driver). What happens?",
         ["Only that request waits", "The event loop is blocked, so all requests on that worker stall", "FastAPI moves it to a thread automatically", "It raises an error"], 1,
         "Blocking calls inside async def block the event loop. Use async libraries, or a plain def endpoint (run in a threadpool).", "medium"),
    _mcq("fastapi", "fastapi-mcq-response-model", "Why set `response_model=UserOut` on an endpoint returning a database user?",
         ["It makes the endpoint faster", "It filters and validates the output, so fields like password_hash are never returned, and documents the schema",
          "It is required for JSON", "It caches responses"], 1,
         "response_model shapes the output to the declared fields and documents it in OpenAPI."),
    _mcq("fastapi", "fastapi-mcq-httpexception", "How do you return a 404 with a message from an endpoint?",
         ["return 404", "raise HTTPException(status_code=404, detail=\"Not found\")", "print an error", "set response.status = 404 and return None"], 1,
         "Raising HTTPException stops the handler and FastAPI returns the status code with a JSON detail.", "easy"),
    _mcq("fastapi", "fastapi-mcq-yield-dep", "What does a dependency written with `yield` (e.g. a DB session) give you?",
         ["Streaming responses", "Code after `yield` runs after the response is sent, which is ideal for cleanup like closing the session", "Faster dependencies", "Nothing different from return"], 1,
         "Yield dependencies provide setup before the request and teardown after it."),
    _mcq("fastapi", "fastapi-mcq-testing", "What is the usual way to test FastAPI endpoints?",
         ["Start uvicorn and call it with curl", "Use TestClient (or httpx with ASGITransport) to call the app in-process, overriding dependencies when needed",
          "Only unit-test the functions", "Use Selenium"], 1,
         "TestClient/httpx run requests against the app without a server, and dependency_overrides swap things like the database."),
    _mcq("fastapi", "fastapi-mcq-background", "A signup endpoint must send a welcome email without making the user wait. What is a good first option?",
         ["time.sleep until it is sent", "BackgroundTasks for short work, or a task queue like Celery for heavier/retried work", "A global thread pool shared by hand", "Send it in a middleware"], 1,
         "BackgroundTasks run after the response; durable or heavy work belongs in a queue.", "hard"),
    # ------------------------------------------------------------------ FastAPI: review / viva / project
    {"framework": "fastapi", "type": "review", "slug": "fastapi-review-users", "title": "Review this endpoint",
     "difficulty": "medium", "statement": "Review this endpoint as you would in a pull request. List every problem you find and how to fix it.",
     "content": {"language": "python", "code": """@app.get("/users/{user_id}")
async def get_user(user_id):
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute(f"SELECT * FROM users WHERE id = {user_id}")
    row = cur.fetchone()
    if row is None:
        return {"error": "not found"}
    return {"id": row[0], "email": row[1], "password_hash": row[2]}""", "issues": [
         {"key": "sql_injection", "description": "SQL is built with an f-string from user input: SQL injection. Use parameters.", "weight": 3},
         {"key": "leaks_password_hash", "description": "Returns password_hash; use a response_model that excludes secrets.", "weight": 3},
         {"key": "blocking_in_async", "description": "psycopg2 is blocking inside async def, stalling the event loop; use an async driver or a sync def.", "weight": 2},
         {"key": "no_type_hint", "description": "user_id has no type hint, so it isn't validated as an int.", "weight": 1},
         {"key": "wrong_status", "description": "Not found returns 200 with an error body; raise HTTPException(404).", "weight": 2},
         {"key": "connection_leak", "description": "The connection is opened per request and never closed; use a pooled session dependency.", "weight": 2},
     ]}},
    {"framework": "fastapi", "type": "viva", "slug": "fastapi-viva-async", "title": "async def or def?",
     "difficulty": "medium", "statement": "When should a FastAPI endpoint be `async def` and when plain `def`? What goes wrong if you choose badly?",
     "content": {"key_points": ["async def when the endpoint awaits async I/O (async DB driver, httpx)", "plain def for blocking code; FastAPI runs it in a threadpool",
                                "Blocking calls inside async def block the event loop for every request", "CPU-heavy work belongs in a worker/queue, not either"]}},
    {"framework": "fastapi", "type": "viva", "slug": "fastapi-viva-auth", "title": "Protecting endpoints",
     "difficulty": "hard", "statement": "How would you protect a set of FastAPI endpoints so only logged-in admins can call them?",
     "content": {"key_points": ["A dependency that reads and verifies a token (e.g. JWT via OAuth2 bearer)", "It loads the current user and raises 401 if invalid",
                                "A second dependency checks the role/permission and raises 403", "Attach it per route or to an APIRouter's dependencies",
                                "Check permissions on the backend for every endpoint, not just in the UI"]}},
    {"framework": "fastapi", "type": "viva", "slug": "fastapi-viva-validation", "title": "Validation with Pydantic",
     "difficulty": "easy", "statement": "How does FastAPI validate request bodies, and what does the client get when validation fails?",
     "content": {"key_points": ["The body is declared as a Pydantic model parameter", "Types and constraints (Field, validators) are enforced",
                                "Invalid input returns 422 with details of each error", "The same models generate the OpenAPI docs"]}},
    {"framework": "fastapi", "type": "project", "slug": "fastapi-project-todo", "title": "Build a small todo API",
     "difficulty": "medium", "statement": "Write FastAPI routes for todos kept in memory: `POST /todos` creates one from `{ \"title\": str }` (title 1-200 chars) and returns it with an id and `done: false` (status 201); `GET /todos/{todo_id}` returns it or 404; `PATCH /todos/{todo_id}` can set `done`.",
     "content": {"language": "python", "starter": "from fastapi import FastAPI\n\napp = FastAPI()\n", "requirements": [
         {"key": "pydantic_models", "description": "Request/response bodies are Pydantic models", "pattern": r"BaseModel", "weight": 2},
         {"key": "title_validation", "description": "Title length is validated (1-200 characters)", "pattern": r"min_length|max_length|constr|Field\(", "weight": 2},
         {"key": "created_status", "description": "POST returns status 201", "pattern": r"201|HTTP_201_CREATED", "weight": 1},
         {"key": "not_found", "description": "Unknown ids return 404 via HTTPException", "pattern": r"HTTPException", "weight": 2},
         {"key": "typed_path", "description": "todo_id is a typed path parameter", "pattern": r"todo_id\s*:\s*int", "weight": 1},
         {"key": "partial_update", "description": "PATCH only changes the fields that were sent", "weight": 1},
     ]}},
]  # fmt: skip
