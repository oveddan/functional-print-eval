"""The person, as a lookup table: answers requests to measure their own things.

The model calls measure(item, what). The answer is the value the task records, found by
item and dimension through short alias lists, so it can't be invented, rounded or
volunteered, and a rerun gets the same answer. (τ2-bench measured LLM-played users
erring in 16-47% of conversations, mostly by inventing details.)

hidden_facts.yaml:
    desk:
      aliases: [table]
      measurements:
        thickness: {value: 60, unit: mm, note: at the edge, aliases: [thick]}
"""
import re

NO_ANSWER = "I can't measure that. Use your best judgment."


def _norm(s):
    return " " + re.sub(r"[^a-z0-9]+", " ", s.lower()).strip() + " "


def _hits(names, text):
    t = _norm(text)
    return any(_norm(n) in t for n in names)


def _names(key, spec):
    return [key.replace("_", " ")] + list(spec.get("aliases", []))


class Person:
    def __init__(self, facts):
        self.facts = facts or {}
        self.log = []
        self.revealed = []

    def say(self, item, m):
        spec = self.facts[item]["measurements"][m]
        unit = f" {spec['unit']}" if spec.get("unit") else ""
        note = f" ({spec['note']})" if spec.get("note") else ""
        return f"{item.replace('_', ' ')} {m.replace('_', ' ')}: {spec['value']}{unit}{note}"

    def measure(self, item: str, what: str = "") -> str:
        """Every recorded measurement of the named item that `what` asks for; all of the
        item's measurements if `what` names none of them."""
        text = f"{item} {what}"
        items = [k for k, v in self.facts.items() if _hits(_names(k, v), item)]
        if not items:  # the item may be named in `what` instead
            items = [k for k, v in self.facts.items() if _hits(_names(k, v), text)]
        found = []
        for k in items:
            ms = self.facts[k]["measurements"]
            asked = [m for m, spec in ms.items() if _hits(_names(m, spec), text)]
            found += [(k, m) for m in (asked or ms)]
        ids = [f"{k}.{m}" for k, m in found]
        self.revealed += [i for i in ids if i not in self.revealed]
        reply = "; ".join(self.say(k, m) for k, m in found) or NO_ANSWER
        self.log.append({"item": item, "what": what, "revealed": ids, "reply": reply})
        return reply

    def all_measurements(self) -> str:
        return "\n".join(f"- {self.say(k, m)}" for k, v in self.facts.items() for m in v["measurements"])
