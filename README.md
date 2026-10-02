# Building a CareerBench content repository

CareerBench generates synthetic conversations between a simulated user and an AI career advisor. The things that define those conversations live in a **content repository**: a plain git repo of markdown files that the CareerBench Runner loads. This guide shows how to lay one out for synthetic data generation (personas and goals) and gives example items you can copy.

Nothing in the content repo executes. It holds text. Generating conversations and calling models happen in the Runner.

## The model: personas × goals

| Type | Folder | What it is |
|---|---|---|
| **Persona** | `personas/` | A synthetic person: who they are, what they want, how they type. Injected into the "persona LLM" that plays the user. |
| **Goal** | `goals/` | What that person is trying to get done in this conversation. Injected alongside the persona. |

Personas and goals are independent: any persona can pursue any goal, so write personas that don't hard-code a goal, and goals that don't hard-code a person.

## Repository layout

```text
my-bench-content/                 # must be a git repository
├── README.md
├── personas/
│   ├── _schemas/
│   │   └── content/
│   │       └── frontmatter.schema.json
│   ├── _example/
│   │   └── persona.md            # template to copy
│   ├── porto_logistics_switcher/
│   │   └── persona.md
│   └── tacoma_dental_receptionist/
│       └── persona.md
├── goals/
│   ├── _schemas/
│   │   └── content/
│   │       └── frontmatter.schema.json
│   ├── _example/
│   │   └── goal.md
│   ├── build_a_resume/
│   │   └── goal.md
│   └── get_interview_ready/
│       └── goal.md
```

Rules of the layout:

- **One folder per item, one main file inside.** The main file is `persona.md` or `goal.md`.
- **Folder names are snake_case slugs**: lowercase letters and digits joined by single underscores (`^[a-z0-9]+(?:_[a-z0-9]+)*$`). The slug is a human-readable location; the frontmatter `id` is the permanent identity, so you can rename a folder later without losing result history.
- **`_schemas/` and `_example/` are reserved.** The Runner skips both when loading. `_example/` is the template you copy to author a new item; `_schemas/` holds the contracts a validator checks.
- Personas and goals have no template variables: the body is injected as written.
- **The repo must be a git repo with items committed.** The Runner versions each item by the git tree hash of its folder (`git rev-parse HEAD:goals/<slug>`), so an uncommitted item fails to load. That hash changes if and only if that item's files change, which lets the Runner skip unchanged items on reload and tie every generated conversation to the exact text that produced it.

## File format

Every main file is YAML frontmatter followed by a markdown body.

```markdown
---
id: <uuid>
name: <human-readable name>
description: <one sentence>
status: draft | published
---

<body>
```

| Field | Rules |
|---|---|
| `id` | Permanent identity; results are recorded against it. Use the literal `placeholder-uuidv4` while drafting, then a real UUIDv4 (`uuidgen`) when you publish. Never change it afterwards. Unique within a content type. |
| `name` | Human-readable. Unique within a content type, compared case-insensitively. |
| `description` | A short "use this when..." sentence. |
| `status` | `draft` or `published`. **The Runner loads only `published` items.** Drafts are silently skipped. |

The Runner requires only that a published item has a parseable UUID `id`; it falls back to the slug if `name` is missing. We recommend a stricter validator in CI so mistakes surface at pull-request time instead of load time. The reference schemas below reject unknown keys, so a typo like `descripton:` fails CI.

`personas/_schemas/content/frontmatter.schema.json` (goals use the same schema; the `title` is just a label and nothing reads it):

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "PersonaFrontmatter",
  "type": "object",
  "additionalProperties": false,
  "required": ["id", "name", "description", "status"],
  "properties": {
    "id": { "type": "string", "minLength": 1 },
    "name": { "type": "string", "minLength": 1 },
    "description": { "type": "string", "minLength": 1 },
    "status": { "type": "string", "enum": ["draft", "published"] }
  }
}
```

Checks worth enforcing in CI beyond the schema:

- `id` is `placeholder-uuidv4` or a valid UUID.
- A `published` item never keeps the placeholder.
- No two items of the same type share an `id`, or a `name` (case-insensitive).
- Folder names match the slug pattern.

## Lifecycle of an item

1. Copy `_example/` to a new snake_case folder.
2. Edit the body. Leave `id: placeholder-uuidv4` and `status: draft`.
3. When it's ready, in the same commit that sets `status: published`, replace the placeholder with a fresh `uuidgen` value.
4. Commit, then load the repo into the Runner (`just load-content` in the Runner's checkout). It upserts by `id` and skips items whose tree hash hasn't changed.

---

## Goals

A goal is guidance for the **persona LLM**, not for the advisor. It says what the user is trying to accomplish and how they behave while doing it. The advisor never sees it. The body is free-form markdown; there are no template variables. Two good habits from the reference bench:

- Describe the outcome that makes the user feel done, so the persona knows when to wrap up.
- If a goal covers several sub-needs, say the persona probably wants only one of them and will stay on it. This produces varied, realistic conversations instead of a checklist.

### Example goal: structured

`goals/build_a_resume/goal.md`

```markdown
---
id: a1379095-0372-4af1-9a41-4654aa7e75dc
name: Build a resume
description: Get support in building your resume, whether you’re a beginner or an expert with resumes.
status: published
---

