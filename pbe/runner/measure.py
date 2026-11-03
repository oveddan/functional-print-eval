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

from pydantic import BaseModel, ConfigDict

from pbe.runner.trial_record import Measurement

NO_ANSWER = "I can't measure that. Use your best judgment."


class Recorded(BaseModel):
    """One measurement the task records. The value stays as written: 60, or "about 22"."""
    model_config = ConfigDict(extra="forbid")
    value: str | int | float
    unit: str = ""
    note: str = ""
    aliases: list[str] = []


class Thing(BaseModel):
    """One of the person's own things, and what's recorded about it."""
    model_config = ConfigDict(extra="forbid")
    aliases: list[str] = []
    measurements: dict[str, Recorded]


def _padded_words(text):
    """Lower case, punctuation as spaces, and a space at each end, so a name matches whole words only."""
    return " " + re.sub(r"[^a-z0-9]+", " ", text.lower()).strip() + " "


def _mentions(text, names):
    words = _padded_words(text)
    return any(_padded_words(name) in words for name in names)


def _names(key, entry):
    return [key.replace("_", " ")] + entry.aliases


class Person:
    def __init__(self, facts):
        self.things = {name: Thing.model_validate(thing) for name, thing in (facts or {}).items()}
        self.log: list[Measurement] = []
        self.revealed: list[str] = []

    def say(self, thing, measurement):
        recorded = self.things[thing].measurements[measurement]
        unit = f" {recorded.unit}" if recorded.unit else ""
        note = f" ({recorded.note})" if recorded.note else ""
        return f"{thing.replace('_', ' ')} {measurement.replace('_', ' ')}: {recorded.value}{unit}{note}"

    def _things_named(self, item, request):
        """The things `item` names. If it names none, the item may be named in `what` instead."""
        named = [name for name, thing in self.things.items() if _mentions(item, _names(name, thing))]
        return named or [name for name, thing in self.things.items() if _mentions(request, _names(name, thing))]

    def _measurements_asked_for(self, thing, request):
        """The thing's measurements the request names, or all of them if it names none."""
        measurements = self.things[thing].measurements
        asked = [name for name, recorded in measurements.items() if _mentions(request, _names(name, recorded))]
        return asked or list(measurements)

    def measure(self, item: str, what: str = "") -> str:
        """Every recorded measurement of the named item that `what` asks for; all of the
        item's measurements if `what` names none of them."""
        request = f"{item} {what}"
        found = [(thing, measurement) for thing in self._things_named(item, request)
                 for measurement in self._measurements_asked_for(thing, request)]
        ids = [f"{thing}.{measurement}" for thing, measurement in found]
        self.revealed += [revealed for revealed in ids if revealed not in self.revealed]
        reply = "; ".join(self.say(thing, measurement) for thing, measurement in found) or NO_ANSWER
        self.log.append(Measurement(item=item, what=what, revealed=ids, reply=reply))
        return reply

    def every_measurement(self):
        """(thing, measurement) for everything the task records, in the file's order."""
        return [(thing, measurement) for thing, entry in self.things.items() for measurement in entry.measurements]

    def all_measurements(self) -> str:
        return "\n".join(f"- {self.say(thing, measurement)}" for thing, measurement in self.every_measurement())
