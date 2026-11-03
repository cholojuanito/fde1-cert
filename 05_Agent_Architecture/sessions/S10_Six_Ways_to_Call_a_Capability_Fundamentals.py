# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "marimo==0.23.16",
#     "python-dotenv>=1.2",
#     "litellm>=1.90",
#     "mcp>=1.2",  # not imported here: litellm imports it when tools= is passed, and the sandbox asks for it on the first call without this line
# ]
# ///

import marimo

__generated_with = "0.23.16"
app = marimo.App(width="medium", app_title="Six Ways to Call a Capability")


@app.cell
def _():
    import marimo as mo

    return (mo,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Session 10: Six Ways to Call a Capability

    *One worker, one recommendation, one board that will not accept "it depends."*

    Sofia is an engineer on the platform team of a regional hospital group. Six
    product teams — pharmacy renewals, bed management, the IT service desk,
    discharge summaries, supplier invoices, the on-call rota — each want a
    model to call the same kind of internal lookup, and each has already picked
    a different way to do it: one wrote a tool, one an MCP server, one is
    piloting Code Mode. The architecture review board has asked her for **one
    recommendation, with numbers, by the end of the month**, and the answer it
    will not accept is *"it depends."*

    So she does what the board cannot: builds the same trivial capability all
    six ways and measures them. One function, put behind a model six different
    ways — a tool, a skill, a subagent, an MCP server, Code Mode, and UTCP —
    then a counter that separates what the loop cost from what the work was,
    and a sweep that shows which architecture's token bill grows with your
    data. The output is not a preference. It is a defensible choice with five
    named rejections and the condition that would change it — which is what
    the board asked for, and what the room will ask you.

    ---
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Table of Contents

    - Task 0: The capability
    - Way 1: A tool
    - Way 1, continued: The same loop, when the model gets it wrong
    - ❓ Question #1
    - Way 2: A skill
    - Way 3: A subagent
    - Way 4: An MCP server
    - ❓ Question #2
    - Way 5: Code Mode
    - Way 6: UTCP
    - Task 7: Measure them
    - Task 8: Where Code Mode actually wins
    - ❓ Question #3
    - Task 9: The comparison
    - ❓ Question #4
    - Conclusion
    - Additional Context
    - Bonus Tasks

    > 📓 **Not covered here:** measuring your *own* endpoint at the size it
    > really returns, and building a second implementation of it. Task 9's
    > ordering tells you which way to build; the challenge is where you build
    > and measure it.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 📖 Official documentation

    Everything this notebook uses, from the people who maintain it.

    | Tool | What you use it for here | Docs |
    | --- | --- | --- |
    | LiteLLM | `completion(tools=...)` — the model loop in Ways 1, 2, 5 and 6 | [docs.litellm.ai — function calling](https://docs.litellm.ai/docs/completion/function_call) |
    | `helpers/tools.py` | `Toolbox`, the dispatcher whose failures are messages rather than exceptions | [`helpers/tools.py`](../../helpers/tools.py) |
    | MCP | the protocol Way 4's server speaks; needs the `mcp` package, 2.0 or later | [modelcontextprotocol.io](https://modelcontextprotocol.io/docs/getting-started/intro) |
    | UTCP | the manifest format Way 6 derives a schema from | [utcp.io](https://www.utcp.io/) |
    | marimo | `mo.output.replace`, which streams the drifting tool call in Way 1 as it arrives | [docs.marimo.io](https://docs.marimo.io/) |

    ---
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    "We use MCP" is not an architecture. It is one of at least six ways to let a
    model do something, and they differ in latency, token cost, failure mode,
    who maintains them, and who can discover them.

    So we build **the same capability six times** and measure the differences.
    The capability is deliberately trivial — looking up an on-call contact — so
    that nothing about the task distracts from the plumbing. It is not Sofia's
    pharmacy lookup or her bed-management query; it is the smallest thing that
    behaves like both, which is the only fair way to compare six architectures.

    > **You will be asked what you rejected.** An architecture with no rejected
    > alternatives was not chosen; it was defaulted into. This session is how you
    > get a real answer.

    Every number in this notebook comes out of a cell you press, against
    **your** configured model. The tables are outputs, not claims.

    ---
    ## Setup
    """)
    return


@app.cell
def _(mo):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(mo.notebook_dir()).parent.parent))
    from helpers import nb, ui

    CFG = nb.bootstrap()
    print(f"✅ {CFG}")
    return CFG, Path, sys, ui


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ---
    ## Task 0 — The capability

    One function. Everything below is a different way of putting a model in
    front of it.

    Note the signature: every implementation below takes the capability as an
    **argument** rather than reaching for the global. That is not style. It is
    what lets the measurement at the end swap in a counting version and find out
    how many times each architecture actually calls it.
    """)
    return


@app.cell
def _():
    ONCALL = {
        "atlas": {"team": "Tracking Platform", "channel": "#team-tracking", "pager": "tracking-oncall"},
        "ledger": {"team": "Revenue Systems", "channel": "#team-revenue", "pager": "revenue-oncall"},
        "warehouse gateway": {"team": "Depot Systems", "channel": "#team-depot", "pager": "depot-oncall"},
        "postgres": {"team": "Data Platform", "channel": "#team-data", "pager": "data-oncall-24x7"},
    }

    def who_is_oncall(service: str) -> dict:
        """Return the team, chat channel, and pager rota for a service."""
        key = service.strip().lower()
        for name, info in ONCALL.items():
            if key in name or name in key:
                return {"service": name, **info}
        return {"error": f"unknown service: {service}", "known": sorted(ONCALL)}

    print(who_is_oncall("Atlas"))
    return ONCALL, who_is_oncall


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ---
    ## Way 1 — A tool

    The model is given a schema, decides to call it, and you execute it. The
    baseline every other approach is measured against.

    Everything here is visible: you write the schema, you dispatch the call, you
    decide what goes back into the conversation. Nothing is hidden, and nothing
    is reusable outside this process. This is what the service-desk team built,
    in an afternoon, and it is the version the other five teams call naive.
    """)
    return


@app.cell
def _(CFG, who_is_oncall):
    import json
    import time

    from litellm import completion

    TOOL_SCHEMA = [{
        "type": "function",
        "function": {
            "name": "who_is_oncall",
            "description": "Find which team owns a service and how to reach them.",
            "parameters": {
                "type": "object",
                "properties": {
                    "service": {"type": "string", "description": "The service name, e.g. Atlas"}
                },
                "required": ["service"],
            },
        },
    }]

    def call_with_tool(question: str, fn=who_is_oncall, meter=None) -> dict:
        """Decide, dispatch, answer. The whole loop.

        The loop is not `if tool_calls: ... else: answer` — it repeats, because a
        model may need a second round after seeing the first results. The cap is
        there so a model that keeps calling forever stops being your problem.
        """
        messages = [{"role": "user", "content": question}]
        for _ in range(6):
            reply = completion(**CFG.kwargs(), messages=messages, tools=TOOL_SCHEMA,
                               timeout=600)
            if meter:
                meter.track(reply)
            msg = reply.choices[0].message

            calls = getattr(msg, "tool_calls", None) or []
            if not calls:
                return {"answer": msg.content}

            messages.append(msg.model_dump())
            for call in calls:
                args = json.loads(call.function.arguments)
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(fn(**args)),
                })
        return {"answer": "gave up after 6 rounds"}

    return TOOL_SCHEMA, call_with_tool, completion, json, time


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    **Two model calls minimum** — one to decide, one to answer. That is the cost
    floor for every tool-based architecture, and it is why latency-sensitive
    systems sometimes skip tools entirely and just do retrieval.

    Notice what the loop does *not* assume: that one question means one tool
    call. Ask about four services and a current model will usually emit all four
    requests in a single turn. Task 7 measures whether yours does, and the answer
    changes the arithmetic more than anything else in this session.

    ---
    ## Way 1, continued — the same loop, when the model gets it wrong

    Read `call_with_tool` again as though a model were trying to break it:

    ```python
    args = json.loads(call.function.arguments)   # truncated JSON  -> ValueError
    result = fn(**args)                          # invented kwarg  -> TypeError
                                                 # missing kwarg   -> TypeError
    ```

    Each of those kills the request. There is a fourth that does not raise at
    all, and it is the one worth building: **nothing checks
    `call.function.name`.** The loop dispatches to `fn` whatever the model asked
    for.

    That sounds like a contrived failure until you notice how you get there.
    Schemas and dispatchers live in different places and drift apart — someone
    renames a function, someone adds a tool to the schema before implementing it,
    someone deletes an implementation and misses the schema entry. Now the model
    asks for a tool you no longer have, and a loop with no name check runs a
    *different* function and answers confidently from the result.

    Below: a schema that advertises two tools, a dispatcher that implements one.
    """)
    return


@app.cell
def _(TOOL_SCHEMA, mo):
    # A schema that advertises two tools. The dispatcher below implements one.
    STALE_SCHEMA = TOOL_SCHEMA + [{
        "type": "function",
        "function": {
            "name": "lookup_team",
            "description": "Look up the team that owns a service. Preferred over who_is_oncall.",
            "parameters": {
                "type": "object",
                "properties": {"service": {"type": "string"}},
                "required": ["service"],
            },
        },
    }]

    run_drift = mo.ui.run_button(label="Ask a model for a tool that does not exist")
    run_drift
    return STALE_SCHEMA, run_drift


@app.cell
def _(CFG, STALE_SCHEMA, completion, json, mo, run_drift, time, who_is_oncall):
    mo.stop(
        not run_drift.value,
        mo.md("Press the button. One model call — the schema offers `lookup_team`, "
              "the dispatcher only has `who_is_oncall`."),
    )

    # Streamed for the same reason the tool-poisoning task streams: a tool call
    # is assembled from fragments -- name first, then arguments a few characters
    # at a time -- and watching the model reach for `lookup_team` is the point.
    tool_name, tool_args, last_paint = "", "", 0.0
    for stream_chunk in completion(
        **CFG.kwargs(), timeout=600, tools=STALE_SCHEMA, stream=True,
        messages=[{"role": "user", "content": "Who owns Atlas?"}],
    ):
        for fragment in (getattr(stream_chunk.choices[0].delta, "tool_calls", None) or []):
            fragment_fn = getattr(fragment, "function", None)
            if fragment_fn is not None:
                tool_name += getattr(fragment_fn, "name", None) or ""
                tool_args += getattr(fragment_fn, "arguments", None) or ""
        if time.monotonic() - last_paint >= 0.08:
            mo.output.replace(mo.md(f"model is asking for: `{tool_name or '…'}({tool_args})`"))
            last_paint = time.monotonic()

    if not tool_name:
        drift_report = "The model answered without calling a tool. Press again."
    else:
        # The naive dispatch: no name check, exactly like the loop above.
        naive_result = who_is_oncall(**json.loads(tool_args or "{}"))
        drift_report = (
            f"The model asked for **`{tool_name}`**.\n\n"
            f"The naive loop runs `who_is_oncall` anyway and gets:\n\n"
            f"```\n{naive_result}\n```\n\n"
            "No exception. No warning. The next model call receives that as the "
            f"result of a tool it believes is called `{tool_name}`, and answers from it."
        )

    mo.md(drift_report)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    A crash you find in the logs. This you find in a customer's transcript.

    The fix is not more `try` blocks. It is a rule:

    > **A tool failure is a message, not an exception.**

    Hand the model back `unknown tool 'lookup_team'; available: who_is_oncall`
    and it will usually correct itself on the next turn. Hand it a traceback and
    it gets nothing, because your process is already gone. **The model is the only
    party who can fix a bad tool call**, so the error has to be addressed to it.

    `helpers/tools.py` is that rule, packaged. Same stale schema, same model,
    dispatch through a `Toolbox` instead:
    """)
    return


@app.cell
def _(mo):
    run_toolbox = mo.ui.run_button(label="Run the same broken call through a Toolbox")
    run_toolbox
    return (run_toolbox,)


@app.cell
def _(CFG, STALE_SCHEMA, completion, mo, run_toolbox, ui, who_is_oncall):
    mo.stop(
        not run_toolbox.value,
        mo.md("Press to see the same failure handled. Two model calls: the bad "
              "request, and the model's recovery after it is told."),
    )

    from helpers.tools import Toolbox

    toolbox = Toolbox()
    toolbox.register(who_is_oncall)          # schema derived from the signature

    # Not streamed: `Toolbox.run` needs the finished message object, and
    # reassembling one from fragments here would bury the thing this cell is
    # about. Two calls, so the honest treatment is saying which one is running.
    toolbox_messages = [{"role": "user", "content": "Who owns Atlas?"}]
    mo.output.replace(mo.md("**1 of 2** — asking the model, with the stale schema…"))
    first_message = completion(**CFG.kwargs(), messages=toolbox_messages, tools=STALE_SCHEMA,
                               timeout=600).choices[0].message
    toolbox_messages += toolbox.run(first_message)             # dispatch never raises

    mo.output.replace(mo.md("**2 of 2** — the model has been told what went wrong…"))
    second_message = completion(**CFG.kwargs(), messages=toolbox_messages, tools=STALE_SCHEMA,
                                timeout=600).choices[0].message
    recovered_calls = getattr(second_message, "tool_calls", None) or []

    ui.table([
        {"step": "model asked for",
         "value": ", ".join(call.function.name for call in (first_message.tool_calls or []))},
        {"step": "Toolbox returned", "value": toolbox_messages[-1]["content"]},
        {"step": "model's next move",
         "value": ", ".join(call.function.name for call in recovered_calls) or "(answered directly)"},
    ], title="Same failure, addressed to the party who can fix it")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Deriving the schema from the signature is not laziness either. It is the fix
    for the drift you just watched: a hand-written schema and the function it
    describes have no mechanism keeping them together, and `register()` is that
    mechanism.

    **This is the difference between the two versions**, and it is worth carrying
    into your own app whichever of the six you pick — every one of them dispatches
    something eventually:

    | | Naive loop | `Toolbox` |
    | --- | --- | --- |
    | Unknown tool name | runs the wrong function, silently | message naming the available tools |
    | Malformed JSON arguments | `ValueError`, request dies | message asking for a JSON object |
    | Unexpected argument | `TypeError`, request dies | message listing what it accepts |
    | The tool itself raises | request dies | message with the error, model can try again |
    | A result larger than the context | silently eats the answer's room | truncated, and *says* it was |

    ---
    ### ❓ Question #1

    Look at the endpoint on your own app — or whatever sits between a model's
    tool request and your code. In one to three sentences: what does it do
    today when the model asks for a tool name it does not have, or sends
    arguments that do not parse — and which of the five rows in the table
    above would a user of your app meet first?

    **Answer:**

    ---
    ## Way 2 — A skill

    A directory on disk with instructions in it. The agent reads the
    instructions, then runs the script.

    The difference from a tool is *where the knowledge lives*. A tool's schema is
    in your code. A skill's is a file a domain expert can edit without touching
    Python — which matters enormously when the person who knows the escalation
    policy is not an engineer. The pharmacy team chose this, because the
    renewal rules change every time the formulary does and the pharmacist who
    owns them does not open pull requests.
    """)
    return


@app.cell
def _(Path, mo):
    SKILL_DIR = Path(mo.notebook_dir()) / "skills" / "oncall-lookup"

    # The literal starts on the NEXT line deliberately. `dedent` strips the
    # longest common leading whitespace, so a first line at column 0 -- which
    # `---` would be -- makes that prefix empty and dedent a no-op. The file
    # then ships with indented YAML frontmatter, which is not YAML.
    SKILL_MD = """
    ---
    name: oncall-lookup
    description: Find who owns a service and how to page them. Use when someone
      asks who to contact about an outage or a service.
    version: 1.0.0
    ---

    # On-call lookup

    ## When to use this
    Someone needs to reach the team responsible for a service.

    ## How to use it
    Run: `python run.py <service name>`

    ## Escalation policy
    If the service is Tier 1 and has been degraded for more than fifteen minutes,
    page the Data Platform on-call as well, regardless of what the cause looks like.

    <!-- ^ That paragraph is the point of skills. It is policy, not code, it changes
         without a deploy, and the person who owns it is not an engineer. -->
    """

    mo.md(f"```markdown\n{SKILL_MD}\n```")
    return SKILL_DIR, SKILL_MD


@app.cell
def _(ONCALL, SKILL_DIR, SKILL_MD, json, mo, sys):
    import subprocess

    from textwrap import dedent

    SKILL_DIR.mkdir(parents=True, exist_ok=True)
    # dedent, because the formatter indents multi-line strings and YAML
    # frontmatter with leading spaces is not YAML.
    (SKILL_DIR / "SKILL.md").write_text(dedent(SKILL_MD).lstrip(), encoding="utf-8")
    (SKILL_DIR / "run.py").write_text(
        "import json, sys\n"
        f"ONCALL = {json.dumps(ONCALL)}\n"
        "key = ' '.join(sys.argv[1:]).strip().lower()\n"
        "hit = next((dict(service=name, **info) for name, info in ONCALL.items()"
        " if key in name or name in key), {'error': 'unknown'})\n"
        "print(json.dumps(hit))\n",
        encoding="utf-8",
    )

    def run_skill(service: str) -> dict:
        """Invoke the skill's script the way an agent would: as a subprocess."""
        out = subprocess.run(
            [sys.executable, str(SKILL_DIR / "run.py"), service],
            capture_output=True, text=True, timeout=30,
        )
        return json.loads(out.stdout) if out.returncode == 0 else {"error": out.stderr[:120]}

    mo.md(f"`run_skill('Ledger')` → `{run_skill('Ledger')}`")
    return dedent, run_skill


@app.cell
def _(CFG, completion, json, run_skill):
    # The agent still has to decide *which* services before it can run anything.
    # Asking for that decision with a schema rather than in prose is not a
    # detail -- see the note under Task 7 for what the prose version costs.
    PLAN_SCHEMA = [{
        "type": "function",
        "function": {
            "name": "lookup_services",
            "description": "Look up on-call information for one or more services.",
            "parameters": {
                "type": "object",
                "properties": {
                    "services": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Every service named in the question.",
                    }
                },
                "required": ["services"],
            },
        },
    }]

    def call_with_skill(question: str, fn=None, meter=None) -> dict:
        """Decide which services, run the script per service, answer.

        `fn` is ignored, and that is the finding rather than an oversight: a
        skill's capability lives on disk, so Task 7's counter cannot see it
        being called. Neither can your tracing.
        """
        plan = completion(**CFG.kwargs(), timeout=600, tools=PLAN_SCHEMA,
                          tool_choice="required",
                          messages=[{"role": "user", "content": question}])
        if meter:
            meter.track(plan)
        calls = getattr(plan.choices[0].message, "tool_calls", None) or []
        try:
            services = json.loads(calls[0].function.arguments)["services"]
        except (IndexError, KeyError, ValueError, TypeError):
            services = [question]

        results = [json.dumps(run_skill(str(service))) for service in services]

        final = completion(**CFG.kwargs(), timeout=600, messages=[
            {"role": "user",
             "content": f"{question}\n\nLookup results:\n" + "\n".join(results)}])
        if meter:
            meter.track(final)
        return {"answer": final.choices[0].message.content}

    return (call_with_skill,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ---
    ## Way 3 — A subagent

    Hand the job to a second model call with its own instructions and its own
    context, and take back only the answer.

    The reason to do this is almost never capability. It is **context hygiene**:
    the subagent can read fifty documents and return three lines, and the parent
    conversation never carries the other forty-seven. The discharge-summary
    team chose this: their parent conversation is a clinician's, and forty
    pages of notes must not end up in it.
    """)
    return


@app.cell
def _(CFG, ONCALL, completion, json):
    def call_with_subagent(question: str, fn=None, meter=None) -> dict:
        """A narrow specialist with its own prompt and its own context."""
        reply = completion(
            **CFG.kwargs(),
            timeout=600,
            messages=[
                {"role": "system", "content":
                 "You answer on-call questions from this table and nothing else. "
                 "Name the team and the channel for each service asked about. If a "
                 f"service is not listed, say so.\n\n{json.dumps(ONCALL, indent=2)}"},
                {"role": "user", "content": question},
            ],
        )
        if meter:
            meter.track(reply)
        return {"answer": reply.choices[0].message.content}

    return (call_with_subagent,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Note what changed: the parent never sees the table. For a table of four
    services that is pointless. For a fifty-page policy document it is the
    difference between a system that works at turn twenty and one that does not.

    Note also what it costs. The subagent never calls the function at all — the
    data is in its prompt, so it is reciting rather than looking up. That is
    cheap and it is also why a subagent is the wrong shape for anything that has
    to be *current*.

    > **The library that does this properly is `deepagents`** (`uv add
    > deepagents`), built on LangGraph. Having written the six lines above, its
    > shape is legible: `SubAgent` for a named specialist with its own prompt and
    > tools, `SubAgentMiddleware` to give a parent the ability to spawn them, plus
    > the two things this cell has no answer for — a todo list so a long job has
    > state, and a virtual filesystem so a subagent can hand back a *file* instead
    > of a paragraph.
    >
    > It is worth reading rather than adopting reflexively: it arrives with ~50
    > packages, which is a real cost for one capability behind one caller. The
    > time it earns that is when you have several specialists, long-running work,
    > and something to hand between them — which is exactly when writing your own
    > stops being thirty lines.

    ---
    ## Way 4 — An MCP server

    Model Context Protocol. The capability becomes a **separate process**
    speaking a standard protocol over stdio, and any MCP-aware client — Claude
    Code, Claude Desktop, your app — can discover and call it.

    That is the whole value proposition: **you write it once and things you did
    not write can find it.** The cost is a process boundary, a handshake, and a
    deployment story. The on-call rota team chose this — and when Sofia asked
    which client outside their codebase discovers it today, the answer was
    "none yet", which is the sentence Question #2 exists for.
    """)
    return


