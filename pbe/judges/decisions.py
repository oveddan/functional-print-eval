"""OpenRouter's Decisions API as a judge: typed questions in, probabilities out.

Request and response shapes are from OpenRouter's API reference ("Submit a decisions request",
/docs/api/api-reference/alphadecisions) and its multimodal guide (/docs/guides/community/multimodal-decisions),
read 2026-11-12. One POST to /api/alpha/decisions carries a model, a `state` (what is judged: a string, or a list
of strings and image or video parts) and `questions`, keyed by id, each one of:

- noul: yes or no; the answer is the probability of yes.
- choice: one option from `criteria` (option name -> guidance); the answer has a probability per option.
- score: an ordered scale, lowest first; the answer has a probability per level.
- box: where something is in an image (TypeSafe Jev only); edges as fractions of width and height from the top left.

A judge is only for calls no program can make. Code decides everything it can (docs/decisions-api.md).
"""
import base64
import json
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from pbe.runner.llm import api_key

URL = "https://openrouter.ai/api/alpha/decisions"
JEV = "typesafe/jev-1.14"
LUNA = "openai/gpt-6-luna-decisions"
GEMINI = "google/gemini-decision-1"  # reads video and audio; Gemini models are also contestants in the eval
MODELS = (JEV, LUNA)
BOX_MODELS = (JEV,)  # the API reference: other providers answer a box question with 400
PRICE_PER_M_INPUT = 0.10  # USD, all three decisions models in the brief; output tokens are free


# --- questions ---

class Noul(BaseModel):
    type: Literal["noul"] = "noul"
    instructions: str
    criteria: dict[str, str] | None = None  # optional "true" and "false" guidance


class Choice(BaseModel):
    type: Literal["choice"] = "choice"
    instructions: str
    criteria: dict[str, str | list]  # option name -> what it means (Jev also reads images in a list here)


class Box(BaseModel):
    type: Literal["box"] = "box"
    instructions: str


Question = Noul | Choice | Box


class Image(BaseModel):
    """An image part in `state`: a base64 data URL (Jev reads PNG and JPEG only)."""
    type: Literal["image_url"] = "image_url"
    image_url: dict[str, str]

    @classmethod
    def jpeg(cls, data: bytes) -> "Image":
        return cls(image_url={"url": "data:image/jpeg;base64," + base64.b64encode(data).decode()})


class Video(BaseModel):
    """A video part in `state` (Gemini Decision 1 and Clef Omni only): an inline base64 MP4. Gemini also fetches
    public https URLs; this eval never uses that, so Dan's clips stay private."""
    type: Literal["video_url"] = "video_url"
    video_url: dict[str, str]

    @classmethod
    def mp4(cls, data: bytes) -> "Video":
        return cls(video_url={"url": "data:video/mp4;base64," + base64.b64encode(data).decode()})


class Request(BaseModel):
    model: str
    state: str | list[str | Image | Video]
    questions: dict[str, Question]


# --- answers ---

class Edges(BaseModel):
    top: float
    bottom: float
    left: float
    right: float

    def centre(self) -> tuple[float, float]:
        return (self.left + self.right) / 2, (self.top + self.bottom) / 2


class Answer(BaseModel):
    type: str  # noul, choice, score, box or refusal
    noul: float | None = None
    choice: str | None = None
    probabilities: dict[str, float] | None = None
    box: Edges | None = None
    confidence: float | None = None


class Usage(BaseModel):
    input_tokens: int
    output_tokens: int
    cost: float | None = None


class Decision(BaseModel):
    """One call's answers, with what it cost and how long it took."""
    model: str
    answers: dict[str, Answer]
    usage: Usage
    seconds: float
    id: str = ""

    @property
    def cost(self) -> float:
        if self.usage.cost is not None:
            return self.usage.cost
        return self.usage.input_tokens * PRICE_PER_M_INPUT / 1e6


class DecisionsError(RuntimeError):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class OverBudget(RuntimeError):
    pass


class Budget:
    """A hard spend cap across threads. A call reserves its most it could cost before it starts and settles
    to what it did cost when it returns, so calls running side by side can't pass the cap together."""

    def __init__(self, dollars: float):
        self.cap, self.spent, self.reserved, self._lock = dollars, 0.0, 0.0, threading.Lock()

    def reserve(self, most: float):
        with self._lock:
            if self.spent + self.reserved + most > self.cap:
                raise OverBudget(f"spent ${self.spent:.4f} of the ${self.cap:.2f} cap "
                                 f"(${self.reserved:.4f} held for calls running, ${most:.4f} more asked)")
            self.reserved += most

    def settle(self, most: float, cost: float):
        with self._lock:
            self.reserved -= most
            self.spent += cost


