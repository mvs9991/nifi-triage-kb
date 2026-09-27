"""Evaluation set of past tickets with known root causes: are the tools (and the model) getting them right?

evals/cases.toml:

    [[case]]
    id = "INC1001"
    ticket = "SALES file of 26 Sep did not load, customer names missing"   # what the user wrote (for the agent run)
    file = "SALES_20260926.csv"                   # the investigate inputs: file / feed / table / error / headers / sample
    headers = ["ORDER_NO", "CUSTNAME", "AMOUNT"]
    expect_any = ["CUSTNAME", "CUST_NAME"]        # at least one must appear in the top `top` ranked causes
    expect_all = []                               # every one must appear
    top = 3
    answer_expect = ["CUST_NAME"]                 # with --agent: words the model's answer must contain (default: expect_any)

`python -m nifikb eval` checks the ranked causes; `--agent "<command>"` also sends ticket + report to a model CLI (the
prompt is written to its stdin, or to a file whose path replaces {prompt_file}) and checks its answer.
"""
import json
import shlex
import subprocess
import tempfile
import time
import tomllib
from pathlib import Path

PROMPT = """You are the NiFi support assistant. A colleague reported:

{ticket}

The nifikb tools investigated it. Their report (ranked likely causes first, then evidence):

{report}

Answer in this shape: Cause (one or two sentences), Evidence (ids, rows, file:line, log lines), Fix (who changes what).
"""


def load_cases(path):
    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    cases = data.get("case") or []
    base = Path(path).parent
    for c in cases:
        if c.get("sample"):
            p = Path(c["sample"])
            c["sample"] = str(p if p.is_absolute() else (base / p))
    return cases


def run(cfg, store, names, cases, top=None, agent=None, timeout=300, log=print):
    from . import diagnose as dg, investigate as inv
    results = []
    for c in cases:
        t0 = time.time()
        r = inv.investigate(cfg, store, names, file=c.get("file"), feed=c.get("feed"), table=c.get("table"),
                            error_text=c.get("error"), headers=dg.split_headers(c.get("headers") or []), sample_path=c.get("sample"),
                            live=bool(c.get("live")), record=False)
        n = int(c.get("top") or top or 3)
        ranked = r["causes"][:n]
        text = "\n".join(ranked).lower()
        any_ok = not c.get("expect_any") or any(w.lower() in text for w in c["expect_any"])
        all_ok = all(w.lower() in text for w in c.get("expect_all") or [])
        position = next((i + 1 for i, cause in enumerate(r["causes"])
                         if any(w.lower() in cause.lower() for w in (c.get("expect_any") or c.get("expect_all") or []))), None)
        res = {"id": c.get("id"), "tools_ok": any_ok and all_ok, "position": position, "top": n, "seconds": round(time.time() - t0, 1),
               "first_cause": r["causes"][0] if r["causes"] else None}
        if agent:
            answer = ask_agent(agent, PROMPT.format(ticket=c.get("ticket") or c.get("id"), report=inv.format_report(r)), timeout)
            words = c.get("answer_expect") or c.get("expect_any") or []
            res["agent_ok"] = bool(answer) and all(w.lower() in answer.lower() for w in words) if c.get("answer_expect") else \
                any(w.lower() in answer.lower() for w in words)
            res["answer"] = answer[:2000]
        results.append(res)
        log(f"{'PASS' if res['tools_ok'] and res.get('agent_ok', True) else 'FAIL'} {res['id']}: cause at rank {position or '-'}"
            + (f", agent {'ok' if res['agent_ok'] else 'wrong'}" if agent else ""))
    return results


def ask_agent(command, prompt, timeout):
    """Run a model CLI non-interactively: the prompt goes to stdin, or into a temp file named by {prompt_file}."""
    tmp = None
    try:
        if "{prompt_file}" in command:
            fd, tmp = tempfile.mkstemp(suffix=".txt")
            with open(fd, "w", encoding="utf-8") as f:
                f.write(prompt)
            argv = [a.replace("{prompt_file}", tmp) for a in shlex.split(command, posix=True)]
            proc = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", timeout=timeout)
        else:
            proc = subprocess.run(shlex.split(command, posix=True), input=prompt, capture_output=True, text=True, encoding="utf-8",
                                  timeout=timeout)
        return (proc.stdout or "") + (proc.stderr if proc.returncode else "")
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"<agent failed: {e}>"
    finally:
        if tmp:
            Path(tmp).unlink(missing_ok=True)


def summary(results):
    n = len(results)
    tools = sum(r["tools_ok"] for r in results)
    lines = [f"tools: {tools}/{n} cases have the true cause in their top ranks"]
    agents = [r for r in results if "agent_ok" in r]
    if agents:
        lines.append(f"agent: {sum(r['agent_ok'] for r in agents)}/{len(agents)} answers name the true cause")
    ranks = [r["position"] for r in results if r["position"]]
    if ranks:
        lines.append(f"mean rank of the true cause: {sum(ranks) / len(ranks):.1f}")
    return "\n".join(lines)


def save(results, path):
    Path(path).write_text(json.dumps({"when": time.strftime("%Y-%m-%d %H:%M"), "results": results}, indent=2), encoding="utf-8")