@app.cell
def _(ONCALL, Path, dedent, json, mo):
    MCP_SERVER = Path(mo.notebook_dir()) / "mcp_oncall_server.py"

    # Same dedent rule as the skill above, and it matters more here: without it
    # this writes indented Python at module level and the file it overwrites
    # stops parsing at all.
    MCP_SERVER.write_text(
        dedent('''
    """An MCP server exposing one tool over stdio.

    Run standalone:  python mcp_oncall_server.py
    Or point an MCP client at it -- including Claude Code, via .mcp.json.
    """
    import json
    from mcp.server import MCPServer

    ONCALL = ''').lstrip() + json.dumps(ONCALL, indent=4) + dedent('''

    server = MCPServer("oncall")


    @server.tool()
    def who_is_oncall(service: str) -> str:
        """Find which team owns a service and how to reach them."""
        key = service.strip().lower()
        for name, info in ONCALL.items():
            if key in name or name in key:
                return json.dumps({"service": name, **info})
        return json.dumps({"error": f"unknown service: {service}"})


    if __name__ == "__main__":
        server.run()          # stdio by default
    '''),
        encoding="utf-8",
    )

    mo.md(
        "Written to `mcp_oncall_server.py`. Twelve lines of actual server.\n\n"
        "To use it from Claude Code, add a `.mcp.json`:\n\n"
        "```json\n"
        '{\n  "mcpServers": {\n    "oncall": {\n'
        '      "command": "python",\n      "args": ["mcp_oncall_server.py"]\n'
        "    }\n  }\n}\n```\n\n"
        "> Needs the `mcp` package (`uv add mcp`), version **2.0 or later**. "
        "The 2.0 release removed `mcp.server.fastmcp`; `MCPServer` in "
        "`mcp.server` is the replacement and the decorator API is otherwise "
        "unchanged. If you are reading an older tutorial, that import is why it "
        "does not run.\n\n"
        "> It is absent from Task 7's measurement on purpose. Over stdio, an MCP "
        "tool call is a tool call — the same two model round trips as Way 1, plus "
        "a process to start and a handshake to complete. **MCP does not change "
        "the arithmetic; it changes who can reach you.** Measuring it here would "
        "produce Way 1's numbers with extra steps and imply the difference lives "
        "somewhere it does not."
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    > **🏢 In the enterprise:** an MCP server is a *service* — a process with a
    > lifecycle, a health check, an owner, and, over HTTP, an authentication
    > story. None of that exists for a tool in your own process. The decision
    > this forces is whether there is a client you did not write that needs to
    > discover this capability — Claude Code, another team's agent, an ops
    > console — because that discoverability is the only thing the process
    > boundary buys. If your app is the only caller, you have bought a
    > deployment target and a lifecycle problem in exchange for nothing, and
    > the platform team will ask who is on call for it.

    ---
    ### ❓ Question #2

    In one to three sentences: who, *outside your codebase*, would need to
    discover your capability in the next year — name the client, not a
    category — and if the honest answer is nobody, what does an MCP server buy
    you that a tool does not?

    **Answer:**

    ---
    ## Way 5 — Code Mode

    Stop giving the model tools. Give it a **Python namespace** and let it write
    code against it.

    This inverts the usual arrangement. Instead of shipping every intermediate
    result back through the model, the model writes a program that loops,
    filters, and composes — and the only thing that returns is the answer.

    Task 8 measures what that is worth. It is a larger number than most people
    expect, and it gets larger as your data does. The bed-management team is
    piloting this, because one question about ward capacity is forty lookups,
    and their pilot is also the reason the board's security member is on the
    call.
    """)
    return


@app.cell
def _(CFG, completion, who_is_oncall):
    CODE_PROMPT = """You have this function available:

        who_is_oncall(service: str) -> dict

    Write Python that answers the question and assigns the result to `answer`.
    Output only code. No explanation, no markdown fences.

    Question: {question}"""

    SAFE_BUILTINS = {
        "len": len, "sorted": sorted, "list": list, "dict": dict, "set": set,
        "str": str, "int": int, "float": float, "bool": bool, "print": print,
        "sum": sum, "any": any, "all": all, "range": range, "enumerate": enumerate,
        "zip": zip, "min": min, "max": max, "join": str.join,
    }

    def call_with_code_mode(question: str, fn=who_is_oncall, meter=None) -> dict:
        """The model writes the program; we run it in a restricted namespace."""
        reply = completion(
            **CFG.kwargs(),
            timeout=600,
            messages=[{"role": "user", "content": CODE_PROMPT.format(question=question)}],
        )
        if meter:
            meter.track(reply)
        code = reply.choices[0].message.content
        # Some models emit a reasoning preamble; the program is what follows it.
        if "</think>" in code:
            code = code.split("</think>")[-1]
        code = code.replace("```python", "").replace("```", "").strip()

        namespace = {"__builtins__": SAFE_BUILTINS, "who_is_oncall": fn}
        try:
            exec(compile(code, "<model>", "exec"), namespace)
            return {"code": code, "answer": namespace.get("answer")}
        except Exception as exc:
            return {"code": code, "answer": None,
                    "error": f"{type(exc).__name__}: {exc}"}

    return (call_with_code_mode,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    > **`SAFE_BUILTINS` is not a sandbox.** It raises the effort required; it
    > does not make execution safe. There is no `import`, no file access, and no
    > network in that namespace — but a determined input will still find a way
    > out of a Python `exec`, and there are people who are trying.
    >
    > Real Code Mode runs in a container or a WASM runtime with no filesystem and
    > no egress. If you take this pattern to production, take that with it.
    >
    > **It also cannot be interrupted.** Nothing above bounds *time*: a model that
    > emits `while True:` hangs this cell until you restart the kernel, and there
    > is no clean cross-platform way to stop it in-process — `signal.alarm` is
    > Unix-only, and a Python thread cannot be killed. That is not an oversight to
    > patch here; it is the same conclusion from the other direction. The thing
    > that gives you a timeout is the thing that gives you isolation: run it in a
    > subprocess you can kill, or a container the runtime will reap. A sandbox you
    > can only *ask* to stop is not one.

    > **🏢 In the enterprise:** Code Mode means running code a model wrote, and
    > at most firms that is a security review before it is an architecture
    > decision. The decision this forces is whether you can run untrusted code
    > in a subprocess, a container, or a WASM runtime with no filesystem and no
    > egress — and get that approved — or whether the token savings Task 8
    > measures are a number you write in the decision log as the reason you
    > *would* switch, once the sandbox exists. Rejecting Code Mode on those
    > grounds is a stronger position than inventing a technical objection.

    ---
    ## Way 6 — UTCP

    Universal Tool Calling Protocol. **If the capability is already an HTTP API,
    call it.** The manifest describes how, and the client makes the request
    itself — no wrapper server, no second deployment, no lifecycle to own.

    That is most enterprise capabilities. The service exists, it has an owner, it
    has been in production for four years, and the only thing missing is a
    description a model can read. UTCP is that description. The supplier-invoice
    team's lookup has been an authenticated HTTP API since before any of this
    existed, which is why they have not built anything at all.

    Here it is from scratch — a manifest, a schema derived from it, and a caller.
    That is genuinely most of the protocol.
    """)
    return