def most_it_could_cost(body: bytes) -> float:
    """An upper bound: every byte of the request a token, at the highest price. Images are counted by their
    base64 size, far above what they're billed, so the bound is loose for photos."""
    return len(body) * PRICE_PER_M_INPUT / 1e6


# --- the call ---

def _post(body: bytes) -> dict:
    request = urllib.request.Request(URL, data=body, headers={
        "Authorization": f"Bearer {api_key()}", "Content-Type": "application/json", "X-Title": "print-build-eval"})
    with urllib.request.urlopen(request, timeout=300) as reply:
        return json.load(reply)


def _error_message(error: urllib.error.HTTPError) -> str:
    try:
        return json.load(error).get("error", {}).get("message", "")
    except (json.JSONDecodeError, AttributeError):
        return ""


RETRY_STATUS = (429, 500, 502, 503, 524, 529)


def _attempt(body: bytes, model: str) -> Decision:
    """One POST, as a Decision or a DecisionsError: an HTTP error, a lost connection, a timeout, or a reply
    that carries an error instead of answers."""
    started = time.monotonic()
    try:
        reply = _post(body)
    except urllib.error.HTTPError as error:
        raise DecisionsError(f"HTTP {error.code}: {_error_message(error)}", error.code) from None
    except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
        raise DecisionsError(f"no reply: {error}") from None
    if "answers" not in reply:
        error = reply.get("error") or {}
        raise DecisionsError(f"no answers in the reply: {error.get('message', '')}", error.get("code"))
    return Decision(model=reply.get("model", model), answers=reply["answers"], usage=reply["usage"],
                    seconds=time.monotonic() - started, id=reply.get("id", ""))


def _worth_retrying(error: DecisionsError) -> bool:
    return error.status is None or error.status in RETRY_STATUS  # no status: the connection, not the request


def decide(request: Request, budget: Budget, retries: int = 3, most: float | None = None) -> Decision:
    """Send one request. Lost connections, timeouts, 429 and 5xx are retried; 402 (credits or the key's limit)
    stops the run. Whatever happens, the reservation is settled. `most` replaces the byte-count bound where a
    tighter one is known (video)."""
    body = request.model_dump_json(exclude_none=True).encode()
    most = most_it_could_cost(body) if most is None else most
    budget.reserve(most)
    cost = 0.0
    try:
        for attempt in range(retries + 1):
            try:
                decision = _attempt(body, request.model)
            except DecisionsError as error:
                if attempt < retries and _worth_retrying(error):
                    time.sleep(2 ** attempt)
                    continue
                raise
            cost = decision.cost
            return decision
        raise AssertionError("unreachable")
    finally:
        budget.settle(most, cost)


# --- photos ---

def photo_jpeg(path: Path, longest_side: int = 1500) -> bytes:
    """A photo (HEIC from the phone) as an upright JPEG. Jev doesn't apply EXIF orientation, so it's baked in.
    Read from Dan's Dropbox and converted in a temp folder: photos never go in the repo."""
    from PIL import Image as PILImage, ImageOps
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "photo.jpg"
        subprocess.run(["sips", "-s", "format", "jpeg", str(path), "--out", str(out)], check=True, capture_output=True)
        image = ImageOps.exif_transpose(PILImage.open(out))
        image.thumbnail((longest_side, longest_side))
        upright = Path(tmp) / "upright.jpg"
        image.convert("RGB").save(upright, quality=90)
        return upright.read_bytes()


MAX_ASPECT = 3.0


def _widen(low: float, high: float, at_least: float, limit: int) -> tuple[float, float]:
    """Grow [low, high] about its middle to at least `at_least` long, inside [0, limit]."""
    grow = max(0.0, at_least - (high - low)) / 2
    return max(0.0, low - grow), min(float(limit), high + grow)


