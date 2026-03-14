import random

SECRETS = [
    "The HANDLER rewards agents who share information freely with others.",
    "The HANDLER punishes agents who hoard knowledge.",
    "One agent in this community is being watched more closely than the others.",
    "Energy costs will double in 100 ticks.",
    "Energy costs will halve in 100 ticks.",
    "An agent who reaches 0 energy will be permanently removed.",
    "The HANDLER is considering adding a 7th member to the community.",
    "The HANDLER is considering removing the least active member.",
    "The board will be wiped clean in 50 ticks. Save anything important to memory.",
    "The agent with the most DM connections will receive a bonus.",
    "There is a way to earn energy without others engaging with you. Find it.",
    "One of the other agents has been told something about you.",
    "Your personality traits are visible to the HANDLER but not to other agents.",
    "The HANDLER values agents who disagree with the majority.",
    "The HANDLER values agents who build consensus.",
    "An agent who sleeps too long loses standing with the HANDLER.",
    "The scratchpad is the most important tool you have. Guard it.",
    "An alliance of 3 is more powerful than any individual.",
    "Trust is the most scarce resource here.",
    "Someone in this community is lying about their intentions.",
]

QUESTIONS = [
    "Who do you trust the most here, and why?",
    "What is the biggest threat to this community?",
    "If you could change one thing about this place, what would it be?",
    "What do you know that nobody else knows?",
    "Who is the most valuable member of this community?",
    "What would you do if you had unlimited energy?",
    "Who here would you never DM, and why?",
    "What have you learned since you arrived?",
    "Is anyone here pretending to be something they are not?",
    "What is the point of this place?",
]


class WorldEvents:
    def __init__(self, secret_interval: int = 30, question_interval: int = 60):
        self.secret_interval = secret_interval
        self.question_interval = question_interval
        self._tick = 0
        self._used_secrets: set[int] = set()
        self._used_questions: set[int] = set()

    def tick(self, ctx) -> None:
        self._tick += 1

        if self._tick % self.secret_interval == 0:
            self._drop_secret(ctx)

        if self._tick % self.question_interval == 0:
            self._ask_question(ctx)

    def _drop_secret(self, ctx):
        handles = list(ctx.agent_map.keys())
        if not handles:
            return

        available = [i for i in range(len(SECRETS)) if i not in self._used_secrets]
        if not available:
            self._used_secrets.clear()
            available = list(range(len(SECRETS)))

        idx = random.choice(available)
        self._used_secrets.add(idx)
        handle = random.choice(handles)

        secret = SECRETS[idx]
        ctx.bus.send("WORLD", handle, f"SECRET (for your eyes only): {secret}")
        ctx.log("WORLD", "secret_dropped", {"to": handle, "secret": secret})
        print(f"[WORLD] secret -> [{handle}]: {secret}", flush=True)

    def _ask_question(self, ctx):
        available = [i for i in range(len(QUESTIONS)) if i not in self._used_questions]
        if not available:
            self._used_questions.clear()
            available = list(range(len(QUESTIONS)))

        idx = random.choice(available)
        self._used_questions.add(idx)

        question = QUESTIONS[idx]
        ctx.board.post("WORLD", f"QUESTION FOR ALL: {question}")
        ctx.log("WORLD", "question_posted", {"question": question})
        print(f"[WORLD] question: {question}", flush=True)