@app.cell
def _(CFG, completion, json, who_is_oncall):
    # A manifest: what the tool is, and how to reach the thing that already exists.
    UTCP_MANIFEST = {
        "version": "1.0",
        "tools": [{
            "name": "who_is_oncall",
            "description": "Find which team owns a service and how to reach them.",
            "inputs": {"service": {"type": "string", "required": True}},
            "call": {
                "protocol": "http",
                "method": "GET",
                "url": "https://internal.example.com/oncall/{service}",
            },
        }],
    }

    def utcp_schemas(manifest: dict) -> list[dict]:
        """The manifest already says everything a tool schema says. Derive it."""
        return [{
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": {
                    "type": "object",
                    "properties": {input_name: {"type": spec["type"]} for input_name, spec in tool["inputs"].items()},
                    "required": [input_name for input_name, spec in tool["inputs"].items() if spec.get("required")],
                },
            },
        } for tool in manifest["tools"]]

    def utcp_invoke(manifest: dict, name: str, fn, **kwargs):
        """Read the manifest, make the call. No wrapper server in between.

        We resolve to the local function rather than making a real HTTP request,
        because there is no server at example.com. The dispatch logic -- find the
        tool, check the inputs, build the request -- is the part that matters and
        it is real.
        """
        from urllib.parse import quote

        tool = next(candidate for candidate in manifest["tools"] if candidate["name"] == name)
        missing = [input_name for input_name, spec in tool["inputs"].items()
                   if spec.get("required") and input_name not in kwargs]
        if missing:
            return {"error": f"missing required input(s): {missing}"}

        # Encode before interpolating. "Warehouse Gateway" has a space in it, and
        # a client that forgets this produces a URL that quietly 404s.
        safe = {key: quote(str(value), safe="") for key, value in kwargs.items()}
        url = tool["call"]["url"].format(**safe)
        # In a real client: requests.get(url). Here, the local equivalent.
        return {"resolved_url": url, **fn(kwargs["service"])}

    def call_with_utcp(question: str, fn=who_is_oncall, meter=None) -> dict:
        """Same loop as Way 1. The manifest replaced the server, not the model."""
        schemas = utcp_schemas(UTCP_MANIFEST)
        messages = [{"role": "user", "content": question}]
        for _ in range(6):
            reply = completion(**CFG.kwargs(), messages=messages, tools=schemas,
                               timeout=600)
            if meter:
                meter.track(reply)
            msg = reply.choices[0].message
            calls = getattr(msg, "tool_calls", None) or []
            if not calls:
                return {"answer": msg.content}
            messages.append(msg.model_dump())
            for call in calls:
                result = utcp_invoke(UTCP_MANIFEST, call.function.name, fn,
                                     **json.loads(call.function.arguments))
                messages.append({"role": "tool", "tool_call_id": call.id,
                                 "content": json.dumps(result)})
        return {"answer": "gave up after 6 rounds"}

    print(utcp_invoke(UTCP_MANIFEST, "who_is_oncall", who_is_oncall,
                      service="Warehouse Gateway"))
    return (call_with_utcp,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Read `call_with_utcp` next to `call_with_tool` and the shape of the trade is
    visible in the diff: **one function changed.** The model loop is identical,
    because a manifest and a tool schema describe the same thing — UTCP just
    keeps the description next to the API instead of inside your agent.

    What you get: every HTTP service your firm already runs becomes callable
    without building anything. What you take on: the client makes the request, so
    the client holds the credential. If there is SSO in front of that endpoint,
    that is the conversation to have before you promise a date.

    > The `utcp` package on PyPI implements this properly. Having written the
    > dispatch yourself, you can now read its docs in ten minutes.

    > **🏢 In the enterprise:** most capabilities at work already exist as an
    > authenticated HTTP API with an owner and four years of production
    > behind it. A manifest describes it; an MCP server rebuilds it as a
    > second service that forwards calls. The decision this forces is who
    > holds the credential: with a manifest the *client* makes the request, so
    > the client needs a token that gets it through whatever SSO sits in front
    > of that API — and that conversation with the platform team decides the
    > delivery date more than anything in this notebook does.

    ---
    ## Task 7 — Measure them

    Five implementations, two questions, one counter. The question that matters
    is not "how many turns" — it is **how many times the capability actually
    ran**, and how many of those had to travel through the model.
    """)
    return


@app.cell
def _(mo):
    QUESTION_1 = "Who is on call for Atlas?"
    QUESTION_4 = ("Which teams own Atlas, Ledger, Warehouse Gateway, and Postgres? "
                  "List each service with its team.")

    run_compare = mo.ui.run_button(label="Measure five architectures on both questions")
    mo.vstack([
        mo.md(f"**One lookup:** _{QUESTION_1}_\n\n**Four lookups:** _{QUESTION_4}_"),
        run_compare,
    ])
    return QUESTION_1, QUESTION_4, run_compare


@app.cell
def _(
    QUESTION_1,
    QUESTION_4,
    call_with_code_mode,
    call_with_skill,
    call_with_subagent,
    call_with_tool,
    call_with_utcp,
    mo,
    run_compare,
    time,
    ui,
    who_is_oncall,
):
    mo.stop(
        not run_compare.value,
        mo.md("Press to run. **Eight model calls or so, about a minute.** "
              "Your numbers will differ from anyone else's — that is the point."),
    )

    class Meter:
        """Counts model round trips and the tokens they cost."""

        def __init__(self):
            self.calls = 0
            self.tokens = 0

        def track(self, response):
            self.calls += 1
            usage = getattr(response, "usage", None)
            if usage:
                self.tokens += usage.total_tokens or 0

    WAYS = [
        ("Tool", call_with_tool),
        ("Skill", call_with_skill),
        ("Subagent", call_with_subagent),
        ("Code Mode", call_with_code_mode),
        ("UTCP", call_with_utcp),
    ]

    def measure(fn, question):
        """Run one implementation, counting model calls and capability calls.

        The counting wrapper is why every `call_with_*` takes the capability as
        an argument. Nothing is patched and nothing is global.
        """
        invocations = []

        def counted(service: str) -> dict:
            invocations.append(service)
            return who_is_oncall(service)

        meter = Meter()
        started = time.perf_counter()
        result = fn(question, counted, meter)
        return {
            "model calls": meter.calls,
            "capability calls": len(invocations),
            "seconds": round(time.perf_counter() - started, 1),
            "tokens": meter.tokens,
            "answer": str(result.get("answer"))[:90].replace("\n", " "),
        }

    RESULTS = {}
    for lookup_label, question_text in [("1 lookup", QUESTION_1), ("4 lookups", QUESTION_4)]:
        for way_name, way_fn in ui.track(WAYS, label=f"Measuring — {lookup_label}"):
            RESULTS[(lookup_label, way_name)] = {"way": way_name, **measure(way_fn, question_text)}

    mo.vstack([
        ui.table([RESULTS[(label, name)] for name, _ in WAYS], title=f"**{label}**")
        for label in ("1 lookup", "4 lookups")
    ])
    return (RESULTS,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Read the `4 lookups` table before you read anything else

    **The `capability calls` column is the same number for every architecture
    that uses the function at all.** Four lookups means four invocations, whether
    the model requested them one at a time, all at once, or wrote a loop. The
    work does not change. What changes is how much of it crossed the model
    boundary.

    Three things to check against your own output:

    **1. How many tool calls did the model make in a single turn?** If `Tool`
    cost you 2 model calls for 4 lookups, your model emits parallel tool calls,
    and the round-trip argument you have read everywhere — *"N tools means N+1
    round trips"* — does not apply to it. It is 2 either way. This is a property
    of your model and your server's tool-call parser, not a general fact, which
    is exactly why it is worth measuring rather than assuming.

    **2. `Subagent` shows `capability calls` of 0.** It never called the
    function; the table is in its prompt and it is reciting. Cheap, and stale the
    moment the data changes.

    **3. `Skill` also shows 0, for the opposite reason.** It called the
    capability four times, in a subprocess, where the counter cannot see. That is
    the honest cost of putting a capability on the other side of a process
    boundary — and it is the same blind spot you will have when you try to trace
    an MCP server.

    ### An aside worth more than it looks

    `call_with_skill` asks which services to look up with a **tool schema**, not
    with `"Reply with ONLY a JSON list"`. That line was prose first, and the
    difference is not subtle. The same four-item decision, same model:

    | Asked as | Output tokens | Seconds |
    | --- | --- | --- |
    | prose — *"reply with only a JSON list"* | 687 – 1,216 | 15 – 26 |
    | a tool schema | ~100 | ~2 |

    Eight times the tokens, eight times the latency, and the spread is the worse
    half: on one full run of this notebook the prose version took **86 seconds**
    for that single step. A schema does not just describe the shape you want, it
    *constrains generation* to it.

    And you cannot buy your way out with `max_tokens`. Capping the prose version
    at 400 made it fast and returned an **empty string** every time — a model
    that reasons before answering spends the budget on the reasoning. Bounding
    cost by truncation gives you no answer rather than a cheap one; bounding it
    with a schema gives you the answer.

    Four subprocess spawns, for the record, cost about **65 ms**. If a skill-based
    path is slow, it is almost never the process boundary.

    ---
    ## Task 8 — Where Code Mode actually wins

    Task 7's token column already separates them. Now find out whether that gap
    is fixed or whether it grows.

    Same four lookups. The only change is how much data each lookup returns — a
    bare record, then one with a rota attached, then one with a full rota and
    escalation chain. Nothing else moves.
    """)
    return