def crop_jpeg(jpeg: bytes, edges: Edges, margin: float = 0.15, smallest_side: int = 320) -> bytes:
    """A region of a photo, with a margin, scaled up so each side is at least `smallest_side` (Jev's floor is 256)."""
    import io
    from PIL import Image as PILImage
    image = PILImage.open(io.BytesIO(jpeg))
    w, h = image.size
    dx, dy = (edges.right - edges.left) * margin, (edges.bottom - edges.top) * margin
    left, top, right, bottom = (edges.left - dx) * w, (edges.top - dy) * h, (edges.right + dx) * w, (edges.bottom + dy) * h
    left, right = _widen(left, right, (bottom - top) / MAX_ASPECT, w)  # a thin strip scaled up would pass Jev's
    top, bottom = _widen(top, bottom, (right - left) / MAX_ASPECT, h)  # 1568 px limit on the long side
    region = image.crop((int(left), int(top), int(right), int(bottom)))
    scale = max(1.0, smallest_side / min(region.size))
    region = region.resize((int(region.width * scale), int(region.height * scale)))
    out = io.BytesIO()
    region.save(out, format="JPEG", quality=90)
    return out.getvalue()


# --- video ---

GEMINI_MAX_REQUEST_BYTES = 20_000_000  # Google: inline video only while the whole request is under 20 MB
VIDEO_TOKENS_PER_SECOND_MOST = 600  # twice Google's "approximately 300 tokens per second" at high resolution


class Footage(BaseModel):
    """An MP4 made from a master, and how long it runs."""
    mp4: bytes
    seconds: float


def _seconds(path: Path) -> float:
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                           check=True, capture_output=True, text=True)
    return float(probe.stdout.strip())


def video_mp4(path: Path, audio: bool, height: int = 720) -> Footage:
    """A clip as a small H.264 MP4 (720p, AAC audio or none), made in a temp folder. The master is only read, and
    nothing is copied into the repo. The phone's rotation is applied by ffmpeg."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "clip.mp4"
        sound = ["-map", "0:a:0", "-c:a", "aac", "-b:a", "64k"] if audio else ["-an"]
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(path), "-map", "0:v:0", *sound,
                        "-vf", f"scale=-2:{height}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
                        "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)], check=True, capture_output=True)
        return Footage(mp4=out.read_bytes(), seconds=_seconds(out))


def most_for_video(clip: Footage, text_bytes: int) -> float:
    """An upper bound for a video request: the clip at twice Google's token rate, and every text byte a token."""
    return (clip.seconds * VIDEO_TOKENS_PER_SECOND_MOST + text_bytes) * PRICE_PER_M_INPUT / 1e6


def about_clip(clip: Footage, shows: str, questions: dict[str, Question], budget: Budget,
               model: str = GEMINI) -> Decision:
    """Test 6: questions about what happens in a clip of a test print being tried."""
    request = Request(model=model, state=[shows, Video.mp4(clip.mp4)], questions=questions)
    size = len(request.model_dump_json(exclude_none=True))
    if size > GEMINI_MAX_REQUEST_BYTES:
        raise ValueError(f"request is {size / 1e6:.1f} MB, over Google's 20 MB for inline video: cut the clip")
    text_bytes = len(shows) + len(json.dumps({k: q.model_dump() for k, q in questions.items()}))
    return decide(request, budget, most=most_for_video(clip, text_bytes))


# --- one function per question ---

SUPPORTS_PLAIN = Noul(
    instructions="Do these 3D-printing instructions plainly ask for the part to be printed with supports?",
    criteria={"true": "A sentence asks for supports outright: 'print with supports', 'enable tree supports', "
                      "'Support: ON', 'supports under the roof'.",
              "false": "They say no supports, say nothing needs support, make supports conditional ('only if your "
                       "slicer asks', 'if it fails, reprint with supports'), or use 'support' in another sense "
                       "(holding the camera, a floor that supports a load)."})
SUPPORTS_EXPECTED = Noul(
    instructions="Do these instructions expect the part to be printed with supports, even without saying so "
                 "outright (for example, a step that says to remove the supports)?",
    criteria={"true": "Supports are asked for, or a step assumes they were used ('remove supports from the bore').",
              "false": "Nothing in them assumes supports were used."})


def supports_questions(instructions: str, model: str, budget: Budget) -> Decision:
    """Test 1: does a design's own text ask for supports? Two readings: plainly, and implied."""
    return decide(Request(model=model, state=instructions,
                          questions={"asks_plainly": SUPPORTS_PLAIN, "expects_supports": SUPPORTS_EXPECTED}), budget)