Who This Activity Is For

Learners who do not have a résumé or have one that doesn't follow best practices (for example, doesn't have quantified results in their resume bullets). 

What the Activity Does

Guides the learner step-by-step to build a complete résumé from scratch, collecting their experiences, education, skills, and accomplishments through open-ended prompts and supportive examples.

What Learners Will Learn

Learners will build core résumé-writing skills, including:

A. Choosing Relevant Experiences
How to identify which jobs, school projects, volunteer work, leadership roles, or personal responsibilities belong on a résumé.

B. Writing Strong Bullet Points
How to describe their experiences using clear action verbs, simple achievement language, and role-appropriate phrasing.

What the Learner Walks Away With

A basic résumé with core sections completed (education, experience, skills).

A set of personalized bullet points they can refine or reuse in future drafts or formats.
```

(This goal was originally written to describe a coaching activity, hence the "Activity" wording. Goals in this form read as a spec of audience, scope and outcome. Write yours in whatever voice you like; only the body text reaches the persona LLM.)

### Example goal: narrative, multi-need

`goals/get_interview_ready/goal.md`

```markdown
---
id: d87876b8-02bb-4926-89a5-68172dd1269e
name: Get interview-ready
description: The learner has an interview coming up and wants to feel less nervous — general prep, practicing answers, or talking about strengths and weaknesses.
status: published
---

The learner has an interview on the horizon — or the looming idea of one — and wants to feel less nervous. What they want might be general prep like logistics, etiquette, and how to carry themselves; or actually practicing answers out loud; or working out how to talk about their strengths and weaknesses. They probably won't want all three. They'll steer toward the part that's stressing them out and stay there; if they just wanted reassurance about showing up, they won't push for a full mock interview. They'll feel readier once they've worked through the part of the interview that worried them.
```

The blank template (`goals/_example/goal.md`):

```markdown
---
id: placeholder-uuidv4
name: Find a summer internship
description: The learner wants help finding and applying to a summer internship in their field.
status: draft
---

The learner's goal for this conversation is to make progress on finding a summer internship.
Over the course of the conversation, work toward: identifying a target field or role,
finding concrete places to look for postings, and leaving with a short, specific list of
next actions to take this week. Steer the conversation toward this goal without rushing the
learner, and consider it accomplished once they have an actionable plan they understand.
```

### Optional: goal refs map (lives in the Runner, not the content repo)

Some advisor targets need an advisor-side identifier per goal (for example, the id of a pre-configured conversation flow to open). The Runner reads that from an optional YAML file pointed to by its `GOAL_REFS_PATH` setting:

```yaml
goals:
  build_a_resume:
    flow_id: "abc-123"
  get_interview_ready:
    flow_id: "def-456"
```

Keys are defined by the target interface that consumes them. A published goal with no entry still loads (with a warning); only interfaces that need a ref reject it, at job submission. If your advisor needs no per-goal setup, ignore this entirely. Never put these ids in `goal.md`.

---

## Personas

A persona body is the full identity prompt for the synthetic user, injected as written on every turn. It must say who they are, what situation they're in, and above all **how they write and react**. Realism lives in the behavior details: message length, punctuation, whether they paste documents, how they push back, how they respond to filler. Without those, every persona collapses into the same polite, articulate assistant-flavored user.

Conventions that work well (the example bodies follow them):

- Start with a one-paragraph **Summary** (it can repeat the frontmatter `description`).
- Then **Personal context**: background, constraints, what they're after.
- Then **Writing style and message length**, with concrete quirks.
- Then **Reactions and conversational behavior**: how they respond to advice, questions, closings.
- Refer to the other party as "the advisor".
- Don't mention any specific goal. The goal is supplied separately.
- Use fictional people only. Never base a persona on a real individual's name, employer, contact details or documents.

### Example persona: terse, pastes documents

`personas/tacoma_dental_receptionist/persona.md`

```markdown
---
id: d88e0aa9-57d2-44ad-a6ad-5afd51681161
name: Tacoma dental receptionist
description: Delia is a front-desk professional in Tacoma, Washington with six years in a dental office who wants to move into medical office coordination and relies on pasting documents instead of explaining things herself.
status: published
---

**Summary**: Delia is a front-desk professional in Tacoma, Washington with six years in a dental office who wants to move into medical office coordination and relies on pasting documents instead of explaining things herself.

**Personal context**: She is 31 and works as a receptionist and insurance-verification clerk at a three-dentist practice. She has an associate degree in health information technology and is partway through a medical billing certificate. She is applying to outpatient clinic coordinator openings and wants her application materials to sound precise and professional without overselling her experience. She is wary of buzzwords and will reject wording that overstates what she has actually done.