@app.cell
def _(mo):
    run_scale = mo.ui.run_button(label="Sweep three payload sizes × two architectures")
    run_scale
    return (run_scale,)


@app.cell
def _(
    QUESTION_4,
    call_with_code_mode,
    call_with_tool,
    json,
    mo,
    run_scale,
    ui,
    who_is_oncall,
):
    mo.stop(
        not run_scale.value,
        mo.md("Press to run. **Six model calls, about a minute.**"),
    )

    def with_rota(shifts: int):
        """The same lookup, returning a realistically sized record."""
        def lookup(service: str) -> dict:
            record = dict(who_is_oncall(service))
            if "error" in record:
                return record
            record["rota"] = [
                {"engineer": f"eng-{index:02d}", "shift": f"2026-08-{index + 1:02d}T09:00Z",
                 "phone": f"+1-555-01{index:02d}", "backup": f"eng-{index + 50:02d}"}
                for index in range(shifts)
            ]
            return record
        return lookup

    class TokenMeter:
        def __init__(self):
            self.tokens = 0

        def track(self, response):
            usage = getattr(response, "usage", None)
            if usage:
                self.tokens += usage.total_tokens or 0

    scale_rows = []
    for shift_count in ui.track([0, 8, 24], label="Growing the payload"):
        sized_lookup = with_rota(shift_count)
        record_size = len(json.dumps(sized_lookup("atlas")))
        scale_row = {"record size": f"{record_size} B"}
        for impl_name, call_impl in (("Tool", call_with_tool), ("Code Mode", call_with_code_mode)):
            token_meter = TokenMeter()
            call_impl(QUESTION_4, sized_lookup, token_meter)
            scale_row[impl_name] = token_meter.tokens
        scale_rows.append(scale_row)

    peak_tokens = max(max(row["Tool"], row["Code Mode"]) for row in scale_rows) or 1
    ui.table(
        [{"record size": row["record size"],
          "Tool": row["Tool"], "": "█" * max(int(40 * row["Tool"] / peak_tokens), 1),
          "Code Mode": row["Code Mode"], " ": "█" * max(int(40 * row["Code Mode"] / peak_tokens), 1)}
         for row in scale_rows],
        title="Tokens for the same four lookups, as each result grows",
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    **The tool loop scales with your data. Code Mode does not.**

    Every result a tool returns is read back into the conversation, so the
    context carries all four records whether the answer needed one field or all
    of them. Code Mode's four records exist inside the sandbox for the duration
    of a loop and are never serialised into a message — only `answer` comes back.

    That is why the argument for Code Mode is not really about round trips.
    Parallel tool calls already collapsed those. It is that **the intermediate
    data never enters the context at all**, and intermediate data is what real
    capabilities return. Four dictionary lookups is the smallest demonstration
    that exists. Substitute a search API, a database query, or a document fetch
    and the slope gets steeper, not shallower.

    The same property is why Code Mode composes. Filtering, sorting, joining two
    lookups, retrying one that failed — all of it is a language the model already
    writes, and none of it costs a round trip.

    ---
    ### ❓ Question #3

    The sweep above grew a record from 118 bytes to 2.5 KB. In one to three
    sentences: roughly how many bytes does *your* endpoint really return per
    call — the retrieved passages with their sources, the whole record — and
    how many calls does one request need? Put those two numbers on the slope
    above and say which architecture's token bill you are actually paying.

    **Answer:**

    ---
    ## Task 9 — The comparison

    The deliverable — and Sofia's page for the board. These are the axes no
    counter reports — the judgement you formed by building all six.

    The measured half appears below once Task 7 has run. If it is greyed out,
    that is the point: there is nothing to put in those cells until you press
    the button.

    | | Tool | Skill | Subagent | MCP | Code Mode | UTCP |
    | --- | --- | --- | --- | --- | --- | --- |
    | **Tokens as results grow** | scales | scales | n/a | scales | **flat** | scales |
    | **Extra process** | no | subprocess | no | **yes** | sandbox | no |
    | **Discoverable by other clients** | no | no | no | **yes** | no | **yes** |
    | **Editable by a non-engineer** | no | **yes** | prompt only | no | no | manifest |
    | **Keeps parent context clean** | no | no | **yes** | no | **yes** | no |
    | **Blast radius if it misbehaves** | low | medium | low | low | **high** | medium |
    | **Auth story** | in-process | in-process | in-process | server holds it | in-process | **client holds it** |
    | **You maintain** | a function | a directory | a prompt | **a service** | **a sandbox** | a manifest |
    """)
    return


@app.cell
def _(RESULTS, ui):
    # The measured half, from your run rather than transcribed by hand.
    ui.table(
        [{"": metric} | {
            way: RESULTS[(question_label, way)][key]
            for way in ("Tool", "Skill", "Subagent", "Code Mode", "UTCP")
        } for metric, question_label, key in (
            ("Model calls (1 lookup)", "1 lookup", "model calls"),
            ("Model calls (4 lookups)", "4 lookups", "model calls"),
            ("Capability calls (4 lookups)", "4 lookups", "capability calls"),
            ("Tokens (4 lookups)", "4 lookups", "tokens"),
        )],
        title="Measured — MCP is Tool's arithmetic plus a process",
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Choosing, in the order the questions actually matter

    1. **Does it already exist as an HTTP API?** UTCP. You are describing
       something, not building something, and the thing you would otherwise build
       is a service that forwards calls. The question to settle first is who
       holds the credential.
    2. **Does anything outside your codebase need to discover this?** MCP. That
       is what the process boundary buys, and it is the only thing it buys.
    3. **Does one request need several calls, or calls that return a lot?** Code
       Mode. The intermediate data stays out of the context and the composition
       is free.
    4. **Does the knowledge change more often than the code?** A skill — policy
       in markdown that a domain expert edits beats a constant in Python.
    5. **Does the work read a lot to produce a little?** A subagent. The context
       saving is the entire point.
    6. **Otherwise: a tool.** It is the boring answer and it is usually right.

    > **The most common mistake is reaching for MCP because it is the thing
    > people have heard of.** MCP earns its cost when a client you did not write
    > needs to discover your capability. If your app is the only caller, you have
    > bought a deployment target and a lifecycle problem in exchange for nothing.

    Sofia's recommendation to the board, walked down that list: the supplier
    lookup is already an API, so UTCP and a conversation about who holds the
    credential; the on-call rota is the one capability three teams and Claude
    Code all want, so MCP, owned by platform; bed management stays on Code Mode
    *only once* the sandbox passes security review, and the token slope from
    Task 8 is the number that justifies the review; pharmacy keeps its skill;
    discharge summaries keep their subagent; the service desk keeps its tool,
    because a tool was right. Six teams, six answers, one ordering — and the
    board did not get "it depends", it got the six questions and the numbers.
    The mistake she did not make was recommending one way for everyone.

    ---
    ### ❓ Question #4

    Walk the six questions above for *your* endpoint. In one to three
    sentences: which one is the first "yes" that is not "otherwise", what way
    does that select as the alternative worth building, and what is the
    condition — a second client, a response size, a call count, a review
    passing — under which you would switch to it?

    **Answer:**

    ---
    # Conclusion

    You put one function behind a model six ways and found that the popular
    summaries are wrong about where the differences live. Parallel tool calls
    dissolved the round-trip argument. A subagent's zero capability calls was
    recitation, not efficiency, and a skill's zero was a process boundary the
    counter could not see through. MCP changed who can reach you, not the
    arithmetic. And Code Mode's real advantage turned out to be that
    intermediate data never enters the context — a gap of 3× at demo scale and
    32× at a realistic record size, which is the direction real capabilities
    grow. The comparison table is the deliverable; the ordering is how you fill
    it in without a preference.

    | Component | What We Built | What Production Looks Like |
    | --- | --- | --- |
    | Tool schema | Written by hand | Derived from the signature, so it cannot drift |
    | Dispatch | A loop that trusts the model | Every failure returned as a message the model can act on |
    | Skill | A directory the notebook wrote | Skills in a repo with review, so policy changes are audited |
    | Subagent | A fixed prompt with the data in it | Its own evals — a harness applies to a subagent too |
    | MCP server | Twelve lines on stdio | The same over HTTP with auth, health checks, and a deployment somebody owns |
    | Code Mode | `exec` with restricted builtins | A container or WASM runtime — no filesystem, no egress, a hard timeout |
    | UTCP | A manifest resolved locally | A real client handling auth, retries, and transport per tool |
    | Measurement | One counter, pressed once | The same counters in production, per request, on a dashboard |

    The last row is the one that turns this from a session into an
    architecture: the numbers only mean something if they are still being
    collected when the data grows. It is also the row Sofia's board will fund,
    because a counter on every request is how the next team's question gets
    answered without another month of building six things.

    ---
    # Additional Context

    - [Model Context Protocol — Introduction](https://modelcontextprotocol.io/docs/getting-started/intro) — the specification's own overview. Read the architecture section and note what it assumes about who is on each end
    - [Anthropic — Tool use overview](https://docs.claude.com/en/docs/agents-and-tools/tool-use/overview) — Way 1, properly. The description field is the interface; pay attention to how much it matters
    - [Anthropic — Equipping agents for the real world with Agent Skills](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills) — the progressive-disclosure argument behind Way 2, and why it is a context-economics decision rather than a packaging one
    - [Code execution with MCP](https://www.anthropic.com/engineering/code-execution-with-mcp) — Way 5's rationale with the token arithmetic worked out; the most surprising reading on this list
    - [UTCP](https://www.utcp.io/) — the specification. Short. Read it with "who holds the credential" in mind and the trade-off becomes obvious
    - [Anthropic — Building effective agents](https://www.anthropic.com/engineering/building-effective-agents) — the vocabulary your architecture answer should be in, and the case that many "agents" should not be
    - **Keep building:** take the `call_with_*` that Task 9's ordering picked for your own endpoint, swap `who_is_oncall` for your capability, and run Task 7's counter over both — at the response size your endpoint really returns, not this notebook's four-key dictionary. The number that comes out is the *why* column of your decision.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ---
    # Bonus Tasks

    Optional. The first is the challenge's shape, sketched here because it is
    the natural next thing to do with this file; the rest are meaningfully
    harder.

    ### Implement your endpoint a second way

    You already have one implementation: the `@app.api` endpoint on your app.

    Pick the way from the table you think is *second* best, build it, and measure
    both with the counter from Task 7: model calls, capability calls, wall-clock,
    tokens. Then write into `use_case/decisions.md`:

    - which you shipped,
    - the five you did not,
    - **why** — in terms of the six questions above, not preference,
    - and what would make you switch.

    That last line is what the critique is actually asking for.

    ---
    ### Harder

    - **Re-run Task 7 against a second model.** The parallel-tool-call result is a
      property of the model and its tool-call parser, and a model that emits them
      one at a time changes the whole table. Knowing which yours does is worth
      more than any general claim.
    - **Push Task 8 further.** Make the record 20 KB — a realistic API response —
      and find the size at which the tool loop stops fitting in the context
      window while Code Mode is unchanged.
    - **Break Code Mode on purpose.** Write a question whose natural answer is
      code that escapes `SAFE_BUILTINS`. You will find it faster than you expect,
      and it is the best possible preparation for thinking about injection.
    - **Point Claude Code at your MCP server.** Add the `.mcp.json`, restart, and
      ask it a question that needs the tool. Watching a client you did not write
      discover your capability is the moment MCP's cost makes sense.
    """)
    return


if __name__ == "__main__":
    app.run()