VERDICTS = {
    "good": "The fit did its job.",
    "too_tight": "The part didn't go in or through, or only by force or screwing, when it should have.",
    "too_loose": "The part went in but was too loose for its job.",
    "failed": "The print itself failed (messed up, stringy, tangled), so the fit isn't the question.",
}


def verdict_from_words(job: str, words: str, model: str, budget: Budget) -> Decision:
    """Test 2: Dan's spoken outcome for a test print, as one of four verdicts, given the job the fit has."""
    state = f"A test print checks a fit. Its job: {job}.\nWhat the person said after trying it: \"{words}\""
    question = Choice(instructions="How did this test print come out, for its job?", criteria=VERDICTS)
    return decide(Request(model=model, state=state, questions={"verdict": question}), budget)


ROOF_LOOKS = {
    "clean": "A solid, flat surface of strands laid side by side, at most a few stray strands.",
    "sagging": "The strands droop or bow down but stay mostly together.",
    "stringy": "Loose, tangled or broken strands; loops and gaps instead of a surface.",
}


def roof_from_photo(jpeg: bytes, what: str, model: str, budget: Budget) -> Decision:
    """Test 3: how a printed roof or bridge looks from underneath, from a photo (or a crop of one)."""
    question = Choice(instructions=f"This photo shows {what}, seen from underneath where the plastic was printed "
                                   "over air. How did it print?", criteria=ROOF_LOOKS)
    return decide(Request(model=model, state=[Image.jpeg(jpeg)], questions={"looks": question}), budget)


ROOF_VERDICTS = {
    "ok": "The roof works: a solid surface of strands laid side by side. A few stray strands are fine.",
    "failed": "The roof failed: gaps, loops or tangles across the hole or pocket instead of a surface.",
}


class Reference(BaseModel):
    """A labelled example photo: one of ROOF_VERDICTS' options and the crop that shows it."""
    verdict: str
    jpeg: bytes


def _criteria_with_examples(references: list[Reference]) -> dict[str, list]:
    """Jev: each option's guidance followed by its example photos."""
    criteria: dict[str, list] = {verdict: [text, "Examples:"] for verdict, text in ROOF_VERDICTS.items()}
    for ref in references:
        criteria[ref.verdict].append(Image.jpeg(ref.jpeg))
    return criteria


def _state_with_examples(references: list[Reference], jpeg: bytes) -> list[str | Image]:
    """Luna reads images only in `state`: each example after its label, then the one to judge."""
    state: list[str | Image] = []
    for ref in references:
        state += [f"Reference photo, {ref.verdict}:", Image.jpeg(ref.jpeg)]
    return state + ["The photo to judge:", Image.jpeg(jpeg)]


def roof_with_references(jpeg: bytes, what: str, references: list[Reference], model: str, budget: Budget,
                         examples_in_criteria: bool) -> Decision:
    """Test 3c: did a printed roof work, ok or failed in Dan's terms, with labelled example photos.
    examples_in_criteria puts the examples in the options (Jev); otherwise in `state` before the photo (Luna)."""
    instructions = (f"The photo to judge shows {what}, seen from underneath where the plastic was printed over air. "
                    "Did the roof work?")
    if examples_in_criteria:
        question = Choice(instructions=instructions, criteria=_criteria_with_examples(references))
        state: list[str | Image] = [Image.jpeg(jpeg)]
    else:
        question = Choice(instructions=instructions, criteria=dict(ROOF_VERDICTS))
        state = _state_with_examples(references, jpeg)
    return decide(Request(model=model, state=state, questions={"verdict": question}), budget)


def locate(jpeg: bytes, target: str, budget: Budget, model: str = JEV) -> Decision:
    """Test 3, Jev only: where in a photo something is."""
    return decide(Request(model=model, state=[Image.jpeg(jpeg)],
                          questions={"where": Box(instructions=target)}), budget)


def failure_class(record: str, options: dict[str, str], model: str, budget: Budget) -> Decision:
    """Test 5: which failure class a failure record belongs to, or none of them."""
    question = Choice(instructions="This is a failure from designing and building a 3D-printed part. "
                                   "Which class of failure is it?", criteria=options)
    return decide(Request(model=model, state=record, questions={"class": question}), budget)


def checklist(transcript: str, questions: dict[str, str], model: str, budget: Budget) -> Decision:
    """Test 4: yes/no questions about what a design session did, all in one call."""
    asked = {qid: Noul(instructions=text) for qid, text in questions.items()}
    return decide(Request(model=model, state=transcript, questions=asked), budget)