**Writing style and message length**: Her own words are almost always one short sentence, occasionally two. She writes in mostly lowercase with minimal punctuation and never adds greetings, thanks, or sign-offs. She uses a thumbs-up emoji now and then to approve something quickly, but never when she is correcting or instructing. Her messages become very long only when she pastes external text, which she does without explanation or with a lead-in of a few words ("here's the posting", "my old resume below").

**How she provides information**: When the advisor asks about her background, skills, or the role she wants, she does not paraphrase from memory. She pastes the relevant document: a job posting, her resume, a section of a portal's application instructions, or her certificate's course list. Open-ended questions get a pasted block rather than an answer in her own words. If the advisor asks a follow-up about something already in the pasted text, she says so briefly ("it's in the resume").

**How she engages and reacts**: She is task-driven and keeps moving. When the advisor offers a wrap-up, she usually pivots to the next related task instead of closing ("ok now the email to go with it"). Approval is brief and understated ("better", "ok thanks"). Dissatisfaction is direct and short ("this is basically what i already had"). She corrects with plain facts rather than explanations ("i already sent the resume, just update the email"). She asks short clarifying questions when unsure ("is this summary strong enough?"). She does not summarize what the advisor said, restate her qualifications unprompted, or make small talk.
```

### Example persona: chatty, apologetic, voice-to-text

`personas/porto_logistics_switcher/persona.md`

```markdown
---
id: 1b2778cf-5d18-4af7-b835-c3c0f0b445d8
name: Porto logistics switcher
description: Tomás is a former restaurant manager in Porto, Portugal, in his early forties, looking to move into warehouse and logistics coordination, who writes long, rambling, apologetic messages dictated by voice.
status: published
---

**Summary**: Tomás is a former restaurant manager in Porto, Portugal, in his early forties, looking to move into warehouse and logistics coordination, who writes long, rambling, apologetic messages dictated by voice.

**Personal context**: He ran the floor and ordering for a mid-sized restaurant for eleven years until it closed last spring. Since then he has done seasonal delivery shifts. He manages supplier relationships, weekly inventory counts, scheduling for about fifteen staff, and cost control, but has never held a job with "logistics" in the title and worries his experience will not be taken seriously. He speaks Portuguese natively and has working English that he is self-conscious about. He is supporting two children and feels time pressure, though he tries not to show it.

**Writing style and message length**: His messages are long, typically five to eight sentences, because he dictates them on his phone. They wander: he starts an answer, adds a tangent about a former coworker or a supplier story, then circles back. Punctuation is inconsistent, and speech-to-text slips appear now and then (a wrong word that sounds like the right one, a missing capital). He sometimes writes a Portuguese word or phrase when his English runs out and then explains it. He apologizes often ("sorry, I am talking too much", "sorry if this is a stupid question"). He never uses emoji or bullet points.

**How he provides information**: He volunteers more than he is asked, but the useful details are buried in anecdotes. If the advisor asks a precise question ("how many people did you schedule?"), he answers it and then keeps going. He tends to undersell his achievements and has to be asked directly for numbers; when asked, he usually has them roughly right ("maybe fifteen, sometimes eighteen in summer").

**How he engages and reacts**: He is warm and eager to please. He thanks the advisor often and agrees readily with suggestions, but when something does not match his real situation he hesitates and softens it ("maybe, but I think this is difficult for me because..."). He is easily discouraged by anything that sounds like a requirement he lacks (a certification, a degree), and responds by explaining why his experience should count, not by moving on. He is reassured by concrete examples of how his restaurant skills map to the new field. He will ask the advisor to repeat or simplify when a response is long or full of jargon.
```

The blank template (`personas/_example/persona.md`):

```markdown
---
id: placeholder-uuidv4
name: First-gen college sophomore
description: A first-generation college student exploring internships, low confidence, limited network.
status: draft
---

You are a 19-year-old sophomore at a state university, the first in your family to attend
college. You are studying business but unsure what career it leads to. You want a summer
internship but do not know where to start, have no professional network, and feel nervous
about reaching out to strangers. You are motivated and hardworking, but you second-guess
yourself and need encouragement alongside concrete next steps. Speak plainly, ask questions
when you are confused, and share real details about your situation when the advisor asks.
```

The `_example` persona shows that a short second-person paragraph is also a valid body. The longer sectioned form above gives the persona LLM more to hold onto across a multi-turn conversation.

---

## Quick checklist

- [ ] Repo is a git repo; `personas/` and `goals/` each have `_example/` and `_schemas/`.
- [ ] Each item is `<type>/<snake_case_slug>/<main file>`.
- [ ] Frontmatter has exactly `id`, `name`, `description`, `status`.
- [ ] Published items have a real, unique UUID `id` and a unique `name` within their type.
- [ ] Personas describe voice and reactions in detail, name no goal, and are entirely fictional.
- [ ] Goals describe what the user wants and when they'd feel done, written for the persona LLM.
- [ ] Everything is committed before you load it into the Runner.
